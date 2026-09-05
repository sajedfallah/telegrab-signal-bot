from __future__ import annotations

from contextlib import asynccontextmanager
import base64
import asyncio
import binascii
import json
import uuid
import math
import hmac
from io import BytesIO
from pathlib import Path
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from .. import db
from .service import (
    AutoTradeError, active_signals, authorize_mt5, authorize_admin_mt5,
    authorize_standard_mt5, pending_commands,
)

API_VERSION = "0.6.5"

@asynccontextmanager
async def lifespan(_app):
    db.init_db()
    from ..admin_api import init_admin_schema
    init_admin_schema()
    yield

app = FastAPI(title="NEXUS Auto Trade API", version=API_VERSION, lifespan=lifespan)

# Browser access is deliberately allow-listed. For local development the Vite
# origin is enabled; production origins can be supplied as a comma-separated
# ADMIN_WEB_ORIGINS value.
import os
_admin_origins = [x.strip() for x in os.getenv("ADMIN_WEB_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173").split(",") if x.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_admin_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
)

@app.middleware("http")
async def admin_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.url.path.startswith("/admin"):
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self' ws: wss:"
        response.headers["Cache-Control"] = "no-store"
    return response

from ..admin_api import router as admin_router
app.include_router(admin_router)

RECEIPT_STATUSES = "^(?:executed|activated|rejected|failed|failed_retryable|closed|pending|ignored)$"

# Telegram publication is fail-closed. Only a durable, broker-confirmed
# execution receipt may create the original Telegram signal/screenshot.
PUBLISHABLE_RECEIPT_STATUSES = {"EXECUTED", "PENDING", "ACTIVATED"}


class ActivateRequest(BaseModel):
    license_key: str
    account_number: str
    broker: str | None = None
    server: str | None = None
    ea_version: str | None = None


class HeartbeatRequest(BaseModel):
    license_key: str
    account_number: str
    ea_version: str | None = None


# Legacy contract marker: pattern="OPEN|PENDING|UPDATE|CLOSE" remains supported semantically.
class AccountChangeRequest(BaseModel):
    new_account_number: str = Field(min_length=3, max_length=32)
    broker: str | None = Field(default=None, max_length=128)
    server: str | None = Field(default=None, max_length=128)
    reason: str | None = Field(default=None, max_length=500)


class SignalReceiptRequest(BaseModel):
    license_key: str
    account_number: str
    signal_db_id: int
    status: str = Field(pattern=RECEIPT_STATUSES)
    ticket: str | None = None
    error: str | None = None


class MT5AdminSignalRequest(BaseModel):
    market_type: str = Field(default="GOLD", pattern="^(?:FOREX|CRYPTO|GOLD|INDEX|OTHER)$")
    symbol: str = Field(min_length=1, max_length=64)
    direction: str = Field(pattern="^(?:BUY|SELL|LONG|SHORT)$")
    order_type: str = Field(default="MARKET", pattern="^(?:MARKET|LIMIT|BUY_LIMIT|SELL_LIMIT|BUY_STOP|SELL_STOP|BUY_STOP_LIMIT|SELL_STOP_LIMIT)$")
    timeframe: str = Field(default="M5", pattern="^(?:M1|M3|M5|M15|M30|H1|H4|D1|W1)$")
    entry_price: float = Field(gt=0)
    stop_loss: float = Field(gt=0)
    targets: list[float] = Field(min_length=1, max_length=10)
    risk_percent: float = Field(default=0.0, ge=0, le=100)
    rr_ratio: float | None = Field(default=None, gt=0)
    volume_mode: str = Field(default="RISK", pattern="^(?:RISK|FIXED)$")
    lot_size: float | None = Field(default=None, gt=0)
    leverage: float | None = Field(default=None, gt=0)
    trailing_code: str | None = Field(default=None, max_length=64)
    trailing_name: str | None = Field(default=None, max_length=128)
    trailing_config: dict | None = None
    max_entry_deviation_pct: float | None = Field(default=None, gt=0)
    max_entry_deviation_abs: float | None = Field(default=None, gt=0)
    stop_limit_price: float | None = Field(default=None, gt=0)
    request_id: str | None = Field(default=None, max_length=160)
    signal_code: str | None = Field(default=None, max_length=64)
    chart_base64: str | None = Field(default=None, max_length=8_000_000)
    destination: str = Field(default="BOTH", pattern="^(?:FREE|VIP|BOTH)$")


class MT5AdminCommandRequest(BaseModel):
    command: str = Field(pattern="^(?:MOVE_SL_TO_ENTRY|CLOSE_SIGNAL|CANCEL_PENDING|UPDATE_SL|UPDATE_TP|ACTIVATE_TRAILING|PARTIAL_CLOSE)$")
    value: str | None = Field(default=None, max_length=128)
    request_id: str | None = Field(default=None, max_length=160)


class CommandReceiptRequest(BaseModel):
    license_key: str
    account_number: str
    command_id: int
    status: str = Field(pattern=RECEIPT_STATUSES)
    error: str | None = None



class MT5LiveStateItem(BaseModel):
    identifier: str = Field(min_length=1, max_length=64)
    ticket: str = Field(min_length=1, max_length=64)
    signal_code: str = Field(default="", max_length=128)
    symbol: str = Field(min_length=1, max_length=64)
    direction: str = Field(default="", max_length=16)
    volume: float = Field(default=0.0, ge=0.0, le=1_000_000)
    entry_price: float = Field(default=0.0, ge=0.0, le=1e12)
    current_price: float = Field(default=0.0, ge=0.0, le=1e12)
    stop_loss: float = Field(default=0.0, ge=0.0, le=1e12)
    take_profit: float = Field(default=0.0, ge=0.0, le=1e12)
    profit: float = Field(default=0.0, ge=-1e12, le=1e12)
    magic: int = Field(default=0, ge=-2_147_483_648, le=2_147_483_647)
    nexus_managed: bool = True
    order_type: str = Field(default="MARKET", max_length=32)

class MT5LiveStateRequest(BaseModel):
    license_key: str = ""
    account_number: str = Field(min_length=3, max_length=32)
    broker: str = Field(default="", max_length=128)
    server: str = Field(default="", max_length=128)
    ea_version: str = Field(default="", max_length=32)
    positions: list[MT5LiveStateItem] = Field(default_factory=list, max_length=200)
    orders: list[MT5LiveStateItem] = Field(default_factory=list, max_length=200)


