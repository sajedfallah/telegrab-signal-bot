from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query

from . import db
from .miniapp_api import _auth_user, _entitlements

router = APIRouter(prefix="/miniapp/api", tags=["NEXUS Mini App Signals"])

PUBLIC_CLOSED_VIP_DETAILS = os.getenv("MINIAPP_PUBLIC_CLOSED_VIP_DETAILS", "false").strip().lower() in {"1", "true", "yes", "on"}
CUSTOMER_INACTIVE_STATUSES = {"DRAFT", "REJECTED", "CANCELLED", "EXPIRED", "PUBLISH_FAILED"}
ACTIVE_TRUTH_STALE_SECONDS = max(120, min(int(os.getenv("MINIAPP_ACTIVE_TRUTH_STALE_SECONDS", "600")), 3600))


def _access_class(row: dict[str, Any]) -> str:
    return "VIP" if str(row.get("destination") or "FREE").upper() == "VIP" else "FREE"


def _result_meta(row: dict[str, Any]) -> dict[str, Any]:
    status = str(row.get("status") or "").upper()
    if status != "CLOSED":
        return {"result": None, "result_value": None, "result_unit": None, "result_label_fa": None}

    raw = row.get("result_value")
    unit = str(row.get("result_unit") or "").strip().upper()
    reason = str(row.get("close_reason") or "").strip().upper()
    if raw is None:
        if reason in {"CANCELLED", "CANCELED"}:
            return {"result": "CANCELLED", "result_value": None, "result_unit": unit or None, "result_label_fa": "لغوشده"}
        if reason == "EXPIRED":
            return {"result": "EXPIRED", "result_value": None, "result_unit": unit or None, "result_label_fa": "منقضی‌شده"}
        if reason in {"PARTIAL", "PARTIAL_CLOSE"}:
            return {"result": "PARTIAL", "result_value": None, "result_unit": unit or None, "result_label_fa": "بسته‌شدن بخشی"}
        return {"result": "UNKNOWN", "result_value": None, "result_unit": unit or None, "result_label_fa": "نتیجه ثبت نشده"}
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return {"result": "UNKNOWN", "result_value": None, "result_unit": unit or None, "result_label_fa": "نتیجه ثبت نشده"}

    suffix = f" {unit}" if unit else ""
    if value > 0:
        result, label = "WIN", f"سود +{value:g}{suffix}"
    elif value < 0:
        result, label = "LOSS", f"ضرر {value:g}{suffix}"
    else:
        result, label = "BE", f"سر‌به‌سر 0{suffix}"
    return {"result": result, "result_value": value, "result_unit": unit or None, "result_label_fa": label}


def _result(row: dict[str, Any]) -> str | None:
    return _result_meta(row)["result"]


def _targets(signal_id: int) -> list[dict[str, Any]]:
    return [dict(row) for row in db.get_signal_targets(signal_id)]


def _customer_visible_status(status: Any) -> bool:
    key = str(status or "").strip().upper()
    return key == "CLOSED" or (bool(key) and key not in CUSTOMER_INACTIVE_STATUSES)


def _live_cutoff() -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=ACTIVE_TRUTH_STALE_SECONDS)).isoformat()


def _active_truth_clause(state: str) -> tuple[str, tuple[Any, ...]]:
    if str(state or "").upper() != "ACTIVE":
        return "1=1", ()
    # MT5-admin signals are customer-visible as ACTIVE only while the broker
    # snapshot proves an OPEN/PENDING NEXUS-managed position/order. Matching by
    # execution ticket also covers brokers that clear the position comment.
    return """
        (
          UPPER(COALESCE(signals.issuer_type,'')) <> 'MT5_ADMIN'
          OR EXISTS (
            SELECT 1
            FROM mt5_live_state live
            WHERE live.account_number = signals.issuer_account
              AND live.nexus_managed = 1
              AND UPPER(COALESCE(live.status,'')) IN ('OPEN','PENDING')
              AND live.last_seen_at >= ?
              AND (
                UPPER(COALESCE(live.signal_code,'')) = UPPER(COALESCE(signals.code,''))
                OR EXISTS (
                  SELECT 1 FROM autotrade_trade_executions exec
                  WHERE exec.signal_id = signals.id
                    AND exec.ticket = live.ticket
                )
              )
          )
        )
    """, (_live_cutoff(),)


