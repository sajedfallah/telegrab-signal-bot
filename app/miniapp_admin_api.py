from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from . import db
from .config import settings
from .miniapp_api import _auth_user
from .autotrade.service import signal_to_payload
from .autotrade.symbol_registry import normalize_symbol
from .autotrade.trailing_profiles import TRAILING_PROFILES, profile_snapshot


router = APIRouter(prefix="/miniapp/api/admin", tags=["NEXUS Admin Mini App"])
RR_MULTIPLIERS = (1.0, 1.5, 2.0, 3.0)
VALID_COMMANDS = {
    "MOVE_SL_TO_ENTRY", "CLOSE_SIGNAL", "CANCEL_PENDING", "UPDATE_SL",
    "UPDATE_TP", "ACTIVATE_TRAILING", "PARTIAL_CLOSE",
}


def _admin(init_data: str | None) -> dict[str, Any]:
    user = _auth_user(init_data)
    if int(user["id"]) not in settings.admin_ids:
        raise HTTPException(status_code=403, detail="NEXUS administrator access is required")
    return user


def _admin_account() -> str | None:
    configured = tuple(str(value).strip() for value in settings.nexus_admin_mt5_accounts if str(value).strip())
    with db.conn() as con:
        if configured:
            marks = ",".join("?" for _ in configured)
            row = con.execute(
                f"SELECT account_number FROM mt5_heartbeats_v060 "
                f"WHERE role='ADMIN' AND account_number IN ({marks}) "
                f"ORDER BY last_seen_at DESC LIMIT 1",
                configured,
            ).fetchone()
            if row:
                return str(row["account_number"])
            return configured[0]
        row = con.execute(
            "SELECT account_number FROM mt5_heartbeats_v060 "
            "WHERE role='ADMIN' ORDER BY last_seen_at DESC LIMIT 1"
        ).fetchone()
        return str(row["account_number"]) if row else None


def _admin_mt5_status() -> dict[str, Any]:
    account = _admin_account()
    if not account:
        return {"online": False, "status": "OFFLINE", "account_number": None, "last_seen_at": None, "age_seconds": None}
    with db.conn() as con:
        row = con.execute(
            "SELECT account_number,ea_version,last_seen_at FROM mt5_heartbeats_v060 "
            "WHERE role='ADMIN' AND account_number=? LIMIT 1",
            (account,),
        ).fetchone()
    if not row:
        return {"online": False, "status": "OFFLINE", "account_number": account, "last_seen_at": None, "age_seconds": None}
    age = None
    try:
        seen = datetime.fromisoformat(str(row["last_seen_at"]).replace("Z", "+00:00"))
        if seen.tzinfo is None:
            seen = seen.replace(tzinfo=timezone.utc)
        age = max(0.0, (datetime.now(timezone.utc) - seen.astimezone(timezone.utc)).total_seconds())
    except ValueError:
        pass
    online = age is not None and age <= 120
    return {
        "online": online,
        "status": "ONLINE" if online else "OFFLINE",
        "account_number": account,
        "ea_version": str(row["ea_version"] or ""),
        "last_seen_at": str(row["last_seen_at"]),
        "age_seconds": round(age, 1) if age is not None else None,
    }


