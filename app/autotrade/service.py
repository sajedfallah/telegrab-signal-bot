from __future__ import annotations

import json
import hmac
from datetime import datetime, timezone
from typing import Any

from .. import db
from .trailing_profiles import profile_snapshot


class AutoTradeError(RuntimeError):
    pass


def _license_state(license_key: str):
    latest=db.license_by_key(license_key,active_only=False)
    if not latest:
        raise AutoTradeError("invalid license")
    status = str(latest["status"] or "").lower()
    if status in {"cancelled", "revoked", "suspended"}:
        raise AutoTradeError(f"license is {status}")
    raw=latest["autotrade_expires_at"] if "autotrade_expires_at" in latest.keys() else latest["expires_at"]
    if not raw or not bool(latest["autotrade_access"]):
        raise AutoTradeError("license has no Auto Trade entitlement")
    try:
        active=datetime.fromisoformat(str(raw))>datetime.now(timezone.utc)
    except Exception:
        active=False
    if active and status == "active":
        return latest,"ACTIVE",True,True
    mode = db.get_setting("autotrade_expiry_mode", "A").strip().upper()
    if mode == "C":
        return latest,"EXPIRED_CLOSE",False,True
    if mode == "B":
        return latest,"EXPIRED_NO_MANAGE",False,False
    return latest,"SAFE_MODE",False,True



def authorize_standard_mt5(account_number: str, *, broker: str | None = None,
                           server: str | None = None, ea_version: str | None = None) -> dict[str, Any]:
    """Authorize the public/default EA mode without a customer license.

    Standard mode is deliberately capability-limited: it can receive published
    channel signals and execute them, but it cannot publish manual MT5 signals
    or access admin/global configuration. A synthetic internal identity is used
    only for durable MT5 receipts; it has no Telegram user-facing privileges.
    """
    account = str(account_number or "").strip()
    if not account:
        raise AutoTradeError("account number is required")
    # Internal identity reserved for anonymous standard EA sessions.
    uid = 0
    try:
        db.upsert_user(uid, "nexus_standard", "NEXUS Standard")
    except Exception as exc:
        raise AutoTradeError("could not initialize standard EA identity") from exc
    return {
        "telegram_id": uid,
        "license_id": 0,
        "license_status": "STANDARD",
        "mode": "STANDARD",
        "admin_authenticated": False,
        "account_verified": True,
        "allow_signal_receive": True,
        "allow_new_trade": True,
        "allow_manage_trade": True,
        "allow_advanced_settings": False,
        "allow_manual_signal": False,
        "allow_reports": False,
        "vip_access": False,
        "force_close_all": False,
        "expires_at": "",
        "account_number": account,
    }

def authorize_admin_mt5(account_number: str, admin_token: str | None = None) -> dict[str, Any]:
    """Authorize a private administrator MT5 terminal without a customer license.

    Access is limited by both an allow-listed MT5 account and the server-side
    NEXUS_ADMIN_TOKEN. This is intentionally separate from customer licensing.
    """
    from ..config import settings
    account = str(account_number or "").strip()
    if not account:
        raise AutoTradeError("account number is required")
    if not settings.nexus_admin_token or not admin_token or not hmac.compare_digest(str(admin_token), str(settings.nexus_admin_token)):
        raise AutoTradeError("admin authorization rejected")
    if settings.nexus_admin_mt5_accounts and account not in settings.nexus_admin_mt5_accounts:
        raise AutoTradeError("MT5 account is not allow-listed for admin mode")
    if not settings.nexus_admin_mt5_accounts:
        raise AutoTradeError("NEXUS_ADMIN_MT5_ACCOUNTS is not configured")
    uid = int(settings.admin_ids[0])
    # Fresh-database hardening: MT5 Admin is a system identity and must exist
    # before any receipt/notification row can satisfy the users FK.  Provision
    # the identity idempotently; this does not grant Telegram access to anyone
    # outside the configured admin allow-list.
    db.upsert_user(uid, "NEXUS_ADMIN", "NEXUS Admin")
    return {"telegram_id": uid, "license_id": 0, "license_status": "ADMIN",
            "mode": "ADMIN", "admin_authenticated": True, "account_verified": True,
            "allow_signal_receive": True, "allow_new_trade": True, "allow_manage_trade": True,
            "allow_advanced_settings": True, "allow_manual_signal": True, "allow_reports": True,
            "force_close_all": False, "expires_at": "", "account_number": account, "admin_mode": True}