def _mt5_admin_is_live(data: dict[str, Any]) -> bool:
    if str(data.get("issuer_type") or "").upper() != "MT5_ADMIN":
        return True
    with db.conn() as con:
        row = con.execute(
            """
            SELECT 1
            FROM mt5_live_state live
            WHERE live.account_number=?
              AND live.nexus_managed=1
              AND UPPER(COALESCE(live.status,'')) IN ('OPEN','PENDING')
              AND live.last_seen_at>=?
              AND (
                UPPER(COALESCE(live.signal_code,''))=UPPER(COALESCE(?,''))
                OR EXISTS (
                  SELECT 1 FROM autotrade_trade_executions exec
                  WHERE exec.signal_id=? AND exec.ticket=live.ticket
                )
              )
            LIMIT 1
            """,
            (str(data.get("issuer_account") or ""), _live_cutoff(), str(data.get("code") or ""), int(data["id"])),
        ).fetchone()
    return row is not None


def _snapshot_age_seconds(value: Any) -> float | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds())
    except (TypeError, ValueError):
        return None


def _live_signal_state(data: dict[str, Any]) -> dict[str, Any] | None:
    """Return broker-reported, read-only live state for one NEXUS signal.

    Floating PnL is never reconstructed from price. It is the MT5-reported
    `profit` from the authoritative live snapshot. Original signal Entry/SL are
    used only to express current price displacement as an informational R value.
    """
    if str(data.get("status") or "").upper() == "CLOSED":
        return None
    account = str(data.get("issuer_account") or "").strip()
    code = str(data.get("code") or "").strip()
    signal_id = int(data["id"])
    if not account or not code:
        return {"status": "UNAVAILABLE", "pnl_state": None, "last_sync": None, "age_seconds": None}

    with db.conn() as con:
        rows = [dict(row) for row in con.execute(
            """
            SELECT live.*
            FROM mt5_live_state live
            WHERE live.account_number=?
              AND live.nexus_managed=1
              AND UPPER(COALESCE(live.status,'')) IN ('OPEN','PENDING')
              AND (
                UPPER(COALESCE(live.signal_code,''))=UPPER(?)
                OR EXISTS (
                  SELECT 1 FROM autotrade_trade_executions exec
                  WHERE exec.signal_id=? AND exec.ticket=live.ticket
                )
              )
            ORDER BY live.last_seen_at DESC, live.ticket DESC
            """,
            (account, code, signal_id),
        ).fetchall()]

    if not rows:
        return {"status": "UNAVAILABLE", "pnl_state": None, "last_sync": None, "age_seconds": None}

    last_sync = max((str(row.get("last_seen_at") or "") for row in rows), default="") or None
    age_seconds = _snapshot_age_seconds(last_sync)
    fresh = age_seconds is not None and age_seconds <= ACTIVE_TRUTH_STALE_SECONDS
    positions = [row for row in rows if str(row.get("state_type") or "").upper() == "POSITION" and str(row.get("status") or "").upper() == "OPEN"]
    pending = [row for row in rows if str(row.get("state_type") or "").upper() == "ORDER" and str(row.get("status") or "").upper() == "PENDING"]

    if positions:
        latest = max(positions, key=lambda row: str(row.get("last_seen_at") or ""))
        floating_pnl = sum(float(row.get("profit") or 0.0) for row in positions)
        volume = sum(float(row.get("volume") or 0.0) for row in positions)
        current_price = float(latest.get("current_price") or 0.0) or None
        entry = float(data.get("entry_price") or 0.0)
        original_sl = float(data.get("stop_loss") or 0.0)
        current_r = None
        initial_r = abs(entry - original_sl)
        if current_price is not None and entry > 0 and initial_r > 0:
            direction = str(data.get("direction") or "").upper()
            displacement = current_price - entry if direction in {"BUY", "LONG"} else entry - current_price
            current_r = round(displacement / initial_r, 4)
        pnl_state = "IN_PROFIT" if floating_pnl > 0 else "IN_LOSS" if floating_pnl < 0 else "BE"
        return {
            "status": "LIVE" if fresh else "STALE",
            "current_price": current_price,
            "floating_pnl": round(floating_pnl, 2),
            "current_r": current_r,
            "volume": volume,
            "stop_loss": float(latest.get("stop_loss") or 0.0) or None,
            "take_profit": float(latest.get("take_profit") or 0.0) or None,
            "pnl_state": pnl_state,
            "last_sync": last_sync,
            "age_seconds": round(age_seconds, 1) if age_seconds is not None else None,
            "position_count": len(positions),
        }

    if pending:
        latest = max(pending, key=lambda row: str(row.get("last_seen_at") or ""))
        return {
            "status": "PENDING" if fresh else "STALE",
            "current_price": float(latest.get("current_price") or 0.0) or None,
            "floating_pnl": 0.0,
            "current_r": None,
            "volume": sum(float(row.get("volume") or 0.0) for row in pending),
            "stop_loss": float(latest.get("stop_loss") or 0.0) or None,
            "take_profit": float(latest.get("take_profit") or 0.0) or None,
            "pnl_state": "BE",
            "last_sync": last_sync,
            "age_seconds": round(age_seconds, 1) if age_seconds is not None else None,
            "position_count": 0,
        }

    return {"status": "UNAVAILABLE", "pnl_state": None, "last_sync": last_sync, "age_seconds": age_seconds}