class HistoryReconcileItem(BaseModel):
    event: str = Field(pattern="^(?:OPEN|CLOSE)$")
    ticket: str = Field(min_length=1, max_length=64)
    event_id: str = Field(min_length=1, max_length=160)
    signal_id: str = Field(default="", max_length=128)
    symbol: str = Field(min_length=1, max_length=64)
    direction: str = Field(pattern="^(?:LONG|SHORT)$")
    volume: float = Field(default=0.0, ge=0.0, le=1_000_000)
    entry_price: float = Field(default=0.0, ge=0.0, le=1e12)
    stop_loss: float = Field(default=0.0, ge=0.0, le=1e12)
    take_profit: float = Field(default=0.0, ge=0.0, le=1e12)
    exit_price: float = Field(default=0.0, ge=0.0, le=1e12)
    profit: float = Field(default=0.0, ge=-1e12, le=1e12)
    gross_profit: float = Field(default=0.0, ge=-1e12, le=1e12)
    commission: float = Field(default=0.0, ge=-1e12, le=1e12)
    swap: float = Field(default=0.0, ge=-1e12, le=1e12)
    slippage: float = Field(default=0.0, ge=-1e12, le=1e12)
    risk_cash: float = Field(default=0.0, ge=0.0, le=1e12)
    realized_r: float | None = Field(default=None, ge=-1e9, le=1e9)
    position_id: str = Field(default="", max_length=64)
    deal_id: str = Field(default="", max_length=64)
    cycle_id: str = Field(default="", max_length=128)
    event_time: str = Field(default="", max_length=64)
    event_time_ms: int = Field(default=0, ge=0, le=9_999_999_999_999)
    destination: str = Field(default="BOTH", max_length=8)


class HistoryReconcileRequest(BaseModel):
    license_key: str = ""
    account_number: str = ""
    items: list[HistoryReconcileItem] = Field(default_factory=list, max_length=200)


class TradeEventRequest(BaseModel):
    license_key: str = ""
    account_number: str = ""
    event: str = Field(pattern="^(?:OPEN|PENDING|UPDATE|CLOSE|CANCEL|EXPIRE)$")
    ticket: str = Field(min_length=1, max_length=32)
    signal_id: str = Field(default="", max_length=128)
    symbol: str = Field(min_length=1, max_length=64)
    direction: str = Field(pattern="^(?:LONG|SHORT)$")
    volume: float = Field(default=0.0, ge=0.0, le=1_000_000)
    entry_price: float = Field(default=0.0, ge=0.0, le=1e12)
    stop_loss: float = Field(default=0.0, ge=0.0, le=1e12)
    take_profit: float = Field(default=0.0, ge=0.0, le=1e12)
    exit_price: float = Field(default=0.0, ge=0.0, le=1e12)
    profit: float = Field(default=0.0, ge=-1e12, le=1e12)
    gross_profit: float = Field(default=0.0, ge=-1e12, le=1e12)
    commission: float = Field(default=0.0, ge=-1e12, le=1e12)
    swap: float = Field(default=0.0, ge=-1e12, le=1e12)
    slippage: float = Field(default=0.0, ge=-1e12, le=1e12)
    risk_cash: float = Field(default=0.0, ge=0.0, le=1e12)
    realized_r: float | None = Field(default=None, ge=-1e9, le=1e9)
    position_id: str = Field(default="", max_length=64)
    deal_id: str = Field(default="", max_length=64)
    cycle_id: str = Field(default="", max_length=128)
    chart_base64: str = Field(default="", max_length=7_000_000)
    event_id: str = Field(default="", max_length=160)
    event_time_ms: int = Field(default=0, ge=0, le=9_223_372_036_854_775_807)
    destination: str = Field(default="NONE", pattern="^(?:NONE|FREE|VIP|BOTH)$")
    order_type: str = Field(default="MARKET", pattern="^(?:MARKET|BUY_LIMIT|SELL_LIMIT|BUY_STOP|SELL_STOP|BUY_STOP_LIMIT|SELL_STOP_LIMIT|LIMIT)$")
    stop_limit_price: float = Field(default=0.0, ge=0.0, le=1e12)
    close_reason: str = Field(default="", max_length=64)

    @field_validator("event", "direction", "destination", "order_type", mode="before")
    @classmethod
    def normalize_enums(cls, value):
        return str(value or "").strip().upper()

    @field_validator("volume", "entry_price", "stop_loss", "take_profit", "exit_price", "profit", "stop_limit_price")
    @classmethod
    def reject_non_finite(cls, value):
        if not math.isfinite(float(value)):
            raise ValueError("numeric value must be finite")
        return float(value)

def _auth_headers(x_license_key: str | None, x_mt5_account: str | None) -> tuple[str, str]:
    if not x_license_key or not x_mt5_account:
        raise HTTPException(status_code=401, detail="missing Auto Trade credentials")
    return x_license_key, x_mt5_account


def _ea_auth_headers(
    x_license_key: str | None,
    x_mt5_account: str | None,
    x_broker: str | None = None,
    x_server: str | None = None,
    x_ea_version: str | None = None,
):
    # Admin-mode EA sessions intentionally have no customer license key.
    # The account is still mandatory because the server-side admin allow-list
    # binds the bypass to a specific MT5 account.
    account = str(x_mt5_account or "").strip()
    if not account:
        raise HTTPException(status_code=401, detail="missing MT5 account")
    return str(x_license_key or "").strip(), account, x_broker, x_server, x_ea_version


def _admin_auth(x_admin_mode: str | None, x_admin_token: str | None, account: str):
    if str(x_admin_mode or "").strip().lower() not in {"1", "true", "yes", "on"}:
        return None
    try:
        return authorize_admin_mt5(account, x_admin_token)
    except AutoTradeError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


def _resolve_ea_auth(
    key: str, account: str, *,
    admin: dict | None = None,
    broker: str | None = None,
    server: str | None = None,
    ea_version: str | None = None,
    bind: bool = False,
) -> dict:
    """Resolve ADMIN or a valid customer license; fail closed otherwise."""
    if admin:
        return admin
    if not str(key or "").strip():
        raise AutoTradeError("Auto Trade license is required")
    # Never downgrade a supplied invalid/expired license to STANDARD.
    return authorize_mt5(
        str(key).strip(), account, bind=bind, broker=broker, server=server,
        ea_version=ea_version,
    )


def _require_broker_confirmed_receipt(row, account: str, status: str, ticket: str | None) -> None:
    """Reject success receipts until the authoritative MT5 snapshot proves them."""
    status_l = str(status).lower()
    expected_type = {"executed": "POSITION", "activated": "POSITION", "pending": "ORDER"}.get(status_l)
    if expected_type is None:
        return
    ticket_s = str(ticket or "").strip()
    if not ticket_s:
        raise HTTPException(status_code=409, detail=f"{status_l} receipt requires a broker ticket")
    if not row:
        raise HTTPException(status_code=409, detail="signal not found")
    live = db.mt5_live_for_signal(str(row["code"]), str(account))
    # ePlanet (and some other brokers) can clear POSITION_COMMENT after a
    # partial close. In that case the current snapshot temporarily has no
    # signal_code, but an exact broker ticket on the same authenticated account
    # remains an authoritative and unambiguous confirmation.
    if not live:
        live = (
            db.mt5_live_positions(str(account), nexus_only=True)
            if expected_type == "POSITION"
            else db.mt5_live_orders(str(account), nexus_only=True)
        )
    confirmed = any(
        str(item.get("state_type") or "").upper() == expected_type
        and str(item.get("ticket") or "") == ticket_s
        and str(item.get("status") or "").upper() in {"OPEN", "PENDING"}
        and bool(item.get("nexus_managed"))
        for item in live
    )
    if not confirmed:
        raise HTTPException(
            status_code=409,
            detail=f"{status_l} receipt is not confirmed by the current MT5 broker snapshot",
        )


