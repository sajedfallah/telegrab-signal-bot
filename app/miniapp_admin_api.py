from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query
from pydantic import BaseModel, Field, field_validator, model_validator

from . import db
from .autotrade.symbol_registry import CANONICAL_SYMBOLS, infer_category, normalize_symbol
from .autotrade.trailing_profiles import TRAILING_GUIDE_FA, TRAILING_PROFILES, profile_snapshot


router = APIRouter(prefix="/miniapp/api/admin", tags=["miniapp-admin-signal-center"])
MAX_INIT_DATA_AGE = max(60, int(os.getenv("MINIAPP_AUTH_MAX_AGE_SECONDS", "86400")))
LIVE_PNL_STALE_SECONDS = max(120, min(int(os.getenv("MINIAPP_ACTIVE_TRUTH_STALE_SECONDS", "600")), 3600))
RR_MULTIPLIERS = (1.0, 1.5, 2.0, 3.0)
VALID_COMMANDS = {
    "MOVE_SL_TO_ENTRY", "CLOSE_SIGNAL", "CANCEL_PENDING", "UPDATE_SL",
    "UPDATE_TP", "ACTIVATE_TRAILING", "PARTIAL_CLOSE",
}


def init_miniapp_admin_schema() -> None:
    with db.conn() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS miniapp_admin_signal_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT NOT NULL UNIQUE,
                admin_telegram_id INTEGER NOT NULL,
                signal_id INTEGER,
                status TEXT NOT NULL,
                error_message TEXT,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(signal_id) REFERENCES signals(id) ON DELETE SET NULL
            );
            CREATE INDEX IF NOT EXISTS idx_miniapp_admin_signal_status
                ON miniapp_admin_signal_requests(status, updated_at);
            CREATE INDEX IF NOT EXISTS idx_miniapp_admin_signal_signal
                ON miniapp_admin_signal_requests(signal_id);
            """
        )


def _validate_init_data(init_data: str) -> dict[str, Any]:
    raw = str(init_data or "").strip()
    if not raw:
        raise HTTPException(401, "missing Telegram initData")
    try:
        pairs = parse_qsl(raw, keep_blank_values=True, strict_parsing=True)
    except ValueError as exc:
        raise HTTPException(401, "invalid Telegram initData") from exc
    if not pairs or len({key for key, _ in pairs}) != len(pairs):
        raise HTTPException(401, "invalid Telegram initData")
    data = dict(pairs)
    received_hash = str(data.pop("hash", ""))
    if not received_hash:
        raise HTTPException(401, "Telegram initData hash is missing")
    from .config import settings
    check_string = "\n".join(f"{key}={data[key]}" for key in sorted(data))
    secret_key = hmac.new(b"WebAppData", settings.bot_token.encode(), hashlib.sha256).digest()
    calculated = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated, received_hash):
        raise HTTPException(401, "Telegram initData signature is invalid")
    try:
        auth_date = int(data.get("auth_date", "0"))
        user = json.loads(data.get("user", "{}"))
        user_id = int(user["id"])
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise HTTPException(401, "invalid Telegram user data") from exc
    now = int(time.time())
    if auth_date <= 0 or auth_date > now + 60 or now - auth_date > MAX_INIT_DATA_AGE:
        raise HTTPException(401, "Telegram initData has expired")
    if user_id not in settings.admin_ids:
        raise HTTPException(403, "NEXUS administrator access is required")
    return user


def _admin(init_data: str | None) -> dict[str, Any]:
    return _validate_init_data(init_data or "")


def _digits_for(symbol: str, requested: int | None = None) -> int:
    if requested is not None:
        return max(0, min(int(requested), 8))
    configured = os.getenv("MINIAPP_SYMBOL_DIGITS_JSON", "").strip()
    if configured:
        try:
            value = json.loads(configured).get(symbol)
            if value is not None:
                return max(0, min(int(value), 8))
        except (ValueError, TypeError, json.JSONDecodeError):
            pass
    if symbol.endswith("JPY"):
        return 3
    if symbol.startswith(("XAU", "XAG", "BTC", "ETH")) or symbol in {"US30", "US100", "DOWJONES", "NASDAQ", "SPX500"}:
        return 2
    return 5


def calculate_auto_targets(symbol: str, direction: str, entry: float, stop_loss: float,
                           digits: int | None = None) -> dict[str, Any]:
    canonical = normalize_symbol(symbol)
    side = str(direction or "").strip().upper()
    if side not in {"BUY", "SELL"}:
        raise ValueError("direction must be BUY or SELL")
    entry_f, stop_f = float(entry), float(stop_loss)
    if not math.isfinite(entry_f) or not math.isfinite(stop_f) or entry_f <= 0 or stop_f <= 0:
        raise ValueError("entry and stop-loss must be positive finite numbers")
    if entry_f == stop_f:
        raise ValueError("entry and stop-loss must create non-zero risk")
    if side == "BUY" and stop_f >= entry_f:
        raise ValueError("BUY stop-loss must be below entry")
    if side == "SELL" and stop_f <= entry_f:
        raise ValueError("SELL stop-loss must be above entry")
    precision = _digits_for(canonical, digits)
    entry_n, stop_n = round(entry_f, precision), round(stop_f, precision)
    risk = round(abs(entry_n - stop_n), precision)
    if risk <= 0:
        raise ValueError("risk becomes zero after symbol precision normalization")
    sign = 1 if side == "BUY" else -1
    targets = [round(entry_n + sign * risk * multiple, precision) for multiple in RR_MULTIPLIERS]
    if any(value <= 0 for value in targets):
        raise ValueError("calculated target must be positive")
    ordered = (all(targets[i] < targets[i + 1] for i in range(len(targets) - 1))
               if side == "BUY" else
               all(targets[i] > targets[i + 1] for i in range(len(targets) - 1)))
    if not ordered:
        raise ValueError("calculated targets are not strictly ordered")
    return {"symbol": canonical, "direction": side, "digits": precision, "entry": entry_n,
            "stop_loss": stop_n, "risk": risk, "targets": targets,
            "target_multipliers": list(RR_MULTIPLIERS)}


def calculate_signal_levels(
    symbol: str,
    direction: str,
    entry: float,
    *,
    stop_loss: float | None = None,
    stop_loss_mode: str = "MANUAL",
    stop_distance: float | None = None,
    take_profit_mode: str = "AUTO",
    targets: list[float] | None = None,
    digits: int | None = None,
) -> dict[str, Any]:
    """Resolve canonical SL/TP levels without inventing trading assumptions.

    AUTO SL is deterministic and requires an explicit positive price distance.
    AUTO TP preserves the existing 1R/1.5R/2R/3R ladder. MANUAL TP preserves
    the prices supplied by the administrator after directional validation.
    """
    canonical = normalize_symbol(symbol)
    side = str(direction or "").strip().upper()
    sl_mode = str(stop_loss_mode or "MANUAL").strip().upper()
    tp_mode = str(take_profit_mode or "AUTO").strip().upper()
    if side not in {"BUY", "SELL"}:
        raise ValueError("direction must be BUY or SELL")
    if sl_mode not in {"MANUAL", "AUTO"}:
        raise ValueError("stop_loss_mode must be MANUAL or AUTO")
    if tp_mode not in {"MANUAL", "AUTO"}:
        raise ValueError("take_profit_mode must be MANUAL or AUTO")

    entry_f = float(entry)
    if not math.isfinite(entry_f) or entry_f <= 0:
        raise ValueError("entry must be a positive finite number")

    if sl_mode == "AUTO":
        if stop_distance is None:
            raise ValueError("stop_distance is required when stop-loss mode is AUTO")
        distance = float(stop_distance)
        if not math.isfinite(distance) or distance <= 0:
            raise ValueError("stop_distance must be a positive finite number")
        resolved_stop = entry_f - distance if side == "BUY" else entry_f + distance
    else:
        if stop_loss is None:
            raise ValueError("stop_loss is required when stop-loss mode is MANUAL")
        resolved_stop = float(stop_loss)

    result = calculate_auto_targets(canonical, side, entry_f, resolved_stop, digits)
    result["stop_loss_mode"] = sl_mode
    result["take_profit_mode"] = tp_mode
    result["stop_distance"] = round(abs(result["entry"] - result["stop_loss"]), result["digits"])

    if tp_mode == "AUTO":
        return result

    if not targets:
        raise ValueError("manual take-profit mode requires at least one target")
    precision = int(result["digits"])
    clean_targets: list[float] = []
    for raw in targets:
        value = float(raw)
        if not math.isfinite(value) or value <= 0:
            raise ValueError("manual take-profit targets must be positive finite numbers")
        clean_targets.append(round(value, precision))

    entry_n = float(result["entry"])
    if side == "BUY":
        if any(value <= entry_n for value in clean_targets):
            raise ValueError("BUY take-profit targets must be above entry")
        if any(clean_targets[i] >= clean_targets[i + 1] for i in range(len(clean_targets) - 1)):
            raise ValueError("BUY take-profit targets must be strictly increasing")
    else:
        if any(value >= entry_n for value in clean_targets):
            raise ValueError("SELL take-profit targets must be below entry")
        if any(clean_targets[i] <= clean_targets[i + 1] for i in range(len(clean_targets) - 1)):
            raise ValueError("SELL take-profit targets must be strictly decreasing")

    risk = float(result["risk"])
    result["targets"] = clean_targets
    result["target_multipliers"] = [round(abs(value - entry_n) / risk, 4) for value in clean_targets]
    return result


def _admin_mt5_status() -> dict[str, Any]:
    from .config import settings
    accounts = tuple(str(value) for value in settings.nexus_admin_mt5_accounts)
    row = None
    if accounts:
        with db.conn() as con:
            marks = ",".join("?" for _ in accounts)
            row = con.execute(
                f"SELECT account_number,ea_version,last_seen_at FROM mt5_heartbeats_v060 "
                f"WHERE role='ADMIN' AND account_number IN ({marks}) ORDER BY last_seen_at DESC LIMIT 1", accounts,
            ).fetchone()
    age = None
    if row:
        try:
            seen = datetime.fromisoformat(str(row["last_seen_at"]).replace("Z", "+00:00"))
            if seen.tzinfo is None:
                seen = seen.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - seen.astimezone(timezone.utc)).total_seconds()
        except ValueError:
            age = None
    online = age is not None and age <= 120
    return {"online": online, "status": "ONLINE" if online else "OFFLINE",
            "account_number": str(row["account_number"]) if row else (accounts[0] if accounts else None),
            "ea_version": str(row["ea_version"] or "") if row else None,
            "last_seen_at": str(row["last_seen_at"]) if row else None, "age_seconds": age}


def _symbol_catalog() -> list[dict[str, Any]]:
    labels = {"GOLD": "فلزات", "INDEX": "شاخص‌ها", "FOREX": "Forex", "CRYPTO": "Crypto"}
    order = ("GOLD", "INDEX", "FOREX", "CRYPTO")
    return [
        {"key": key, "label": labels[key], "symbols": list(CANONICAL_SYMBOLS[key])}
        for key in order
        if key in CANONICAL_SYMBOLS
    ]


def _trailing_catalog() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for code in sorted(TRAILING_PROFILES):
        snapshot = profile_snapshot(code)
        items.append({
            "code": code,
            "name": str(snapshot.get("name") or code),
            "guide": TRAILING_GUIDE_FA.get(code, ""),
            "config": snapshot,
        })
    return items


class CalculateRequest(BaseModel):
    symbol: str = Field(min_length=3, max_length=32)
    direction: str = Field(pattern="^(?:BUY|SELL)$")
    entry: float = Field(gt=0)
    stop_loss: float | None = Field(default=None, gt=0)
    stop_loss_mode: str = Field(default="MANUAL", pattern="^(?:MANUAL|AUTO)$")
    stop_distance: float | None = Field(default=None, gt=0)
    take_profit_mode: str = Field(default="AUTO", pattern="^(?:MANUAL|AUTO)$")
    targets: list[float] | None = Field(default=None, min_length=1, max_length=10)
    digits: int | None = Field(default=None, ge=0, le=8)

    @field_validator("direction", "stop_loss_mode", "take_profit_mode", mode="before")
    @classmethod
    def normalize_level_enums(cls, value: str) -> str:
        return str(value or "").strip().upper()


class CreateSignalRequest(CalculateRequest):
    destination: str = Field(pattern="^(?:FREE|VIP|BOTH)$")
    request_id: str = Field(min_length=8, max_length=160)
    timeframe: str = Field(default="M5", pattern="^(?:M1|M3|M5|M15|M30|H1|H4|D1|W1)$")
    setup_mode: str = Field(default="MANUAL", pattern="^(?:MANUAL|AUTO)$")
    volume_mode: str = Field(default="RISK", pattern="^(?:RISK|FIXED)$")
    risk_percent: float = Field(default=0.0, ge=0, le=100)
    lot_size: float | None = Field(default=None, gt=0)
    trailing_enabled: bool = False
    trailing_profile_code: str | None = Field(default=None, pattern="^NEXUS_TRAIL_0[1-7]$")
    # Legacy V2 numeric trailing overrides remain accepted for backward compatibility.
    trailing_break_even_r: float | None = Field(default=None, gt=0, le=100)
    trailing_step_r: float | None = Field(default=None, gt=0, le=100)
    trailing_lock_r: float | None = Field(default=None, gt=0, le=100)

    @field_validator("request_id")
    @classmethod
    def safe_request_id(cls, value: str) -> str:
        value = value.strip()
        if not re.fullmatch(r"[A-Za-z0-9._:-]+", value):
            raise ValueError("request_id contains invalid characters")
        return value

    @field_validator("destination", "setup_mode", "volume_mode", mode="before")
    @classmethod
    def normalize_create_enums(cls, value: str) -> str:
        return str(value or "").strip().upper()

    @field_validator("trailing_profile_code", mode="before")
    @classmethod
    def normalize_trailing_profile(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip().upper()
        return normalized or None

    @model_validator(mode="after")
    def validate_v066_contract(self):
        if self.volume_mode == "FIXED" and self.lot_size is None:
            raise ValueError("lot_size is required for FIXED volume")
        if self.volume_mode == "RISK" and self.lot_size is not None:
            raise ValueError("lot_size must be empty for RISK volume")
        # Fail closed until an authoritative completed-candle structure engine
        # exists. Never invent a structural stop from distance or heuristics.
        if self.setup_mode == "AUTO":
            raise ValueError(
                "AUTO setup requires confirmed MT5 candle structure; market-data feed is not available yet"
            )
        return self


class PositionCommandRequest(BaseModel):
    command: str
    account_number: str = Field(min_length=3, max_length=32)
    value: str | None = Field(default=None, max_length=128)


def _resolve_sizing(req: CreateSignalRequest) -> tuple[str, float, float | None]:
    mode = str(req.volume_mode or "RISK").strip().upper()
    if mode == "FIXED":
        if req.lot_size is None or not math.isfinite(float(req.lot_size)) or float(req.lot_size) <= 0:
            raise ValueError("lot_size is required and must be positive in FIXED volume mode")
        return "FIXED", 0.0, float(req.lot_size)
    risk = float(req.risk_percent)
    if not math.isfinite(risk) or risk < 0 or risk > 100:
        raise ValueError("risk_percent must be between 0 and 100")
    return "RISK", risk, None


def _resolve_trailing(req: CreateSignalRequest) -> tuple[str | None, str | None, dict[str, Any] | None]:
    if not req.trailing_enabled:
        return None, None, None

    if req.trailing_profile_code:
        snapshot = profile_snapshot(req.trailing_profile_code)
        code = str(snapshot["code"])
        name = str(snapshot.get("name") or code)
        return code, name, snapshot

    # Backward-compatible V2 fallback: old clients can still submit explicit
    # step values. New V3 UI always submits trailing_profile_code instead.
    break_even = float(req.trailing_break_even_r) if req.trailing_break_even_r is not None else 1.0
    step = float(req.trailing_step_r) if req.trailing_step_r is not None else 0.50
    lock = float(req.trailing_lock_r) if req.trailing_lock_r is not None else 0.30
    if not all(math.isfinite(value) and value > 0 for value in (break_even, step, lock)):
        raise ValueError("trailing parameters must be positive finite numbers")
    if lock > step:
        raise ValueError("trailing lock step cannot be greater than trailing movement step")
    code = "NEXUS_TRAIL_01"
    name = "Custom Step Trail"
    return code, name, {
        "name": name,
        "version": 2,
        "code": code,
        "break_even_r": break_even,
        "trail_step_r": step,
        "lock_step_r": lock,
    }


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


def _admin_live_signal(signal: Any) -> dict[str, Any] | None:
    if not signal:
        return None
    data = dict(signal)
    if str(data.get("status") or "").upper() == "CLOSED":
        return None
    account = str(data.get("issuer_account") or "").strip()
    code = str(data.get("code") or "").strip()
    if not account or not code:
        return {"status": "UNAVAILABLE", "pnl_state": None, "last_sync": None, "age_seconds": None}
    with db.conn() as con:
        rows = [dict(row) for row in con.execute(
            """
            SELECT live.* FROM mt5_live_state live
            WHERE live.account_number=? AND live.nexus_managed=1
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
            (account, code, int(data["id"])),
        ).fetchall()]
    if not rows:
        return {"status": "UNAVAILABLE", "pnl_state": None, "last_sync": None, "age_seconds": None}
    last_sync = max((str(row.get("last_seen_at") or "") for row in rows), default="") or None
    age = _snapshot_age_seconds(last_sync)
    fresh = age is not None and age <= LIVE_PNL_STALE_SECONDS
    positions = [row for row in rows if str(row.get("state_type") or "").upper() == "POSITION" and str(row.get("status") or "").upper() == "OPEN"]
    pending = [row for row in rows if str(row.get("state_type") or "").upper() == "ORDER" and str(row.get("status") or "").upper() == "PENDING"]
    if positions:
        latest = max(positions, key=lambda row: str(row.get("last_seen_at") or ""))
        pnl = sum(float(row.get("profit") or 0.0) for row in positions)
        volume = sum(float(row.get("volume") or 0.0) for row in positions)
        current = float(latest.get("current_price") or 0.0) or None
        entry = float(data.get("entry_price") or 0.0)
        original_sl = float(data.get("stop_loss") or 0.0)
        initial_r = abs(entry - original_sl)
        current_r = None
        if current is not None and entry > 0 and initial_r > 0:
            side = str(data.get("direction") or "").upper()
            move = current - entry if side in {"BUY", "LONG"} else entry - current
            current_r = round(move / initial_r, 4)
        return {
            "status": "LIVE" if fresh else "STALE",
            "current_price": current,
            "floating_pnl": round(pnl, 2),
            "current_r": current_r,
            "volume": volume,
            "stop_loss": float(latest.get("stop_loss") or 0.0) or None,
            "take_profit": float(latest.get("take_profit") or 0.0) or None,
            "pnl_state": "IN_PROFIT" if pnl > 0 else "IN_LOSS" if pnl < 0 else "BE",
            "last_sync": last_sync,
            "age_seconds": round(age, 1) if age is not None else None,
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
            "age_seconds": round(age, 1) if age is not None else None,
            "position_count": 0,
        }
    return {"status": "UNAVAILABLE", "pnl_state": None, "last_sync": last_sync, "age_seconds": age}


