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
    if str(row.get("status") or "").upper() != "CLOSED":
        return {"result": None, "result_value": None, "result_unit": None, "result_label_fa": None}

    raw = row.get("result_value")
    unit = str(row.get("result_unit") or "").strip().upper()
    if raw is None:
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


def _my_execution(uid: int, signal_id: int, *, autotrade: bool) -> dict[str, Any] | None:
    if not autotrade:
        return None
    with db.conn() as con:
        row = con.execute(
            """
            SELECT id,ticket,event_type,symbol,direction,volume,entry_price,exit_price,profit,status,created_at
            FROM autotrade_trade_executions
            WHERE telegram_id=? AND signal_id=?
            ORDER BY id DESC LIMIT 1
            """,
            (uid, signal_id),
        ).fetchone()
    return dict(row) if row is not None else None


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