@app.post("/api/v1/autotrade/account-change")
def account_change(
    req: AccountChangeRequest,
    x_license_key: str | None = Header(None),
    x_mt5_account: str | None = Header(None),
):
    key, account = _auth_headers(x_license_key, x_mt5_account)
    try:
        auth = authorize_mt5(key, account, bind=False)
        if not auth.get("allow_advanced_settings"):
            raise AutoTradeError("Auto Trade license is not active")
        row = db.request_mt5_account_change(int(auth["telegram_id"]), req.new_account_number, req.broker, req.server, req.reason)
        db.add_audit(int(auth["telegram_id"]), "mt5_account_change_requested", int(row["id"]), f"{account} -> {req.new_account_number}")
        return {"ok": True, "request_id": int(row["id"]), "status": str(row["status"])}
    except AutoTradeError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/v1/admin/autotrade/account-change-requests")
def admin_account_change_requests(
    x_admin_token: str | None = Header(None, alias="X-NEXUS-Admin-Token"),
):
    from ..config import settings
    if not settings.nexus_admin_token or not x_admin_token or not hmac.compare_digest(str(x_admin_token), str(settings.nexus_admin_token)):
        raise HTTPException(status_code=403, detail="admin authorization rejected")
    rows = db.pending_mt5_account_change_requests()
    return {"ok": True, "requests": [dict(r) for r in rows]}


class AccountChangeReviewRequest(BaseModel):
    approve: bool
    reason: str | None = Field(default=None, max_length=500)


@app.post("/api/v1/admin/autotrade/account-change-requests/{request_id}/review")
def admin_review_account_change(
    request_id: int,
    req: AccountChangeReviewRequest,
    x_admin_token: str | None = Header(None, alias="X-NEXUS-Admin-Token"),
):
    from ..config import settings
    if not settings.nexus_admin_token or not x_admin_token or not hmac.compare_digest(str(x_admin_token), str(settings.nexus_admin_token)):
        raise HTTPException(status_code=403, detail="admin authorization rejected")
    try:
        admin_id = int(settings.admin_ids[0])
        row = db.review_mt5_account_change(request_id, admin_id, req.approve, req.reason)
        db.add_audit(admin_id, "mt5_account_change_reviewed", int(row["id"]), f"status={row['status']} old={row['old_account_number']} new={row['new_account_number']}")
        return {"ok": True, "request_id": int(row["id"]), "status": str(row["status"]), "telegram_id": int(row["telegram_id"])}
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/v1/autotrade/health")
def health():
    return {"ok": True, "service": "nexus-autotrade", "version": API_VERSION}


@app.post("/api/v1/autotrade/activate")
def activate(req: ActivateRequest):
    try:
        data = authorize_mt5(req.license_key, req.account_number, bind=True, broker=req.broker, server=req.server, ea_version=req.ea_version)
        return {"ok": True, **data}
    except AutoTradeError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@app.post("/api/v1/autotrade/license/check")
def check_license(req: HeartbeatRequest):
    try:
        data = authorize_mt5(req.license_key, req.account_number, bind=False, ea_version=req.ea_version)
        return {"ok": True, **data}
    except AutoTradeError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@app.post("/api/v1/autotrade/heartbeat")
def heartbeat(req: HeartbeatRequest):
    try:
        data = authorize_mt5(req.license_key, req.account_number, bind=False, ea_version=req.ea_version)
        db.record_mt5_heartbeat(req.account_number, role="CLIENT", ea_version=req.ea_version, payload=data)
        return {"ok": True, **data, "next_check_seconds": 300}
    except AutoTradeError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc




# MT5 compatibility endpoints. Some terminal/build combinations are unreliable
# when POSTing JSON to a localhost Uvicorn server. The EA therefore uses GET
# plus headers for its control-plane calls while the original POST endpoints
# remain available for other clients.
@app.get("/api/v1/autotrade/activate")
def activate_mt5_get(
    x_license_key: str | None = Header(None),
    x_mt5_account: str | None = Header(None),
    x_broker: str | None = Header(None),
    x_server: str | None = Header(None),
    x_ea_version: str | None = Header(None),
    x_admin_mode: str | None = Header(None, alias="X-NEXUS-Admin-Mode"),
    x_admin_token: str | None = Header(None, alias="X-NEXUS-Admin-Token"),
):
    key, account, broker, server, version = _ea_auth_headers(
        x_license_key, x_mt5_account, x_broker, x_server, x_ea_version
    )
    admin = _admin_auth(x_admin_mode, x_admin_token, account)
    try:
        data = _resolve_ea_auth(
            key, account, admin=admin, bind=True,
            broker=broker, server=server, ea_version=version,
        )
    except AutoTradeError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return {"ok": True, **data}


@app.get("/api/v1/autotrade/license/check")
def check_license_mt5_get(
    x_license_key: str | None = Header(None),
    x_mt5_account: str | None = Header(None),
    x_ea_version: str | None = Header(None),
    x_admin_mode: str | None = Header(None, alias="X-NEXUS-Admin-Mode"),
    x_admin_token: str | None = Header(None, alias="X-NEXUS-Admin-Token"),
):
    key, account, _, _, _ = _ea_auth_headers(x_license_key, x_mt5_account, x_ea_version=x_ea_version)
    admin = _admin_auth(x_admin_mode, x_admin_token, account)
    try:
        data = _resolve_ea_auth(key, account, admin=admin, ea_version=x_ea_version)
    except AutoTradeError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return {"ok": True, **data}


@app.get("/api/v1/autotrade/heartbeat")
def heartbeat_mt5_get(
    x_license_key: str | None = Header(None),
    x_mt5_account: str | None = Header(None),
    x_ea_version: str | None = Header(None),
    x_admin_mode: str | None = Header(None, alias="X-NEXUS-Admin-Mode"),
    x_admin_token: str | None = Header(None, alias="X-NEXUS-Admin-Token"),
):
    key, account, _, _, _ = _ea_auth_headers(x_license_key, x_mt5_account, x_ea_version=x_ea_version)
    admin = _admin_auth(x_admin_mode, x_admin_token, account)
    try:
        data = admin or authorize_mt5(key, account, bind=False, ea_version=x_ea_version)
        db.record_mt5_heartbeat(account, role="ADMIN" if admin else "CLIENT", ea_version=x_ea_version, payload=data)
        return {"ok": True, **data, "next_check_seconds": 300}
    except AutoTradeError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@app.get("/api/v1/autotrade/signal-receipt")
