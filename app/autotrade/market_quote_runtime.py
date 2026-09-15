from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import Header, Query
from fastapi.routing import APIRoute

from .. import db
from ..autotrade.symbol_registry import normalize_symbol
from ..market_candles import init_market_candle_schema

_QUOTE_MAX_AGE_SECONDS = 15.0
_QUOTE_FUTURE_SKEW_SECONDS = 5.0
_ROUTE_PATH = "/miniapp/api/admin/market-quote"


def _route(app, path: str, method: str) -> APIRoute:
    method = method.upper()
    for candidate in app.router.routes:
        if isinstance(candidate, APIRoute) and candidate.path == path and method in candidate.methods:
            return candidate
    raise RuntimeError(f"NEXUS runtime route not found: {method} {path}")


def _iso_age_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds()
    except ValueError:
        return None


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

    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    quote_age = (now_ms - int(row["quote_time_ms"])) / 1000.0
    capture_age = _iso_age_seconds(str(row["captured_at"] or ""))
    if quote_age < -_QUOTE_FUTURE_SKEW_SECONDS or quote_age > _QUOTE_MAX_AGE_SECONDS:
        return None
    if capture_age is None or capture_age < -_QUOTE_FUTURE_SKEW_SECONDS or capture_age > _QUOTE_MAX_AGE_SECONDS:
        return None

    return {
        "ok": True,
        "symbol": canonical,
        "broker_symbol": str(row["broker_symbol"] or canonical),
        "bid": bid,
        "ask": ask,
        "digits": int(row["digits"]) if row["digits"] is not None else None,
        "captured_at": str(row["captured_at"]),
        "quote_time_ms": int(row["quote_time_ms"]),
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