def _sync_request(row) -> dict[str, Any]:
    item = dict(row)
    signal = db.get_signal(int(item["signal_id"])) if item.get("signal_id") else None
    job = db.get_signal_chart_capture_job(int(item["signal_id"])) if item.get("signal_id") else None
    status, error = str(item["status"]), item.get("error_message")
    if signal:
        if signal["free_message_id"] or signal["vip_message_id"]:
            status = "PUBLISHED"
        elif job:
            job_status = str(job["status"] or "").upper()
            if job_status in {"UPLOADED", "COMPLETED"}:
                status = "SCREENSHOT_READY"
            elif job_status in {"CLAIMED", "CAPTURING"}:
                status = "PROCESSING"
            elif job_status == "FAILED":
                status, error = "FAILED", str(job["error_text"] or "chart capture failed")
            elif job_status == "EXPIRED":
                status, error = "EXPIRED", str(job["error_text"] or "chart capture expired")
            elif job_status == "PENDING":
                status = "WAITING_FOR_MT5" if not _admin_mt5_status()["online"] else "READY"
        if str(signal["publication_stage"] or "").upper() == "PUBLISH_FAILED":
            status, error = "FAILED", "Telegram publication failed"
    if status != item["status"] or error != item.get("error_message"):
        with db.conn() as con:
            con.execute("UPDATE miniapp_admin_signal_requests SET status=?,error_message=?,updated_at=? WHERE id=?",
                        (status, error, db.now_iso(), int(item["id"])))
    item.update({"status": status, "error_message": error,
                 "signal": dict(signal) if signal else None, "chart_job": dict(job) if job else None,
                 "live": _admin_live_signal(signal)})
    if signal:
        item["targets"] = [float(target["price"]) for target in db.get_signal_targets(int(signal["id"]))]
    return item