def authorize_mt5(license_key: str, account_number: str, *, bind: bool = False,
                  broker: str | None = None, server: str | None = None, ea_version: str | None = None) -> dict[str, Any]:
    lic, status, allow_new, allow_manage = _license_state(license_key)
    uid = int(lic["telegram_id"])
    account_number = str(account_number).strip()
    if not account_number:
        raise AutoTradeError("account number is required")

    bound = db.mt5_account(uid)
    if bind and status == "ACTIVE":
        try:
            bound = db.bind_mt5_account(uid, account_number, broker, server, ea_version)
        except ValueError as exc:
            raise AutoTradeError(str(exc)) from exc
    elif bound:
        if str(bound["account_number"]) != account_number:
            raise AutoTradeError("MT5 account mismatch")
        if bound["server"] and server and str(bound["server"]).strip().lower() != str(server).strip().lower():
            raise AutoTradeError("MT5 broker server mismatch")
    else:
        raise AutoTradeError("MT5 account is not activated")

    if bound and status == "ACTIVE":
        db.touch_autotrade_session(uid, account_number, ea_version, "MT5")

    vip_access = bool(lic["vip_access"]) if "vip_access" in lic.keys() else False
    vip_expiry = lic["vip_expires_at"] if "vip_expires_at" in lic.keys() else None
    if vip_access and vip_expiry:
        try:
            vip_access = datetime.fromisoformat(str(vip_expiry)) > datetime.now(timezone.utc)
        except Exception:
            vip_access = False

    return {
        "telegram_id": uid,
        "license_id": int(lic["id"]),
        "license_status": status,
        "mode": "LICENSED" if status == "ACTIVE" else "LICENSED",
        "admin_authenticated": False,
        "account_verified": True,
        "allow_signal_receive": bool(allow_new),
        "allow_new_trade": allow_new,
        "allow_manage_trade": allow_manage,
        "allow_advanced_settings": status == "ACTIVE",
        "allow_manual_signal": False,
        "allow_reports": True,
        "vip_access": vip_access,
        "force_close_all": status == "EXPIRED_CLOSE",
        "expires_at": str(lic["expires_at"]),
        "account_number": account_number,
    }


def signal_to_payload(row) -> dict[str, Any]:
    targets = db.get_signal_targets(int(row["id"]))
    target_map = {int(t["target_no"]): float(t["price"]) for t in targets}
    cfg = None
    raw_cfg = row["trailing_config_json"] if "trailing_config_json" in row.keys() else None
    if raw_cfg:
        try:
            cfg = json.loads(raw_cfg)
        except Exception:
            cfg = None
    if cfg is None and row["trailing_code"]:
        try:
            cfg = profile_snapshot(str(row["trailing_code"]))
        except Exception:
            cfg = None
    return {
        "id": int(row["id"]),
        "signal_id": str(row["code"]),
        "market": str(row["market_type"]),
        "symbol": str(row["symbol"]),
        "timeframe": str(row["timeframe"] if "timeframe" in row.keys() and row["timeframe"] else "M5"),
        "direction": str(row["direction"]),
        "entry": float(row["entry_price"]),
        "sl": float(row["stop_loss"]),
        "tp1": target_map.get(1),
        "tp2": target_map.get(2),
        "tp3": target_map.get(3),
        "tp4": target_map.get(4),
        "tp5": target_map.get(5),
        "tp6": target_map.get(6),
        "tp7": target_map.get(7),
        "tp8": target_map.get(8),
        "tp9": target_map.get(9),
        "tp10": target_map.get(10),
        "targets": [target_map[k] for k in sorted(target_map)],
        "risk_percent": float(row["risk_percent"]),
        "volume_mode": str(row["volume_mode"] if "volume_mode" in row.keys() and row["volume_mode"] else "RISK").upper(),
        "lot_size": float(row["lot_size"]) if row["lot_size"] is not None else None,
        "leverage": float(row["leverage"]) if row["leverage"] is not None else None,
        "trailing_code": str(row["trailing_code"] or ""),
        "trailing_name": str(row["trailing_name"] or ""),
        "trailing_config": cfg,
        "max_entry_deviation_pct": float(row["max_entry_deviation_pct"]) if "max_entry_deviation_pct" in row.keys() and row["max_entry_deviation_pct"] is not None else None,
        "max_entry_deviation_abs": float(row["max_entry_deviation_abs"]) if "max_entry_deviation_abs" in row.keys() and row["max_entry_deviation_abs"] is not None else None,
        "order_type": str(row["order_type"] if "order_type" in row.keys() and row["order_type"] else "MARKET").upper(),
        "stop_limit_price": float(row["stop_limit_price"]) if "stop_limit_price" in row.keys() and row["stop_limit_price"] is not None else None,
        "limit_activated_at": str(row["limit_activated_at"]) if "limit_activated_at" in row.keys() and row["limit_activated_at"] else None,
        "status": str(row["status"]),
        "created_at": str(row["created_at"]),
        "destination": str(row["destination"] or "BOTH").upper(),
        "signal_uuid": str(row["signal_uuid"] or "") if "signal_uuid" in row.keys() else "",
        "revision": int(row["revision"] or 1) if "revision" in row.keys() else 1,
        "issuer_type": str(row["issuer_type"] or "") if "issuer_type" in row.keys() else "",
        "issuer_account": str(row["issuer_account"] or "") if "issuer_account" in row.keys() else "",
        "issued_at": str(row["issued_at"] or "") if "issued_at" in row.keys() else "",
    }