def serialize_signal(row: Any, *, has_vip: bool, include_timeline: bool = False) -> dict[str, Any]:
    data = dict(row)
    access = _access_class(data)
    closed = str(data.get("status") or "").upper() == "CLOSED"
    vip_authorized = access != "VIP" or has_vip
    full_details = vip_authorized or (closed and PUBLIC_CLOSED_VIP_DETAILS)
    result_meta = _result_meta(data)

    result = {
        "id": int(data["id"]),
        "code": str(data.get("code") or ""),
        "symbol": str(data.get("symbol") or "—"),
        "access": access,
        "status": str(data.get("status") or "").upper(),
        "published_at": data.get("created_at"),
        "closed_at": data.get("closed_at"),
        "close_reason": data.get("close_reason"),
        "locked": bool(access == "VIP" and not has_vip and not closed),
        **result_meta,
    }

    if closed and access == "VIP" and not has_vip and not PUBLIC_CLOSED_VIP_DETAILS:
        result.update({"direction": str(data.get("direction") or "")})
        return result

    if not full_details:
        return result

    result.update({
        "market_type": data.get("market_type"),
        "timeframe": data.get("timeframe"),
        "direction": str(data.get("direction") or ""),
        "order_type": data.get("order_type"),
        "entry_price": data.get("entry_price"),
        "stop_loss": data.get("stop_loss"),
        "targets": _targets(int(data["id"])),
        "risk_percent": data.get("risk_percent"),
        "rr_ratio": data.get("rr_ratio"),
        "live": _live_signal_state(data),
    })
    if include_timeline:
        result["timeline"] = [
            {
                "action": str(item.get("action") or ""),
                "detail_fa": str(item.get("detail_fa") or ""),
                "detail_en": str(item.get("detail_en") or ""),
                "value": item.get("value"),
                "created_at": item.get("created_at"),
            }
            for item in (dict(row) for row in db.signal_updates(int(data["id"])))
        ]
    return result


def _execution_timeline(uid: int, signal_id: int) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    with db.conn() as con:
        receipt = con.execute(
            """
            SELECT status,first_seen_at,executed_at,ticket,error_text
            FROM autotrade_signal_receipts
            WHERE telegram_id=? AND signal_id=? AND platform='MT5' LIMIT 1
            """,
            (uid, signal_id),
        ).fetchone()
        if receipt is not None:
            data = dict(receipt)
            if data.get("first_seen_at"):
                items.append({"kind": "EA_RECEIVED", "label_fa": "EA سیگنال را دریافت کرد", "created_at": data.get("first_seen_at")})
            if data.get("executed_at"):
                items.append({"kind": "BROKER_EXECUTED", "label_fa": "سفارش در بروکر اجرا شد", "created_at": data.get("executed_at"), "ticket": data.get("ticket")})
            if data.get("error_text"):
                items.append({"kind": "EXECUTION_ERROR", "label_fa": "اجرا ناموفق بود", "created_at": data.get("executed_at") or data.get("first_seen_at"), "reason": str(data.get("error_text"))})
        rows = con.execute(
            """
            SELECT event_type,status,ticket,profit,error_text,created_at
            FROM autotrade_trade_executions
            WHERE telegram_id=? AND signal_id=?
            ORDER BY id ASC
            """,
            (uid, signal_id),
        ).fetchall()
    for row in rows:
        data = dict(row)
        items.append({
            "kind": str(data.get("event_type") or data.get("status") or "EXECUTION"),
            "label_fa": str(data.get("event_type") or data.get("status") or "رویداد اجرا"),
            "created_at": data.get("created_at"),
            "ticket": data.get("ticket"),
            "profit": data.get("profit"),
            "reason": data.get("error_text"),
        })
    items.sort(key=lambda item: str(item.get("created_at") or ""))
    return items