def signal_receipt_mt5_get(
    background_tasks: BackgroundTasks,
    signal_db_id: int = Query(..., ge=1),
    status: str = Query(..., pattern=RECEIPT_STATUSES),
    ticket: str | None = Query(None),
    error: str | None = Query(None),
    x_license_key: str | None = Header(None),
    x_mt5_account: str | None = Header(None),
    x_admin_mode: str | None = Header(None, alias="X-NEXUS-Admin-Mode"),
    x_admin_token: str | None = Header(None, alias="X-NEXUS-Admin-Token"),
):
    key, account, _, _, _ = _ea_auth_headers(x_license_key, x_mt5_account)
    admin = _admin_auth(x_admin_mode, x_admin_token, account)
    auth = _resolve_ea_auth(key, account, admin=admin)
    row=db.get_signal(signal_db_id)
    _require_broker_confirmed_receipt(row, account, status, ticket)
    try:
        db.mark_signal_receipt(signal_db_id, auth["telegram_id"], status=status, ticket=ticket, error_text=error, account_number=account)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    accepted=str(status).lower() in {"executed","pending"}
    is_authority=bool(row and str(row["issuer_type"] or "").upper()=="MT5_ADMIN" and str(row["issuer_account"] or "")==str(account))
    if accepted and is_authority:
        background_tasks.add_task(_publish_mt5_admin_signal_async,row,None)
    return {"ok":True,"publication":"QUEUED" if accepted and is_authority else "NOT_APPLICABLE"}


@app.get("/api/v1/autotrade/command-receipt")
def command_receipt_mt5_get(
    command_id: int = Query(..., ge=1),
    status: str = Query(..., pattern=RECEIPT_STATUSES),
    error: str | None = Query(None),
    x_license_key: str | None = Header(None),
    x_mt5_account: str | None = Header(None),
    x_admin_mode: str | None = Header(None, alias="X-NEXUS-Admin-Mode"),
    x_admin_token: str | None = Header(None, alias="X-NEXUS-Admin-Token"),
):
    key, account, _, _, _ = _ea_auth_headers(x_license_key, x_mt5_account)
    admin = _admin_auth(x_admin_mode, x_admin_token, account)
    auth = _resolve_ea_auth(key, account, admin=admin)
    try:
        db.mark_command_receipt(command_id, auth["telegram_id"], status=status, error_text=error)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True}


async def _publish_mt5_admin_signal_async(row, chart_base64: str | None = None) -> dict:
    """Publish an MT5-authority signal only after an accepted execution receipt.

    The publication asset is staged before MT5 execution and consumed only here.
    Channel claims make publication idempotent across duplicate receipts/retries.
    """
    receipt = db.mt5_signal_live_state(int(row["id"])) or {}
    exec_status = str(receipt.get("receipt_status") or "NOT_RECEIVED").strip().upper()

    # This guard is intentionally inside the publisher itself so EVERY caller
    # (accepted receipt, retry worker, CLOSE anchor recovery, future callers)
    # inherits the same execution-truth invariant.
    if exec_status not in PUBLISHABLE_RECEIPT_STATUSES:
        return {
            "free_message_id": None,
            "vip_message_id": None,
            "errors": [
                f"EXECUTION_GATE: receipt status {exec_status} is not publishable"
            ],
            "published": False,
            "complete": False,
            "execution_status": exec_status,
        }

    errors: list[str] = []
    try:
        from ..config import settings
        from ..signals.card_generator import build_chart_frame, build_signal_card
        from aiogram import Bot
        from aiogram.enums import ParseMode
        from aiogram.types import BufferedInputFile
    except Exception as exc:
        return {"free_message_id": None, "vip_message_id": None, "errors": [f"TELEGRAM_INIT: {exc}"], "published": False}

    raw = b""
    asset_path = db.get_mt5_signal_publication_asset(int(row["id"]))
    if asset_path:
        try:
            raw = Path(asset_path).read_bytes()
        except OSError as exc:
            errors.append(f"CHART_ASSET: {exc}")
    if not raw and chart_base64:
        try:
            raw = base64.b64decode(chart_base64, validate=True)
            if not raw or len(raw) > 5_000_000:
                raise ValueError("chart image is empty or exceeds 5 MB")
        except (ValueError, binascii.Error) as exc:
            errors.append(f"CHART: {exc}")
            raw = b""

    try:
        if raw:
            chart_frame = await asyncio.to_thread(build_chart_frame, raw)
        else:
            # A broker/terminal may be unable to capture a screenshot (for
            # example while the chart is still loading). Never send an empty
            # dark frame: publish a useful signal card so the channel still
            # receives a visible image and the result reply has an anchor.
            card_signal = {
                "code": row["code"], "market_type": row["market_type"],
                "symbol": row["symbol"], "direction": row["direction"],
                "order_type": row["order_type"], "entry": row["entry_price"],
                "stop_loss": row["stop_loss"], "risk_percent": row["risk_percent"],
                "trailing_code": row["trailing_code"] or "—",
                "trailing_name": row["trailing_name"] or "—",
                "rr": row["rr_ratio"] or "—",
                "volume_mode": row["volume_mode"] or "RISK",
                "lot_size": row["lot_size"], "leverage": row["leverage"],
            }
            for target in db.get_signal_targets(int(row["id"])):
                card_signal[f"tp{int(target['target_no'])}"] = target["price"]
            chart_frame = await asyncio.to_thread(build_signal_card, None, card_signal)
    except Exception as exc:
        errors.append(f"CHART_RENDER: {exc}")
        chart_frame = b""

    destination = str(row["destination"] or "BOTH").upper()
    targets = db.get_signal_targets(int(row["id"]))
    target_map = {int(t["target_no"]): float(t["price"]) for t in targets}
    tp_lines = "\n".join(f"🎯 TP{n}: <code>{target_map[n]:g}</code>" for n in sorted(target_map)) or "🎯 TP: —"
    order_type = str(row["order_type"] or "MARKET").upper()
    caption = (
        "<b>━━━━━━━━ NEXUS SIGNAL ━━━━━━━━</b>\n"
        f"<b>{row['code']}</b>  🟦 {order_type}\n\n"
        f"📌 Symbol: <b>{str(row['symbol']).upper()}</b>\n"
        f"↕️ Direction: <b>{str(row['direction']).upper()}</b>\n"
        f"⏱ Timeframe: <b>{str(row['timeframe'] or 'M5').upper()}</b>\n"
        f"📍 Entry: <code>{float(row['entry_price']):g}</code>\n"
        f"🛑 Stop Loss: <code>{float(row['stop_loss']):g}</code>\n"
        f"{tp_lines}\n"
        f"📊 Risk: <b>{float(row['risk_percent']):g}%</b>\n"
        f"📌 Status: <b>{'PENDING' if exec_status == 'PENDING' else 'ACTIVE'}</b>\n"
        f"🔧 Trailing: <b>{row['trailing_code'] or '—'}</b>"
    )

    free_id = vip_id = None
    async with Bot(settings.bot_token) as bot:
        targets_to_send = []
        if destination in {"FREE", "BOTH"}:
            targets_to_send.append(("FREE", settings.free_channel_target))
        if destination in {"VIP", "BOTH"}:
            targets_to_send.append(("VIP", settings.vip_channel_id))
        for channel, target in targets_to_send:
            if not db.claim_signal_channel(int(row["id"]), channel):
                continue
            try:
                msg = await bot.send_photo(
                    target,
                    BufferedInputFile(chart_frame, filename=f"{row['code']}_chart.png"),
                    caption=caption, parse_mode=ParseMode.HTML,
                )
                mid = int(msg.message_id)
                if channel == "FREE":
                    free_id = mid
                else:
                    vip_id = mid
            except Exception as exc:
                db.release_signal_channel_claim(int(row["id"]), channel)
                errors.append(f"{channel}: {exc}")

    if free_id is not None or vip_id is not None:
        db.set_signal_publish_messages(int(row["id"]), free_id, vip_id)
    db.add_signal_event(
        int(row["id"]), "PUBLISH", actor_type="MT5_AUTHORITY", actor_id=int(row["created_by"]),
        account_number=str(row["issuer_account"] or ""), correlation_id=str(row["code"]),
        payload={"free_message_id": free_id, "vip_message_id": vip_id, "execution_status": exec_status, "errors": errors},
    )
    # Do not delete the staged chart until every requested channel has a message.
    complete = (destination == "FREE" and free_id is not None) or (destination == "VIP" and vip_id is not None) or (destination == "BOTH" and free_id is not None and vip_id is not None)
    if complete:
        db.clear_mt5_signal_publication_asset(int(row["id"]))
    return {"free_message_id": free_id, "vip_message_id": vip_id, "errors": errors,
            "published": bool(free_id or vip_id), "complete": complete}