def _resolve_service_ea_auth(license_key: str, account_number: str) -> dict[str, Any]:
    """Resolve a licensed customer session; never silently fall back on bad credentials."""
    key = str(license_key or "").strip()
    account = str(account_number or "").strip()
    if not account:
        raise AutoTradeError("account number is required")
    if not key:
        raise AutoTradeError("Auto Trade license is required")
    return authorize_mt5(key, account, bind=False)


def signal_visible_to_auth(row, auth: dict[str, Any]) -> bool:
    """Apply the MT5 signal audience scope after authentication.

    FREE/BOTH are visible to every eligible AutoTrade client. VIP is visible
    only when the authenticated license currently carries active VIP access.
    The destination is therefore an access-control scope, not a Telegram route.
    """
    destination = str(row["destination"] or "BOTH").upper() if "destination" in row.keys() else "BOTH"
    if destination in {"FREE", "BOTH"}:
        return True
    if destination == "VIP":
        return bool(auth.get("vip_access", False))
    return False


def active_signals(license_key: str, account_number: str, *, after_id: int = 0, limit: int = 50) -> dict[str, Any]:
    # Use the same authorization resolver as the API layer so STANDARD/ADMIN
    # sessions do not become inconsistent between activation and polling.
    auth = _resolve_service_ea_auth(license_key, account_number)
    if not auth["allow_new_trade"]:
        return {"license_status": auth["license_status"], "signals": []}
    rows = db.autotrade_active_signals(after_id, limit)
    visible = [r for r in rows if signal_visible_to_auth(r, auth)]
    return {"license_status": auth["license_status"], "signals": [signal_to_payload(r) for r in visible]}


def pending_commands(license_key: str, account_number: str, *, after_id: int = 0, limit: int = 100) -> dict[str, Any]:
    auth = _resolve_service_ea_auth(license_key, account_number)
    if not auth["allow_manage_trade"]:
        return {"license_status": auth["license_status"], "commands": []}
    rows = db.autotrade_commands(after_id, limit)
    commands = []
    for row in rows:
        payload = None
        if row["payload_json"]:
            try:
                payload = json.loads(row["payload_json"])
            except Exception:
                payload = {"value": row["payload_json"]}
        sig = db.get_signal(int(row["signal_id"]))
        commands.append({
            "id": int(row["id"]),
            "signal_id": str(sig["code"]) if sig else str(row["signal_id"]),
            "signal_db_id": int(row["signal_id"]),
            "command": str(row["command"]),
            "payload": payload,
            "created_at": str(row["created_at"]),
        })
    return {"license_status": auth["license_status"], "commands": commands}