def _my_execution(uid: int, signal_id: int, *, autotrade: bool) -> dict[str, Any] | None:
    if not autotrade:
        return None
    with db.conn() as con:
        row = con.execute(
            """
            SELECT id,ticket,event_type,symbol,direction,volume,entry_price,exit_price,profit,status,error_text,created_at
            FROM autotrade_trade_executions
            WHERE telegram_id=? AND signal_id=?
            ORDER BY id DESC LIMIT 1
            """,
            (uid, signal_id),
        ).fetchone()
        receipt = con.execute(
            """
            SELECT status,first_seen_at,executed_at,ticket,error_text
            FROM autotrade_signal_receipts
            WHERE telegram_id=? AND signal_id=? AND platform='MT5' LIMIT 1
            """,
            (uid, signal_id),
        ).fetchone()
    timeline = _execution_timeline(uid, signal_id)
    if row is not None:
        data = dict(row)
        data.update({"execution_state": "EXECUTED", "reason_fa": data.get("error_text"), "timeline": timeline})
        return data
    if receipt is not None:
        data = dict(receipt)
        status = str(data.get("status") or "SEEN").upper()
        failed = bool(data.get("error_text")) or status in {"ERROR", "FAILED", "REJECTED", "BLOCKED"}
        return {
            "ticket": data.get("ticket"),
            "status": status,
            "execution_state": "NOT_EXECUTED" if failed else "RECEIVED",
            "reason_fa": str(data.get("error_text") or "") or None,
            "first_seen_at": data.get("first_seen_at"),
            "executed_at": data.get("executed_at"),
            "timeline": timeline,
        }
    return {
        "ticket": None,
        "status": "NO_RECEIPT",
        "execution_state": "NOT_RECEIVED",
        "reason_fa": "برای این حساب، رسید دریافت سیگنال از EA ثبت نشده است.",
        "timeline": timeline,
    }


def _state_clause(state: str) -> tuple[str, tuple[Any, ...]]:
    key = state.upper()
    if key == "ACTIVE":
        return "UPPER(COALESCE(status,'')) NOT IN ('DRAFT','CLOSED','REJECTED','CANCELLED','EXPIRED','PUBLISH_FAILED')", ()
    if key == "CLOSED":
        return "UPPER(COALESCE(status,''))='CLOSED'", ()
    raise HTTPException(status_code=400, detail="unsupported signal state")


def _access_clause(access: str) -> tuple[str, tuple[Any, ...]]:
    key = access.upper()
    if key == "ALL":
        return "1=1", ()
    if key == "FREE":
        return "UPPER(COALESCE(destination,'FREE')) IN ('FREE','BOTH')", ()
    if key == "VIP":
        return "UPPER(COALESCE(destination,'FREE')) IN ('VIP','BOTH')", ()
    raise HTTPException(status_code=400, detail="unsupported signal access filter")


@router.get("/signals")
def signals(
    state: str = Query(default="ACTIVE"),
    access: str = Query(default="ALL"),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0, le=5000),
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    uid = int(_auth_user(x_telegram_init_data)["id"])
    ent = _entitlements(uid)
    has_vip = bool(ent.get("vip"))
    state_key = state.upper()
    access_key = access.upper()
    state_sql, state_args = _state_clause(state_key)
    access_sql, access_args = _access_clause(access_key)
    truth_sql, truth_args = _active_truth_clause(state_key)

    if state_key == "ACTIVE" and not has_vip:
        visibility_sql = "UPPER(COALESCE(destination,'FREE')) <> 'VIP'"
    else:
        visibility_sql = "1=1"

    cycle = db.current_cycle_id()
    params = (*state_args, *access_args, *truth_args, cycle, cycle, limit, offset)
    with db.conn() as con:
        rows = con.execute(
            f"""
            SELECT * FROM signals
            WHERE {state_sql} AND {access_sql} AND {visibility_sql} AND {truth_sql}
              AND COALESCE(cycle_id, ?) = ?
            ORDER BY id DESC LIMIT ? OFFSET ?
            """,
            params,
        ).fetchall()
    return {
        "state": state_key,
        "access": access_key,
        "limit": limit,
        "offset": offset,
        "items": [serialize_signal(row, has_vip=has_vip) for row in rows],
    }


@router.get("/signals/{signal_id}")
def signal_detail(
    signal_id: int,
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    uid = int(_auth_user(x_telegram_init_data)["id"])
    ent = _entitlements(uid)
    has_vip = bool(ent.get("vip"))
    row = db.get_signal(signal_id)
    if row is None or str(row["cycle_id"] or db.current_cycle_id()) != db.current_cycle_id():
        raise HTTPException(status_code=404, detail="signal not found")
    data = dict(row)
    if not _customer_visible_status(data.get("status")):
        raise HTTPException(status_code=404, detail="signal not found")
    if str(data.get("status") or "").upper() != "CLOSED" and not _mt5_admin_is_live(data):
        raise HTTPException(status_code=404, detail="signal is no longer active")
    if _access_class(data) == "VIP" and str(data.get("status") or "").upper() != "CLOSED" and not has_vip:
        raise HTTPException(status_code=403, detail="VIP access required")
    item = serialize_signal(row, has_vip=has_vip, include_timeline=True)
    item["my_execution"] = _my_execution(uid, signal_id, autotrade=bool(ent.get("autotrade")))
    return item