def _live_for_signal(row: Any) -> dict[str, Any] | None:
    account = str(row["issuer_account"] or "") if "issuer_account" in row.keys() else ""
    code = str(row["code"] or "")
    if not account or not code:
        return None
    with db.conn() as con:
        live = con.execute(
            "SELECT * FROM mt5_live_state WHERE account_number=? AND UPPER(COALESCE(signal_code,''))=UPPER(?) "
            "AND nexus_managed=1 AND UPPER(status) IN ('OPEN','PENDING') "
            "ORDER BY last_seen_at DESC LIMIT 1",
            (account, code),
        ).fetchone()
    if not live:
        return None
    age = None
    try:
        seen = datetime.fromisoformat(str(live["last_seen_at"]).replace("Z", "+00:00"))
        if seen.tzinfo is None:
            seen = seen.replace(tzinfo=timezone.utc)
        age = max(0.0, (datetime.now(timezone.utc) - seen.astimezone(timezone.utc)).total_seconds())
    except ValueError:
        pass
    freshness = "LIVE" if age is not None and age <= 120 else "STALE"
    profit = float(live["profit"] or 0)
    return {
        "status": "PENDING" if str(live["status"]).upper() == "PENDING" and freshness == "LIVE" else freshness,
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


class CalculateRequest(BaseModel):
    symbol: str = Field(min_length=3, max_length=32)
    direction: str = Field(pattern="^(?:BUY|SELL)$")
    entry: float = Field(gt=0)
    stop_loss: float = Field(gt=0)


class CreateSignalRequest(CalculateRequest):
    targets: list[float] = Field(min_length=1, max_length=10)
    destination: str = Field(default="BOTH", pattern="^(?:FREE|VIP|BOTH)$")
    request_id: str = Field(min_length=8, max_length=160)
    timeframe: str = Field(default="M5", pattern="^(?:M1|M3|M5|M15|M30|H1|H4|D1|W1)$")
    setup_mode: str = Field(default="MANUAL", pattern="^(?:MANUAL|AUTO)$")
    trailing_code: str | None = Field(default=None, max_length=64)
    volume_mode: str = Field(default="RISK", pattern="^(?:RISK|FIXED)$")
    lot_size: float | None = Field(default=None, gt=0)
    risk_percent: float | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def validate_contract(self):
        if self.setup_mode != "MANUAL":
            raise ValueError("AUTO setup has no authoritative structure feed and is fail-closed")
        if self.volume_mode == "FIXED" and self.lot_size is None:
            raise ValueError("lot_size is required for FIXED volume")
        if self.volume_mode == "RISK" and self.risk_percent is None:
            raise ValueError("risk_percent is required for RISK volume")
        return self


class PositionCommandRequest(BaseModel):
    command: str
    account_number: str = Field(min_length=1, max_length=64)
    value: str | None = Field(default=None, max_length=128)


def _calculate(req: CalculateRequest) -> dict[str, Any]:
    symbol = normalize_symbol(req.symbol)
    direction = req.direction.upper()
    entry = float(req.entry)
    stop = float(req.stop_loss)
    if direction == "BUY" and stop >= entry:
        raise HTTPException(status_code=422, detail="BUY stop-loss must be below entry")
    if direction == "SELL" and stop <= entry:
        raise HTTPException(status_code=422, detail="SELL stop-loss must be above entry")
    risk = abs(entry - stop)
    if not math.isfinite(risk) or risk <= 0:
        raise HTTPException(status_code=422, detail="entry and stop-loss must create finite non-zero risk")
    sign = 1 if direction == "BUY" else -1
    targets = [entry + sign * risk * multiple for multiple in RR_MULTIPLIERS]
    return {
        "symbol": symbol, "direction": direction, "entry": entry, "stop_loss": stop,
        "risk": risk, "digits": None, "targets": targets, "target_multipliers": list(RR_MULTIPLIERS),
    }


@router.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "service": "nexus-miniapp-admin"}


