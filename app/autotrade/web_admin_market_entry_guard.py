from __future__ import annotations

import logging
import math
from typing import Any

from fastapi import HTTPException

log = logging.getLogger("nexus.web_admin_market_entry_guard")

_ROUTE_PATH = "/miniapp/api/admin/signals"


def _entry_truth_check(*, entry: float, direction: str, bid: float, ask: float, digits: int) -> dict[str, Any]:
    """Validate a MARKET entry against the fresh authenticated MT5 side quote.

    The guard deliberately rejects stale/manual prices instead of moving the
    submitted entry. This keeps the Admin preview, stored signal, execution and
    publication chart on one broker-truth price contract.
    """
    entry_f = float(entry)
    bid_f = float(bid)
    ask_f = float(ask)
    side = str(direction or "").strip().upper()
    precision = max(0, min(int(digits), 8))

    if side not in {"BUY", "SELL"}:
        raise ValueError("direction must be BUY or SELL")
    if not all(math.isfinite(v) and v > 0 for v in (entry_f, bid_f, ask_f)) or bid_f > ask_f:
        raise ValueError("invalid MT5 quote")

    market_price = ask_f if side == "BUY" else bid_f
    spread = max(0.0, ask_f - bid_f)
    tick = 10.0 ** (-precision)
    # Tight enough to prevent the large visual/data drift seen on NX-55, while
    # allowing a few ticks / a few spreads between tapping Market Price and
    # pressing Publish. No symbol-specific guessed price is introduced.
    tolerance = max(tick * 10.0, spread * 3.0, abs(market_price) * 0.00005)
    deviation = abs(entry_f - market_price)

    return {
        "ok": deviation <= tolerance,
        "entry": entry_f,
        "market_price": market_price,
        "bid": bid_f,
        "ask": ask_f,
        "spread": spread,
        "digits": precision,
        "deviation": deviation,
        "tolerance": tolerance,
        "side": side,
    }


def _validate_request_market_entry(req: Any, init_data: str | None) -> dict[str, Any]:
    # Import lazily so the already-registered Admin router remains untouched.
    from ..miniapp_admin_api import _digits_for, market_quote

    symbol = str(getattr(req, "symbol", "") or "").strip()
    direction = str(getattr(req, "direction", "") or "").strip().upper()
    entry = float(getattr(req, "entry", 0) or 0)
    requested_digits = getattr(req, "digits", None)
    digits = _digits_for(symbol, requested_digits)

    # market_quote is already fail-closed: authenticated Admin heartbeat only,
    # Bid/Ask only, timezone-aware capture and <=15s freshness.
    quote = market_quote(symbol=symbol, x_telegram_init_data=init_data)
    check = _entry_truth_check(
        entry=entry,
        direction=direction,
        bid=float(quote["bid"]),
        ask=float(quote["ask"]),
        digits=digits,
    )
    check["quote_age_seconds"] = quote.get("age_seconds")
    check["quote_source"] = quote.get("source")

    if not check["ok"]:
        raise HTTPException(
            status_code=409,
            detail=(
                "MARKET entry is out of sync with the fresh MT5 price. "
                f"entry={entry:.{digits}f}, {direction} market={check['market_price']:.{digits}f}, "
                f"deviation={check['deviation']:.{digits}f}, allowed={check['tolerance']:.{digits}f}. "
                "Refresh Market Price and publish again."
            ),
        )
    return check


def install_web_admin_market_entry_guard(app) -> None:
    """Fail closed before a WEB_ADMIN MARKET signal can store a stale entry.

    The current Admin Mini App creates MARKET orders only. Historically it also
    accepted arbitrary manual entry text, which allowed a signal such as NX-55
    to store 4291 while the authenticated MT5 market was around 4283. The chart
    renderer correctly exposed that discrepancy. This guard fixes the creation
    contract instead of falsifying chart candles or moving historical levels.
    """
    if getattr(app.state, "nexus_web_admin_market_entry_guard_v31", False):
        return

    target_route = None
    for route in app.routes:
        methods = set(getattr(route, "methods", set()) or set())
        if getattr(route, "path", None) == _ROUTE_PATH and "POST" in methods:
            target_route = route
            break

    if target_route is None:
        raise RuntimeError(f"Admin signal creation route not found: {_ROUTE_PATH}")

    original_call = target_route.dependant.call

    def guarded_create_signal(*args, **kwargs):
        req = kwargs.get("req")
        init_data = kwargs.get("x_telegram_init_data")
        if req is None:
            raise HTTPException(status_code=422, detail="missing Admin signal request")
        _validate_request_market_entry(req, init_data)
        return original_call(*args, **kwargs)

    target_route.dependant.call = guarded_create_signal
    target_route.endpoint = guarded_create_signal
    app.state.nexus_web_admin_market_entry_guard_v31 = True
    log.info("WEB_ADMIN MARKET entry truth guard installed on %s", _ROUTE_PATH)