def _publish_mt5_admin_signal(row, chart_base64: str | None = None) -> dict:
    return asyncio.run(_publish_mt5_admin_signal_async(row, chart_base64))


@app.post("/api/v1/admin/mt5/signals")
async def issue_mt5_admin_signal(
    req: MT5AdminSignalRequest,
    background_tasks: BackgroundTasks,
    x_mt5_account: str | None = Header(None),
    x_admin_token: str | None = Header(None, alias="X-NEXUS-Admin-Token"),
):
    account = str(x_mt5_account or "").strip()
    if not account:
        raise HTTPException(status_code=401, detail="missing MT5 admin account")
    try:
        auth = authorize_admin_mt5(account, x_admin_token)
        trailing_code = str(req.trailing_code or "").strip().upper() or None
        trailing_config = req.trailing_config
        if trailing_code:
            try:
                from .trailing_profiles import profile_snapshot
                if trailing_config is None:
                    trailing_config = profile_snapshot(trailing_code)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
        row = db.issue_mt5_admin_signal(
            market_type=req.market_type, symbol=req.symbol, direction=req.direction, entry_price=req.entry_price,
            stop_loss=req.stop_loss, targets=req.targets, risk_percent=req.risk_percent, rr_ratio=req.rr_ratio,
            order_type=req.order_type, volume_mode=req.volume_mode, lot_size=req.lot_size, leverage=req.leverage,
            trailing_code=trailing_code, trailing_name=req.trailing_name, trailing_config=trailing_config,
            max_entry_deviation_pct=req.max_entry_deviation_pct, max_entry_deviation_abs=req.max_entry_deviation_abs,
            timeframe=req.timeframe, stop_limit_price=req.stop_limit_price, destination=req.destination, admin_account=account,
            admin_id=int(auth["telegram_id"]), request_id=req.request_id, signal_code=req.signal_code,
        )
        # Stage the original signal screenshot. Publication is deliberately NOT
        # queued here: MT5 must first validate and execute/place the order and
        # send an accepted signal receipt. This closes the v0.6.0 publication race.
        if req.chart_base64:
            try:
                raw = base64.b64decode(req.chart_base64, validate=True)
                if not raw or len(raw) > 5_000_000:
                    raise ValueError("chart image is empty or exceeds 5 MB")
                if not (raw.startswith(b"\x89PNG\r\n\x1a\n") or raw.startswith(b"\xff\xd8\xff")):
                    raise ValueError("chart image must be PNG or JPEG")
                folder = Path(__file__).resolve().parent.parent / "assets" / "autotrade" / "pending_signal_charts"
                folder.mkdir(parents=True, exist_ok=True)
                ext = "png" if raw.startswith(b"\x89PNG\r\n\x1a\n") else "jpg"
                path = folder / f"{int(row['id'])}.{ext}"
                path.write_bytes(raw)
                db.save_mt5_signal_publication_asset(int(row["id"]), str(path))
            except (ValueError, binascii.Error) as exc:
                raise HTTPException(status_code=422, detail=f"invalid chart image: {exc}") from exc
        from .service import signal_to_payload
        payload = signal_to_payload(row)
        return {"ok": True, "signal_id": str(row["code"]), "signal": payload,
                "publication": {"status": "WAITING_EXECUTION", "destination": str(row["destination"] or "BOTH").upper()}}
    except AutoTradeError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/v1/admin/mt5/signals/{signal_id}/command")
def issue_mt5_admin_command(
    signal_id: int,
    req: MT5AdminCommandRequest,
    x_mt5_account: str | None = Header(None),
    x_admin_token: str | None = Header(None, alias="X-NEXUS-Admin-Token"),
):
    account = str(x_mt5_account or "").strip()
    try:
        authorize_admin_mt5(account, x_admin_token)
        row = db.get_signal(signal_id)
        if not row or str(row["issuer_type"] or "").upper() != "MT5_ADMIN":
            raise AutoTradeError("signal is not an MT5-admin signal")
        if str(row["issuer_account"] or "") != account:
            raise AutoTradeError("admin account does not own this signal")
        payload = {} if req.value is None else {"value": req.value}
        command_id = db.create_autotrade_command(signal_id, req.command, payload, actor_type="MT5_ADMIN", actor_id=authorize_admin_mt5(account, x_admin_token)["telegram_id"], account_number=account)
        return {"ok": True, "command_id": command_id, "signal_id": str(row["code"]), "command": req.command}
    except AutoTradeError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/v1/admin/mt5/signals")
