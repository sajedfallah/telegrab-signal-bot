from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from fastapi import Header, Query
from fastapi.routing import APIRoute

from .. import db
from ..autotrade.symbol_registry import normalize_symbol
from ..market_candles import init_market_candle_schema

log = logging.getLogger("nexus-market-quote-v32")

_QUOTE_MAX_AGE_SECONDS = 15.0
_QUOTE_FUTURE_SKEW_SECONDS = 5.0
_BROKER_OFFSET_QUANTUM_SECONDS = 15 * 60
_MAX_BROKER_OFFSET_SECONDS = 14 * 60 * 60
_CORRECTED_NEAR_CAPTURE_SECONDS = 2 * 60
_ROUTE_PATH = "/miniapp/api/admin/market-quote"


def _route(app, path: str, method: str) -> APIRoute:
    method = method.upper()
    for candidate in app.router.routes:
        if isinstance(candidate, APIRoute) and candidate.path == path and method in candidate.methods:
            return candidate
    raise RuntimeError(f"NEXUS runtime route not found: {method} {path}")


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def _iso_age_seconds(value: str | None) -> float | None:
    dt = _parse_iso(value)
    if dt is None:
        return None
    return (datetime.now(timezone.utc) - dt).total_seconds()


def _normalize_quote_time_ms(raw_ms: int, captured_at: str | None) -> tuple[int, int | None]:
    """Normalize MT5 broker-server epoch milliseconds against backend receive time.

    Some brokers expose ``MqlTick.time_msc`` using broker-server wall time encoded
    as Unix milliseconds rather than UTC. In the live ePlanet feed this appears
    as an exact +03:00 shift. We only remove a plausible civil-time offset when
    doing so puts the tick close to the authenticated backend capture time.
    Stale ticks remain stale after correction and implausible future values still
    fail closed in ``_fresh_market_feed_quote``.
    """
    captured = _parse_iso(captured_at)
    if captured is None:
        return int(raw_ms), None
    try:
        candidate = datetime.fromtimestamp(int(raw_ms) / 1000.0, tz=timezone.utc)
    except (OSError, OverflowError, ValueError):
        return int(raw_ms), None

    future_seconds = (candidate - captured).total_seconds()
    if future_seconds <= _QUOTE_FUTURE_SKEW_SECONDS:
        return int(raw_ms), None
    if future_seconds > _MAX_BROKER_OFFSET_SECONDS + _QUOTE_FUTURE_SKEW_SECONDS:
        return int(raw_ms), None

    inferred_offset = int(round(future_seconds / _BROKER_OFFSET_QUANTUM_SECONDS)) * _BROKER_OFFSET_QUANTUM_SECONDS
    if not (_BROKER_OFFSET_QUANTUM_SECONDS <= inferred_offset <= _MAX_BROKER_OFFSET_SECONDS):
        return int(raw_ms), None

    corrected = candidate - timedelta(seconds=inferred_offset)
    if abs((corrected - captured).total_seconds()) > _CORRECTED_NEAR_CAPTURE_SECONDS:
        return int(raw_ms), None

    normalized_ms = int(round(corrected.timestamp() * 1000.0))
    return normalized_ms, inferred_offset


def _fresh_market_feed_quote(account: str, symbol: str) -> dict[str, Any] | None:
    init_market_candle_schema()
    canonical = normalize_symbol(symbol)
    with db.conn() as con:
        row = con.execute(
            """SELECT account_number,symbol,broker_symbol,bid,ask,digits,quote_time_ms,captured_at
               FROM mt5_market_quotes
               WHERE account_number=? AND symbol=?
               LIMIT 1""",
            (str(account), canonical),
        ).fetchone()
    if not row:
        return None

    bid = float(row["bid"])
    ask = float(row["ask"])
    if bid <= 0 or ask <= 0 or ask < bid:
        return None

    raw_quote_time_ms = int(row["quote_time_ms"])
    normalized_quote_time_ms, broker_offset_seconds = _normalize_quote_time_ms(
        raw_quote_time_ms,
        str(row["captured_at"] or ""),
    )

    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    quote_age = (now_ms - normalized_quote_time_ms) / 1000.0
    capture_age = _iso_age_seconds(str(row["captured_at"] or ""))
    if quote_age < -_QUOTE_FUTURE_SKEW_SECONDS or quote_age > _QUOTE_MAX_AGE_SECONDS:
        return None
    if capture_age is None or capture_age < -_QUOTE_FUTURE_SKEW_SECONDS or capture_age > _QUOTE_MAX_AGE_SECONDS:
        return None

    if broker_offset_seconds is not None:
        log.info(
            "[NEXUS][MARKET_QUOTE][BROKER_OFFSET_CORRECTED] account=%s symbol=%s offset_seconds=%s raw_ms=%s normalized_ms=%s",
            account,
            canonical,
            broker_offset_seconds,
            raw_quote_time_ms,
            normalized_quote_time_ms,
        )

    return {
        "ok": True,
        "symbol": canonical,
        "broker_symbol": str(row["broker_symbol"] or canonical),
        "bid": bid,
        "ask": ask,
        "digits": int(row["digits"]) if row["digits"] is not None else None,
        "captured_at": str(row["captured_at"]),
        "quote_time_ms": normalized_quote_time_ms,
        "raw_quote_time_ms": raw_quote_time_ms,
        "broker_time_offset_seconds": broker_offset_seconds,
        "age_seconds": round(max(0.0, quote_age), 3),
        "fresh": True,
        "source": "MT5_MARKET_FEED_TICK",
        "account_number": str(row["account_number"]),
    }


def install_market_quote_runtime(app) -> None:
    """Prefer authenticated MarketFeed Bid/Ask while preserving old fallback.

    Market candles are never converted into a synthetic quote. The only new
    source accepted here is a real SymbolInfoTick Bid/Ask sent by the existing
    allow-listed Admin MarketFeed. If that tick is absent/stale, the original
    heartbeat-backed market_quote path remains authoritative and fail-closed.
    """
    if getattr(app.state, "nexus_market_quote_runtime_v32", False):
        return

    from .. import miniapp_admin_api as mini

    route = _route(app, _ROUTE_PATH, "GET")
    original_call: Callable[..., Any] = route.dependant.call

    def market_quote(
        symbol: str = Query(min_length=3, max_length=32),
        x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
    ):
        mini._admin(x_telegram_init_data)
        mt5 = mini._admin_mt5_status()
        account = str(mt5.get("account_number") or "").strip()
        if account:
            quote = _fresh_market_feed_quote(account, symbol)
            if quote is not None:
                return quote
        return original_call(symbol=symbol, x_telegram_init_data=x_telegram_init_data)

    # V31 imports miniapp_admin_api.market_quote lazily on every validation, so
    # patching both the module symbol and registered FastAPI route keeps the
    # Market Price button and Publish guard on the exact same Bid/Ask contract.
    mini.market_quote = market_quote
    route.endpoint = market_quote
    route.dependant.call = market_quote
    app.state.nexus_market_quote_runtime_v32 = True