@router.get("/bootstrap")
def bootstrap(x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data")):
    user = _admin(x_telegram_init_data)
    return {
        "ok": True, "user": user, "mt5_admin": _admin_mt5_status(),
        "destinations": ["FREE", "VIP", "BOTH"],
        "timeframes": ["M1", "M3", "M5", "M15", "M30", "H1", "H4", "D1", "W1"],
        "trailing_profiles": [{"code": code, "name": value.get("name", code)} for code, value in TRAILING_PROFILES.items()],
    }


@router.post("/signals/calculate")
def calculate(req: CalculateRequest, x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data")):
    _admin(x_telegram_init_data)
    return _calculate(req)


@router.get("/market-quote")
def market_quote(symbol: str = Query(min_length=3, max_length=32), x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data")):
    _admin(x_telegram_init_data)
    raise HTTPException(status_code=503, detail="authoritative MT5 bid/ask quote feed is not available through this backend")


@router.post("/signals", status_code=201)
def create_signal(req: CreateSignalRequest, x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data")):
    user = _admin(x_telegram_init_data)
    account = _admin_account()
    if not account:
        raise HTTPException(status_code=503, detail="no Admin MT5 account is configured")
    trailing = str(req.trailing_code or "").strip().upper() or None
    trailing_cfg = None
    if trailing:
        if trailing not in TRAILING_PROFILES:
            raise HTTPException(status_code=422, detail="unknown trailing profile")
        trailing_cfg = profile_snapshot(trailing)
    try:
        row = db.issue_mt5_admin_signal(
            market_type="GOLD" if normalize_symbol(req.symbol).startswith("XAU") else "FOREX",
            symbol=normalize_symbol(req.symbol), direction=req.direction, entry_price=req.entry,
            stop_loss=req.stop_loss, targets=[float(value) for value in req.targets],
            risk_percent=float(req.risk_percent or 0), rr_ratio=None, order_type="MARKET",
            volume_mode=req.volume_mode, lot_size=req.lot_size,
            trailing_code=trailing, trailing_config=trailing_cfg,
            timeframe=req.timeframe, destination=req.destination, admin_account=account,
            admin_id=int(user["id"]), request_id=req.request_id, signal_code=req.request_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    mt5 = _admin_mt5_status()
    payload = signal_to_payload(row)
    return {
        "ok": True, "request_id": req.request_id, "signal_id": int(row["id"]),
        "status": "READY" if mt5["online"] else "WAITING_FOR_MT5",
        "idempotent": str(row["publish_token"] or "") == req.request_id and str(row["created_at"]) != "",
        "signal": dict(row), "payload": payload, "targets": [float(v) for v in req.targets],
        "mt5_admin": mt5,
    }


def _signal_item(row: Any) -> dict[str, Any]:
    payload = signal_to_payload(row)
    return {
        "request_id": str(row["publish_token"] or row["code"]),
        "status": "PUBLISHED" if row["free_message_id"] or row["vip_message_id"] else ("WAITING_FOR_MT5" if not _admin_mt5_status()["online"] else "READY"),
        "payload_json": json.dumps({
            "symbol": row["symbol"], "direction": row["direction"], "entry": row["entry_price"],
            "stop_loss": row["stop_loss"], "destination": row["destination"],
        }, ensure_ascii=False),
        "signal": dict(row),
        "targets": payload["targets"],
        "live": _live_for_signal(row),
        "error_message": None,
        "chart_job": None,
    }


@router.get("/signals")
def signals(x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data")):
    _admin(x_telegram_init_data)
    with db.conn() as con:
        rows = con.execute(
            "SELECT * FROM signals WHERE issuer_type='MT5_ADMIN' ORDER BY id DESC LIMIT 100"
        ).fetchall()
    return {"ok": True, "mt5_admin": _admin_mt5_status(), "items": [_signal_item(row) for row in rows]}


@router.get("/active-signals")
def active_signals(x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data")):
    _admin(x_telegram_init_data)
    rows = [row for row in db.list_active_signals(100) if str(row["issuer_type"] or "").upper() == "MT5_ADMIN"]
    return {"ok": True, "items": [_signal_item(row) for row in rows]}


@router.get("/rejected-logs")
def rejected_logs(x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data")):
    _admin(x_telegram_init_data)
    return {"ok": True, "items": []}


@router.delete("/rejected-logs")
def clear_rejected_logs(x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data")):
    _admin(x_telegram_init_data)
    return {"ok": True, "deleted": 0}


@router.get("/positions")
def positions(x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data")):
    _admin(x_telegram_init_data)
    mt5 = _admin_mt5_status()
    account = mt5.get("account_number")
    if not account:
        return {"ok": True, "mt5_admin": mt5, "positions": [], "orders": []}
    with db.conn() as con:
        rows = con.execute(
            "SELECT * FROM mt5_live_state WHERE account_number=? AND nexus_managed=1 "
            "AND UPPER(status) IN ('OPEN','PENDING') ORDER BY last_seen_at DESC",
            (account,),
        ).fetchall()
    open_rows, pending_rows = [], []
    for raw in rows:
        item = dict(raw)
        signal = db.get_signal_by_code(str(item.get("signal_code") or "")) if item.get("signal_code") else None
        item["signal_id"] = int(signal["id"]) if signal else None
        item["signal_code"] = str(signal["code"]) if signal else item.get("signal_code")
        if str(item.get("state_type") or "").upper() == "ORDER" or str(item.get("status") or "").upper() == "PENDING":
            pending_rows.append(item)
        else:
            open_rows.append(item)
    return {"ok": True, "mt5_admin": mt5, "positions": open_rows, "orders": pending_rows}


@router.post("/signals/{signal_id}/command")
def command(signal_id: int, req: PositionCommandRequest, x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data")):
    user = _admin(x_telegram_init_data)
    command_name = str(req.command or "").strip().upper()
    if command_name not in VALID_COMMANDS:
        raise HTTPException(status_code=422, detail="unsupported command")
    row = db.get_signal(signal_id)
    if not row or str(row["issuer_type"] or "").upper() != "MT5_ADMIN":
        raise HTTPException(status_code=404, detail="managed signal not found")
    if str(row["issuer_account"] or "") != str(req.account_number):
        raise HTTPException(status_code=409, detail="signal account does not match active Admin MT5 account")
    payload = {"value": req.value} if req.value not in (None, "") else {}
    try:
        command_id = db.create_autotrade_command(
            signal_id, command_name, payload,
            actor_type="MINIAPP_ADMIN", actor_id=int(user["id"]), account_number=req.account_number,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True, "command_id": command_id, "command": command_name, "signal_id": signal_id}


@router.post("/signals/{request_id}/retry")
def retry(request_id: str, x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data")):
    _admin(x_telegram_init_data)
    row = db.get_signal_by_publish_token(request_id)
    if not row:
        raise HTTPException(status_code=404, detail="signal request not found")
    return {"ok": True, "status": _signal_item(row)["status"], "publication": "CURRENT_STATE", "signal_id": int(row["id"])}