def list_mt5_admin_signals(
    limit: int = Query(50, ge=1, le=200),
    x_mt5_account: str | None = Header(None),
    x_admin_token: str | None = Header(None, alias="X-NEXUS-Admin-Token"),
):
    account = str(x_mt5_account or "").strip()
    try:
        authorize_admin_mt5(account, x_admin_token)
        from .service import signal_to_payload
        return {"ok": True, "signals": [signal_to_payload(r) for r in db.list_mt5_admin_signals(limit)]}
    except AutoTradeError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@app.get("/api/v1/autotrade/signals")
def get_signals(
    after_id: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    x_license_key: str | None = Header(None),
    x_mt5_account: str | None = Header(None),
    x_admin_mode: str | None = Header(None, alias="X-NEXUS-Admin-Mode"),
    x_admin_token: str | None = Header(None, alias="X-NEXUS-Admin-Token"),
):
    key, account, _, _, _ = _ea_auth_headers(x_license_key, x_mt5_account)
    if db.get_setting("web_control_KILL_SWITCH", "0") == "1" or db.get_setting("web_control_NEW_ENTRIES", "0") == "1":
        return {"license_status": "PAUSED", "signals": [], "trading_paused": True}
    admin = _admin_auth(x_admin_mode, x_admin_token, account)
    if admin:
        rows = db.autotrade_active_signals(after_id, limit)
        from .service import signal_to_payload
        return {"license_status":"ADMIN", "signals":[signal_to_payload(r) for r in rows]}
    try:
        return active_signals(key, account, after_id=after_id, limit=limit)
    except AutoTradeError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@app.get("/api/v1/autotrade/commands")
def get_commands(
    after_id: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    x_license_key: str | None = Header(None),
    x_mt5_account: str | None = Header(None),
    x_admin_mode: str | None = Header(None, alias="X-NEXUS-Admin-Mode"),
    x_admin_token: str | None = Header(None, alias="X-NEXUS-Admin-Token"),
):
    key, account, _, _, _ = _ea_auth_headers(x_license_key, x_mt5_account)
    admin = _admin_auth(x_admin_mode, x_admin_token, account)
    try:
        auth = _resolve_ea_auth(key, account, admin=admin)
    except AutoTradeError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if not auth["allow_manage_trade"]:
        return {"license_status": auth["license_status"], "mode": auth.get("mode", "LOCKED"), "commands": []}
    rows = db.autotrade_commands(after_id, limit)
    import json as _json
    commands=[]
    for row in rows:
        payload=None
        if row["payload_json"]:
            try: payload=_json.loads(row["payload_json"])
            except Exception: payload={"value":row["payload_json"]}
        sig=db.get_signal(int(row["signal_id"]))
        commands.append({"id":int(row["id"]),"signal_id":str(sig["code"]) if sig else str(row["signal_id"]),
                         "signal_db_id":int(row["signal_id"]),"command":str(row["command"]),
                         "payload":payload,"created_at":str(row["created_at"])})
    return {"license_status": auth["license_status"], "mode": auth.get("mode", "STANDARD"), "commands":commands}



@app.post("/api/v1/autotrade/live-state")
def live_state(
    req: MT5LiveStateRequest,
    background_tasks: BackgroundTasks,
    x_license_key: str | None = Header(None),
    x_mt5_account: str | None = Header(None),
    x_broker: str | None = Header(None),
    x_server: str | None = Header(None),
    x_ea_version: str | None = Header(None),
    x_admin_mode: str | None = Header(None, alias="X-NEXUS-Admin-Mode"),
    x_admin_token: str | None = Header(None, alias="X-NEXUS-Admin-Token"),
):
    key, account, broker_h, server_h, version_h = _ea_auth_headers(x_license_key or req.license_key, x_mt5_account or req.account_number, x_broker, x_server, x_ea_version)
    admin = _admin_auth(x_admin_mode, x_admin_token, account)
    try:
        auth = _resolve_ea_auth(key, account, admin=admin, broker=broker_h or req.broker, server=server_h or req.server, ea_version=version_h or req.ea_version)
    except AutoTradeError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    positions=[i.model_dump() for i in req.positions]
    orders=[i.model_dump() for i in req.orders]
    result=db.upsert_mt5_live_snapshot(account, broker=broker_h or req.broker, server=server_h or req.server, ea_version=version_h or req.ea_version, positions=positions, orders=orders)

    # Missed receipt fallback: a broker-confirmed live NEXUS position is enough
    # to repair an execution receipt/ledger when the original receipt request
    # was lost. Publication is still gated on this broker-confirmed state.
    publications=[]
    uid=int(auth["telegram_id"])
    for item, live_status in [(x,"executed") for x in positions] + [(x,"pending") for x in orders]:
        code=str(item.get("signal_code") or "").strip()
        if not code.startswith("NX-") or not item.get("nexus_managed"): continue
        row=db.get_signal_by_code(code)
        if not row or str(row["issuer_type"] or "").upper()!="MT5_ADMIN" or str(row["issuer_account"] or "")!=account: continue
        try:
            live=db.mt5_signal_live_state(int(row["id"]))
            if str(live.get("receipt_status") or "").upper() not in {"EXECUTED","PENDING","ACTIVATED"}:
                db.mark_signal_receipt(int(row["id"]),uid,status=live_status,ticket=str(item["ticket"]),error_text=None,account_number=account)
                publications.append(int(row["id"]))
            event_type="OPEN" if live_status=="executed" else "PENDING"
            event_id=f"LIVE-{event_type}-{item['identifier']}"
            # Business identity beats transport event_id. A live snapshot may
            # arrive after the original MT5 trade-event and must repair/link that
            # execution rather than creating a second ledger row.
            with db.conn() as con:
                existing=con.execute(
                    "SELECT * FROM autotrade_trade_executions "
                    "WHERE telegram_id=? AND ticket=? AND signal_id=? AND event_type=? "
                    "ORDER BY id DESC LIMIT 1",
                    (uid,str(item["ticket"]),int(row["id"]),event_type),
                ).fetchone()
            payload={"event":event_type,"ticket":str(item["ticket"]),"signal_id":code,"symbol":str(item["symbol"]).upper(),"direction":str(item["direction"]).upper(),
                     "volume":float(item["volume"] or 0),"entry_price":float(item["entry_price"] or 0),"stop_loss":float(item["stop_loss"] or 0),
                     "take_profit":float(item["take_profit"] or 0),"event_id":event_id,"destination":str(row["destination"] or "BOTH"),
                     "order_type":str(item.get("order_type") or "MARKET").upper(),"position_id":str(item.get("identifier") or "") }
            if existing:
                # Update the already-recorded execution with broker-confirmed live data.
                db.update_trade_execution(uid,str(existing["ticket"]),str(existing["event_id"]),signal_id=int(row["id"]),status="RECONCILED",destination=str(row["destination"] or "BOTH"))
            else:
                db.enqueue_autotrade_trade_event(uid,event_type,payload,str(item["ticket"]))
                db.update_trade_execution(uid,str(item["ticket"]),event_id,signal_id=int(row["id"]),status="RECONCILED",destination=str(row["destination"] or "BOTH"))
        except ValueError:
            continue
    for sid in sorted(set(publications)):
        row=db.get_signal(sid)
        if row:
            background_tasks.add_task(_publish_mt5_admin_signal_async,row,None)
    return {"ok":True,**result,"publication_signal_ids":publications,"live_positions":db.mt5_live_positions(account,nexus_only=True),"live_orders":db.mt5_live_orders(account,nexus_only=True)}