@router.get("/bootstrap")
def bootstrap(x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data")):
    user = _admin(x_telegram_init_data)
    return {
        "ok": True,
        "user": user,
        "mt5_admin": _admin_mt5_status(),
        "destinations": ["FREE", "VIP", "BOTH"],
        "timeframes": ["M1", "M5", "M15", "M30", "H1", "H4"],
        "setup_modes": ["MANUAL", "AUTO"],
        "level_modes": ["AUTO", "MANUAL"],
        "volume_modes": ["RISK", "FIXED"],
        "symbol_catalog": _symbol_catalog(),
        "trailing_profiles": _trailing_catalog(),
    }


@router.post("/signals/calculate")
def calculate(req: CalculateRequest, x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data")):
    _admin(x_telegram_init_data)
    try:
        return calculate_signal_levels(
            req.symbol, req.direction, req.entry,
            stop_loss=req.stop_loss,
            stop_loss_mode=req.stop_loss_mode,
            stop_distance=req.stop_distance,
            take_profit_mode=req.take_profit_mode,
            targets=req.targets,
            digits=req.digits,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/signals", status_code=201)
def create_signal(req: CreateSignalRequest, x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data")):
    user = _admin(x_telegram_init_data)
    init_miniapp_admin_schema()
    with db.conn() as con:
        existing = con.execute("SELECT * FROM miniapp_admin_signal_requests WHERE request_id=?", (req.request_id,)).fetchone()
    if existing:
        result = _sync_request(existing); result["idempotent"] = True
        return result
    try:
        calc = calculate_signal_levels(
            req.symbol, req.direction, req.entry,
            stop_loss=req.stop_loss,
            stop_loss_mode=req.stop_loss_mode,
            stop_distance=req.stop_distance,
            take_profit_mode=req.take_profit_mode,
            targets=req.targets,
            digits=req.digits,
        )
        volume_mode, risk_percent, lot_size = _resolve_sizing(req)
        trailing_code, trailing_name, trailing_config = _resolve_trailing(req)
        mt5 = _admin_mt5_status()
        account = str(mt5.get("account_number") or "").strip()
        if not account:
            raise ValueError("NEXUS_ADMIN_MT5_ACCOUNTS is not configured")
        token = f"MINIAPP:{int(user['id'])}:{req.request_id}"
        rr_ratio = max(float(value) for value in calc["target_multipliers"])
        row = db.create_signal(
            market_type=infer_category(calc["symbol"]), symbol=calc["symbol"], direction=calc["direction"],
            entry_price=calc["entry"], stop_loss=calc["stop_loss"], targets=calc["targets"],
            risk_percent=risk_percent, rr_ratio=rr_ratio, destination=req.destination, chart_file_id=None,
            created_by=int(user["id"]), timeframe=req.timeframe, order_type="MARKET",
            volume_mode=volume_mode, lot_size=lot_size, publish_token=token,
            trailing_code=trailing_code, trailing_name=trailing_name, trailing_config=trailing_config,
        )
        with db.conn() as con:
            con.execute(
                "UPDATE signals SET signal_uuid=COALESCE(signal_uuid,?),issuer_type='WEB_ADMIN',issuer_account=?,"
                "issued_at=COALESCE(issued_at,?),status='DRAFT',publication_stage='WAITING_FOR_CHART' WHERE id=?",
                (str(uuid.uuid4()), account, db.now_iso(), int(row["id"])),
            )
        job = db.create_chart_capture_job(int(row["id"]), f"MINIAPP_ADMIN:{int(user['id'])}")
        status = "READY" if mt5["online"] else "WAITING_FOR_MT5"
        payload = {
            **calc,
            "setup_mode": req.setup_mode,
            "destination": req.destination,
            "timeframe": req.timeframe,
            "mt5_account": account,
            "volume_mode": volume_mode,
            "risk_percent": risk_percent,
            "lot_size": lot_size,
            "trailing_enabled": bool(req.trailing_enabled),
            "trailing_profile_code": req.trailing_profile_code,
            "trailing_code": trailing_code,
            "trailing_config": trailing_config,
        }
        with db.conn() as con:
            con.execute(
                "INSERT OR IGNORE INTO miniapp_admin_signal_requests(request_id,admin_telegram_id,signal_id,status,error_message,payload_json,created_at,updated_at) VALUES(?,?,?,?,NULL,?,?,?)",
                (req.request_id, int(user["id"]), int(row["id"]), status, json.dumps(payload, ensure_ascii=False), db.now_iso(), db.now_iso()),
            )
            request_row = con.execute("SELECT * FROM miniapp_admin_signal_requests WHERE request_id=?", (req.request_id,)).fetchone()
        db.add_signal_event(int(row["id"]), "MINIAPP_SIGNAL_CREATED", actor_type="MINIAPP_ADMIN",
                            actor_id=int(user["id"]), request_id=req.request_id, correlation_id=str(row["code"]), payload=payload)
        db.add_signal_event(int(row["id"]), "CHART_JOB_CREATED", actor_type="MINIAPP_ADMIN",
                            actor_id=int(user["id"]), request_id=f"chart-job:{job['id']}", payload={"job_id": int(job["id"]), "account": account})
        result = _sync_request(request_row); result["idempotent"] = False; result["mt5_admin"] = mt5
        return result
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/signals")
def list_signals(limit: int = Query(30, ge=1, le=100), x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data")):
    user = _admin(x_telegram_init_data); init_miniapp_admin_schema()
    with db.conn() as con:
        rows = con.execute("SELECT * FROM miniapp_admin_signal_requests WHERE admin_telegram_id=? ORDER BY id DESC LIMIT ?", (int(user["id"]), limit)).fetchall()
    return {"items": [_sync_request(row) for row in rows], "mt5_admin": _admin_mt5_status()}


@router.get("/signals/{request_id}")
def signal_status(request_id: str, x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data")):
    user = _admin(x_telegram_init_data); init_miniapp_admin_schema()
    with db.conn() as con:
        row = con.execute("SELECT * FROM miniapp_admin_signal_requests WHERE request_id=? AND admin_telegram_id=?", (request_id, int(user["id"]))).fetchone()
    if not row:
        raise HTTPException(404, "signal request not found")
    return _sync_request(row)


@router.post("/signals/{request_id}/retry")
def retry(request_id: str, background_tasks: BackgroundTasks,
          x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data")):
    user = _admin(x_telegram_init_data); init_miniapp_admin_schema()
    with db.conn() as con:
        row = con.execute("SELECT * FROM miniapp_admin_signal_requests WHERE request_id=? AND admin_telegram_id=?", (request_id, int(user["id"]))).fetchone()
    if not row or not row["signal_id"]:
        raise HTTPException(404, "signal request not found")
    try:
        signal = db.get_signal(int(row["signal_id"]))
        existing_job = db.get_signal_chart_capture_job(int(row["signal_id"]))
        already_published = bool(signal and str(signal["publication_stage"] or "").upper() == "PUBLISHED")
        if (signal and existing_job and not already_published
                and str(existing_job["status"] or "").upper() in {"UPLOADED", "COMPLETED"}):
            from .autotrade.api import _publish_mt5_admin_signal_async
            with db.conn() as con:
                con.execute("UPDATE signals SET publication_stage='CHART_RECEIVED' WHERE id=?", (int(row["signal_id"]),))
                con.execute("UPDATE miniapp_admin_signal_requests SET status='SCREENSHOT_READY',error_message=NULL,updated_at=? WHERE id=?",
                            (db.now_iso(), int(row["id"])))
            background_tasks.add_task(_publish_mt5_admin_signal_async, signal, None)
            return {"ok": True, "status": "SCREENSHOT_READY", "chart_job": dict(existing_job),
                    "publication": "RETRY_QUEUED"}
        job = db.retry_chart_capture_job(int(row["signal_id"]))
        status = "READY" if _admin_mt5_status()["online"] else "WAITING_FOR_MT5"
        with db.conn() as con:
            con.execute("UPDATE signals SET publication_stage='WAITING_FOR_CHART' WHERE id=?", (int(row["signal_id"]),))
            con.execute("UPDATE miniapp_admin_signal_requests SET status=?,error_message=NULL,updated_at=? WHERE id=?", (status, db.now_iso(), int(row["id"])))
        return {"ok": True, "status": status, "chart_job": dict(job)}
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/positions")
def positions(x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data")):
    _admin(x_telegram_init_data)
    mt5 = _admin_mt5_status(); account = mt5.get("account_number")
    live_positions = db.mt5_live_positions(account, nexus_only=True) if account else []
    live_orders = db.mt5_live_orders(account, nexus_only=True) if account else []
    return {"mt5_admin": mt5,
            "positions": db.enrich_mt5_live_signals(live_positions, account) if account else [],
            "orders": db.enrich_mt5_live_signals(live_orders, account) if account else []}


@router.post("/signals/{signal_id}/command")
def command(signal_id: int, req: PositionCommandRequest, x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data")):
    user = _admin(x_telegram_init_data)
    action = req.command.strip().upper()
    if action not in VALID_COMMANDS:
        raise HTTPException(422, "invalid position command")
    row = db.get_signal(signal_id)
    if not row or str(row["issuer_type"] or "").upper() not in {"MT5_ADMIN", "WEB_ADMIN"}:
        raise HTTPException(404, "managed signal not found")
    if str(row["issuer_account"] or "") != req.account_number:
        raise HTTPException(409, "MT5 account does not own this signal")
    command_id = db.create_autotrade_command(signal_id, action, {"value": req.value} if req.value else {},
        actor_type="MINIAPP_ADMIN", actor_id=int(user["id"]), account_number=req.account_number)
    return {"ok": True, "command_id": command_id, "command": action}
