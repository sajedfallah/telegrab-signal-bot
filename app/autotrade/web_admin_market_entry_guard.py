from __future__ import annotations

import logging
import math
from typing import Any

from fastapi import HTTPException

log = logging.getLogger("nexus.web_admin_market_entry_guard")

_ROUTE_PATH = "/miniapp/api/admin/signals"


def _entry_truth_check(*, entry: float, direction: str, bid: float, ask: float, digits: int) -> dict[str, Any]:
    """Validate a MARKET entry against a fresh authenticated MT5 side quote."""
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
    # Tight enough to reject NX-55-scale drift while tolerating a small delay
    # between tapping Market Price and pressing Publish. No guessed broker price.
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
        "deferred": False,
    }


def _validate_request_market_entry(req: Any, init_data: str | None) -> dict[str, Any]:
    """Validate now when a fresh quote exists; otherwise preserve offline queueing.

    The existing WEB_ADMIN execution bridge remains the broker execution gate.
    If no authenticated <=15s Bid/Ask quote exists yet, we deliberately do not
    invent or substitute a price. The request may stay queued until MT5 is back.
    """
    from ..miniapp_admin_api import _digits_for, market_quote

    symbol = str(getattr(req, "symbol", "") or "").strip()
    direction = str(getattr(req, "direction", "") or "").strip().upper()
    entry = float(getattr(req, "entry", 0) or 0)
    requested_digits = getattr(req, "digits", None)
    digits = _digits_for(symbol, requested_digits)

    try:
        quote = market_quote(symbol=symbol, x_telegram_init_data=init_data)
    except HTTPException as exc:
        if int(exc.status_code) != 503:
            raise
        return {
            "ok": None,
            "deferred": True,
            "status": "DEFERRED_NO_FRESH_QUOTE",
            "entry": entry,
            "side": direction,
            "digits": digits,
            "reason": str(exc.detail),
        }

    check = _entry_truth_check(
        entry=entry,
        direction=direction,
        bid=float(quote["bid"]),
        ask=float(quote["ask"]),
        digits=digits,
    )
    check["quote_age_seconds"] = quote.get("age_seconds")
    check["quote_source"] = quote.get("source")
    check["status"] = "VALIDATED_FRESH_MT5_QUOTE"

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
    """Wrap the final WEB_ADMIN create route without changing execution logic.

    Install this *after* the Mini App execution runtime, because that runtime
    replaces the same POST route. Fresh authenticated MT5 quotes are enforced
    immediately; absence of a quote preserves the existing offline queue rather
    than manufacturing a price or breaking recovery/retry behavior.
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
        check = _validate_request_market_entry(req, init_data)
        result = original_call(*args, **kwargs)
        if isinstance(result, dict):
            result = dict(result)
            result["entry_truth"] = check
        return result

    target_route.dependant.call = guarded_create_signal
    target_route.endpoint = guarded_create_signal
    app.state.nexus_web_admin_market_entry_guard_v31 = True
    log.info("WEB_ADMIN MARKET entry truth guard installed on final route %s", _ROUTE_PATH)