@app.post("/api/v1/autotrade/trade-event")
def trade_event(
    req: TradeEventRequest,
    x_license_key: str | None = Header(None),
    x_mt5_account: str | None = Header(None),
    x_broker: str | None = Header(None),
    x_server: str | None = Header(None),
    x_ea_version: str | None = Header(None),
    x_admin_mode: str | None = Header(None, alias="X-NEXUS-Admin-Mode"),
    x_admin_token: str | None = Header(None, alias="X-NEXUS-Admin-Token"),
):
    # Header credentials are authoritative; body credentials are retained for
    # compatibility with the existing MT5 client.
    key = x_license_key or req.license_key
    account = x_mt5_account or req.account_number
    admin = _admin_auth(x_admin_mode, x_admin_token, account)
    try:
        auth = _resolve_ea_auth(
            key, account, admin=admin, broker=x_broker, server=x_server,
            ea_version=x_ea_version,
        )
    except AutoTradeError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    event = req.event.upper()
    # Legacy contract: if event not in {"OPEN", "PENDING", "UPDATE", "CLOSE"} remains
    # the base four-event contract; CANCEL/EXPIRE extend it for pending lifecycle.
    if event not in {"OPEN", "PENDING", "UPDATE", "CLOSE", "CANCEL", "EXPIRE"}:
        raise HTTPException(status_code=400, detail="unsupported trade event")

    # Validate trade geometry before persisting an event.  The broker/EA must
    # never be allowed to turn malformed prices into apparently valid ledger
    # entries. Zero is permitted for fields that are legitimately unavailable
    # on UPDATE/CLOSE events.
    if event in {"OPEN", "PENDING"}:
        if req.entry_price <= 0 or req.stop_loss <= 0 or req.take_profit <= 0:
            raise HTTPException(status_code=422, detail="OPEN requires positive entry, stop-loss and take-profit")
        if req.order_type in {"BUY_STOP_LIMIT","SELL_STOP_LIMIT"}:
            if req.stop_limit_price <= 0:
                raise HTTPException(status_code=422, detail="STOP_LIMIT requires stop_limit_price")
            if req.order_type == "BUY_STOP_LIMIT" and req.stop_limit_price < req.entry_price:
                raise HTTPException(status_code=422, detail="BUY_STOP_LIMIT stop-limit price must be >= stop price")
            if req.order_type == "SELL_STOP_LIMIT" and req.stop_limit_price > req.entry_price:
                raise HTTPException(status_code=422, detail="SELL_STOP_LIMIT stop-limit price must be <= stop price")
        if req.direction == "LONG" and not (req.stop_loss < req.entry_price < req.take_profit):
            raise HTTPException(status_code=422, detail="invalid LONG trade geometry")
        if req.direction == "SHORT" and not (req.take_profit < req.entry_price < req.stop_loss):
            raise HTTPException(status_code=422, detail="invalid SHORT trade geometry")
    elif req.stop_loss > 0 and req.take_profit > 0 and req.entry_price > 0:
        if req.direction == "LONG" and not (req.stop_loss < req.entry_price < req.take_profit):
            raise HTTPException(status_code=422, detail="invalid LONG trade geometry")
        if req.direction == "SHORT" and not (req.take_profit < req.entry_price < req.stop_loss):
            raise HTTPException(status_code=422, detail="invalid SHORT trade geometry")

    if len(req.chart_base64) > 7_000_000:
        raise HTTPException(status_code=413, detail="chart image is too large")
    destination = str(req.destination or "NONE").upper()
    if event in {"OPEN", "PENDING"} and destination == "NONE":
        # v0.6.0: destination is no longer a Telegram routing decision.
        # Canonical MT5-authority signals are distributed by AutoTrade API.
        if not auth.get("allow_manual_signal", False):
            raise HTTPException(status_code=403, detail="manual MT5 signal publishing is admin-only")
        destination = "BOTH"
    if destination not in {"NONE", "FREE", "VIP", "BOTH"}:
        raise HTTPException(status_code=400, detail="invalid signal destination")
    if event in {"OPEN", "PENDING"} and destination != "NONE" and not auth.get("allow_manual_signal", False):
        raise HTTPException(status_code=403, detail="manual MT5 signal publishing is admin-only")

    chart_path = ""
    if req.chart_base64:
        try:
            raw = base64.b64decode(req.chart_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise HTTPException(status_code=400, detail="invalid chart image encoding") from exc
        if len(raw) > 5_000_000:
            raise HTTPException(status_code=413, detail="chart image is too large")
        if not (raw.startswith(b"\x89PNG\r\n\x1a\n") or raw.startswith(b"\xff\xd8\xff")):
            raise HTTPException(status_code=400, detail="chart image must be PNG or JPEG")
        try:
            from PIL import Image, UnidentifiedImageError
            with Image.open(BytesIO(raw)) as image:
                image.verify()
                width, height = image.size
                if width <= 0 or height <= 0 or width * height > 20_000_000:
                    raise ValueError("image dimensions exceed safety limits")
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="invalid or unsafe PNG/JPEG image") from exc
        folder = Path(__file__).resolve().parent.parent / "assets" / "autotrade" / "mt5_events"
        folder.mkdir(parents=True, exist_ok=True)
        extension = "png" if raw.startswith(b"\x89PNG\r\n\x1a\n") else "jpg"
        filename = f"{int(auth['telegram_id'])}_{uuid.uuid4().hex}.{extension}"
        path = folder / filename
        path.write_bytes(raw)
        chart_path = str(path)

    payload = {
        "event": event,
        "ticket": str(req.ticket),
        "signal_id": str(req.signal_id or "").strip(),
        "symbol": str(req.symbol).upper(),
        "direction": str(req.direction).upper(),
        "volume": float(req.volume),
        "entry_price": float(req.entry_price),
        "stop_loss": float(req.stop_loss),
        "take_profit": float(req.take_profit),
        "exit_price": float(req.exit_price),
        "profit": float(req.profit),
        "gross_profit": float(req.gross_profit),
        "commission": float(req.commission),
        "swap": float(req.swap),
        "slippage": float(req.slippage),
        "risk_cash": float(req.risk_cash),
        "realized_r": float(req.realized_r) if req.realized_r is not None else None,
        "position_id": str(req.position_id or ""),
        "deal_id": str(req.deal_id or req.ticket),
        "cycle_id": str(req.cycle_id or ""),
        "chart_path": chart_path,
        "event_id": str(req.event_id or "").strip(),
        "event_time_ms": int(req.event_time_ms or 0),
        "destination": destination,
        "order_type": str(req.order_type or "MARKET").upper(),
        "stop_limit_price": float(req.stop_limit_price or 0),
        "close_reason": str(req.close_reason or "").strip().upper(),
        "broker": x_broker or "",
        "server": x_server or "",
        "ea_version": x_ea_version or "",
        "account_number": str(account),
        "issuer_type": "MT5_ADMIN" if auth.get("admin_mode") or auth.get("allow_manual_signal") and event in {"OPEN", "PENDING"} else "MT5_CLIENT",
    }
    # Pending manual orders need a durable signal identity immediately so the
    # later MT5 activation event can update the same lifecycle row.
    if event == "PENDING":
        publish_token = str(req.signal_id or f"MT5MANUAL-PENDING-{req.ticket}").strip()
        existing = db.get_signal_by_publish_token(publish_token)
        if existing:
            payload["signal_id"] = str(existing["code"])
        else:
            is_long = str(req.direction).upper() in {"LONG", "BUY"}
            fallback_tp = req.take_profit if req.take_profit > 0 else (
                req.entry_price + abs(req.entry_price - req.stop_loss) if is_long
                else req.entry_price - abs(req.entry_price - req.stop_loss)
            )
            market_type = "CRYPTO" if any(k in req.symbol.upper() for k in ("BTC","ETH","SOL","BNB","XRP","DOGE","ADA","AVAX","DOT","LTC")) else ("GOLD" if "XAU" in req.symbol.upper() else "FOREX")
            created = db.issue_mt5_admin_signal(
                market_type=market_type, symbol=req.symbol, direction=req.direction, entry_price=req.entry_price,
                stop_loss=req.stop_loss, targets=[fallback_tp], risk_percent=0.0, rr_ratio=None,
                order_type=str(req.order_type or "LIMIT").upper(), volume_mode="FIXED", lot_size=req.volume,
                trailing_name="Manual MT5 Pending", stop_limit_price=(float(req.stop_limit_price) if req.stop_limit_price > 0 else None),
                admin_account=str(account), admin_id=int(auth["telegram_id"]), request_id=str(req.event_id or f"PENDING:{req.ticket}"),
                signal_code=publish_token, timeframe="M5",
            )
            payload["signal_id"] = str(created["code"])
        db.enqueue_autotrade_trade_event(int(auth["telegram_id"]), event, payload, str(req.ticket))
        return {"ok": True, "queued": True, "event": event, "ticket": str(req.ticket), "signal_id": str(payload["signal_id"])}

    db.enqueue_autotrade_trade_event(int(auth["telegram_id"]), event, payload, str(req.ticket))
    return {"ok": True, "queued": True, "event": event, "ticket": str(req.ticket)}

