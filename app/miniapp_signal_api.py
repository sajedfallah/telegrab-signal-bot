from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query

from . import db
from .miniapp_api import _auth_user
from .signals.contract import canonical_signal


router = APIRouter(prefix="/miniapp/api", tags=["NEXUS Mini App Signals"])


def _user_id(init_data: str | None) -> int:
    return int(_auth_user(init_data)["id"])


def _access(row: Any) -> str:
    destination = str(row["destination"] or "BOTH").upper()
    return "VIP" if destination == "VIP" else "FREE"


def _live(row: Any) -> dict[str, Any] | None:
    account = str(row["issuer_account"] or "") if "issuer_account" in row.keys() else ""
    code = str(row["code"] or "")
    if not account or not code or str(row["status"] or "").upper() == "CLOSED":
        return None
    with db.conn() as con:
        live = con.execute(
            "SELECT * FROM mt5_live_state WHERE account_number=? AND UPPER(COALESCE(signal_code,''))=UPPER(?) "
            "AND nexus_managed=1 AND UPPER(status) IN ('OPEN','PENDING') "
            "ORDER BY last_seen_at DESC LIMIT 1",
            (account, code),
        ).fetchone()
    if not live:
        return {"status": "UNAVAILABLE", "pnl_state": None, "age_seconds": None}
    age = None
    try:
        seen = datetime.fromisoformat(str(live["last_seen_at"]).replace("Z", "+00:00"))
        if seen.tzinfo is None:
            seen = seen.replace(tzinfo=timezone.utc)
        age = max(0.0, (datetime.now(timezone.utc) - seen.astimezone(timezone.utc)).total_seconds())
    except ValueError:
        pass
    fresh = age is not None and age <= 120
    profit = float(live["profit"] or 0)
    state = "PENDING" if str(live["status"]).upper() == "PENDING" and fresh else ("LIVE" if fresh else "STALE")
    return {
        "status": state,
        "current_price": float(live["current_price"]) if live["current_price"] else None,
        "floating_pnl": profit,
        "current_r": None,
        "volume": float(live["volume"]) if live["volume"] is not None else None,
        "stop_loss": float(live["stop_loss"]) if live["stop_loss"] else None,
        "take_profit": float(live["take_profit"]) if live["take_profit"] else None,
        "pnl_state": "IN_PROFIT" if profit > 0 else "IN_LOSS" if profit < 0 else "BE",
        "last_sync": str(live["last_seen_at"]),
        "age_seconds": round(age, 1) if age is not None else None,
    }


def _result(row: Any) -> str | None:
    if str(row["status"] or "").upper() != "CLOSED":
        return None
    value = row["result_value"]
    if value is None:
        return "UNKNOWN"
    number = float(value)
    return "WIN" if number > 0 else "LOSS" if number < 0 else "BE"


def _serialize(row: Any, uid: int, *, detail: bool = False) -> dict[str, Any]:
    targets = db.get_signal_targets(int(row["id"]))
    contract = canonical_signal(row, targets)
    access = _access(row)
    locked = access == "VIP" and not db.has_entitlement(uid, "vip") and str(row["status"] or "").upper() != "CLOSED"
    item = {
        "id": contract["signal_id"],
        "signal_id": contract["signal_id"],
        "code": contract["code"],
        "symbol": contract["symbol"],
        "direction": contract["direction"],
        "timeframe": contract["timeframe"],
        "order_type": contract["order_type"],
        "entry_price": None if locked else contract["entry_price"],
        "stop_loss": None if locked else contract["stop_loss"],
        "targets": [] if locked else contract["take_profit_levels"],
        "risk_percent": None if locked else contract["risk_percent"],
        "volume": None if locked else contract["volume"],
        "trailing_code": None if locked else contract["trailing_code"],
        "status": contract["status"],
        "lifecycle_state": contract["lifecycle_state"],
        "access": access,
        "locked": locked,
        "published_at": contract["opened_at"] or contract["created_at"],
        "closed_at": contract["closed_at"],
        "exit_price": None if locked else contract["exit_price"],
        "realized_pnl": None,
        "result": _result(row),
        "result_label_fa": None,
        "live": None if locked else _live(row),
    }
    if detail:
        with db.conn() as con:
            updates = con.execute(
                "SELECT action,detail_fa,detail_en,value,created_at FROM signal_updates "
                "WHERE signal_id=? ORDER BY id ASC",
                (int(row["id"]),),
            ).fetchall()
        item["timeline"] = [dict(update) for update in updates]
        item["my_execution"] = None
        item["source"] = contract["source"]
    return item


@router.get("/signals")
def list_signals(
    state: str = Query(default="ACTIVE", pattern="^(?:ACTIVE|CLOSED)$"),
    access: str = Query(default="ALL", pattern="^(?:ALL|FREE|VIP)$"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
):
    uid = _user_id(x_telegram_init_data)
    where = ["status='CLOSED'" if state == "CLOSED" else "status<>'CLOSED'"]
    params: list[Any] = []
    if access == "VIP":
        where.append("destination='VIP'")
    elif access == "FREE":
        where.append("destination IN ('FREE','BOTH')")
    sql = "SELECT * FROM signals WHERE " + " AND ".join(where) + " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    with db.conn() as con:
        rows = con.execute(sql, tuple(params)).fetchall()
    return {"ok": True, "items": [_serialize(row, uid) for row in rows]}


@router.get("/signals/closed-calendar")
def closed_calendar(
    month: str,
    access: str = Query(default="ALL", pattern="^(?:ALL|FREE|VIP)$"),
    day: str | None = None,
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
):
    uid = _user_id(x_telegram_init_data)
    where = ["status='CLOSED'", "substr(COALESCE(closed_at,created_at),1,7)=?"]
    params: list[Any] = [month]
    if access == "VIP":
        where.append("destination='VIP'")
    elif access == "FREE":
        where.append("destination IN ('FREE','BOTH')")
    with db.conn() as con:
        rows = con.execute(
            "SELECT * FROM signals WHERE " + " AND ".join(where) + " ORDER BY closed_at ASC,id ASC",
            tuple(params),
        ).fetchall()
    days: dict[str, int] = {}
    for row in rows:
        date_key = str(row["closed_at"] or row["created_at"])[:10]
        days[date_key] = days.get(date_key, 0) + 1
    selected = [row for row in rows if day and str(row["closed_at"] or row["created_at"])[:10] == day]
    return {
        "ok": True, "month": month, "day": day,
        "days": [{"day": key, "count": value, "net_pnl": None} for key, value in sorted(days.items())],
        "items": [_serialize(row, uid) for row in selected],
    }


@router.get("/signals/{signal_id}")
def signal_detail(
    signal_id: int,
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
):
    uid = _user_id(x_telegram_init_data)
    row = db.get_signal(signal_id)
    if not row:
        raise HTTPException(status_code=404, detail="signal not found")
    if _access(row) == "VIP" and not db.has_entitlement(uid, "vip") and str(row["status"] or "").upper() != "CLOSED":
        raise HTTPException(status_code=403, detail="VIP access required")
    return _serialize(row, uid, detail=True)