@app.post("/api/v1/autotrade/history-reconcile")
def history_reconcile(
    req: HistoryReconcileRequest,
    x_license_key: str | None = Header(None),
    x_mt5_account: str | None = Header(None),
    x_broker: str | None = Header(None),
    x_server: str | None = Header(None),
    x_ea_version: str | None = Header(None),
    x_admin_mode: str | None = Header(None, alias="X-NEXUS-Admin-Mode"),
    x_admin_token: str | None = Header(None, alias="X-NEXUS-Admin-Token"),
):
    key = x_license_key or req.license_key
    account = x_mt5_account or req.account_number
    admin = _admin_auth(x_admin_mode, x_admin_token, account)
    try:
        auth = _resolve_ea_auth(key, account, admin=admin, broker=x_broker, server=x_server, ea_version=x_ea_version)
    except AutoTradeError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    items = [i.model_dump() for i in req.items]
    result = db.reconcile_mt5_history(int(auth["telegram_id"]), items)
    return {"ok": True, "reconciled": result}

@app.post("/api/v1/autotrade/signal-receipt")
def signal_receipt(
    req: SignalReceiptRequest,
    background_tasks: BackgroundTasks,
    x_license_key: str | None = Header(None),
    x_mt5_account: str | None = Header(None),
    x_admin_mode: str | None = Header(None, alias="X-NEXUS-Admin-Mode"),
    x_admin_token: str | None = Header(None, alias="X-NEXUS-Admin-Token"),
):
    key = x_license_key or req.license_key
    account = x_mt5_account or req.account_number
    admin = _admin_auth(x_admin_mode, x_admin_token, account)
    auth = _resolve_ea_auth(key, account, admin=admin)
    row = db.get_signal(req.signal_db_id)
    _require_broker_confirmed_receipt(row, account, req.status, req.ticket)
    try:
        db.mark_signal_receipt(req.signal_db_id, auth["telegram_id"], status=req.status, ticket=req.ticket, error_text=req.error, account_number=account)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    accepted = str(req.status).lower() in {"executed", "pending"}
    is_authority = bool(row and str(row["issuer_type"] or "").upper() == "MT5_ADMIN" and str(row["issuer_account"] or "") == str(account))
    if accepted and is_authority:
        background_tasks.add_task(_publish_mt5_admin_signal_async, row, None)
    return {"ok": True, "publication": "QUEUED" if accepted and is_authority else "NOT_APPLICABLE"}


@app.post("/api/v1/autotrade/command-receipt")
def command_receipt(
    req: CommandReceiptRequest,
    x_license_key: str | None = Header(None),
    x_mt5_account: str | None = Header(None),
    x_admin_mode: str | None = Header(None, alias="X-NEXUS-Admin-Mode"),
    x_admin_token: str | None = Header(None, alias="X-NEXUS-Admin-Token"),
):
    key = x_license_key or req.license_key
    account = x_mt5_account or req.account_number
    admin = _admin_auth(x_admin_mode, x_admin_token, account)
    auth = _resolve_ea_auth(key, account, admin=admin)
    try:
        db.mark_command_receipt(req.command_id, auth["telegram_id"], status=req.status, error_text=req.error)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True}


# A production build of the React console can be served by the same process,
# keeping the browser and API on one trusted origin. API routes above retain
# priority over the static mount.
_admin_dist = Path(__file__).resolve().parents[2] / "admin-web" / "dist"
if _admin_dist.exists():
    from fastapi.staticfiles import StaticFiles
    app.mount("/admin", StaticFiles(directory=_admin_dist, html=True), name="admin-web")
