from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from decimal import Decimal, ROUND_CEILING, InvalidOperation
from typing import Any

import aiohttp

from .. import db
from ..config import settings


Q2 = Decimal("0.01")


class PricingError(RuntimeError):
    pass


@dataclass(frozen=True)
class RateQuote:
    rate: Decimal
    source: str
    fetched_at: str


def money_usdt(value: Any) -> Decimal:
    try:
        return Decimal(str(value)).quantize(Q2)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise PricingError("invalid USDT amount") from exc


def ceil_rial(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_CEILING))


def _parse_provider_payload(payload: Any) -> Decimal:
    if isinstance(payload, dict):
        for key in ("lastTradePrice", "last", "price", "rate", "last_price"):
            if key in payload:
                try:
                    return Decimal(str(payload[key]))
                except Exception:
                    pass
        for key in ("data", "result", "ticker"):
            if key in payload:
                try:
                    return _parse_provider_payload(payload[key])
                except Exception:
                    pass
        asks = payload.get("asks")
        bids = payload.get("bids")
        if asks:
            try:
                return Decimal(str(asks[0][0]))
            except Exception:
                pass
        if bids:
            try:
                return Decimal(str(bids[0][0]))
            except Exception:
                pass
    raise PricingError("USDT/RIAL provider returned an unsupported response")


async def fetch_usdt_rial_rate() -> RateQuote:
    manual = db.get_setting("usdt_rial_manual_rate", "").strip()
    if manual:
        try:
            rate = Decimal(manual)
            if rate > 0:
                return RateQuote(rate, "manual_override", datetime.now(timezone.utc).isoformat())
        except Exception:
            pass

    source = db.get_setting("usdt_rial_rate_source", settings.usdt_rial_rate_source).strip().lower() or "nobitex"
    url = db.get_setting("usdt_rial_rate_url", settings.usdt_rial_rate_url).strip()
    if source == "nobitex" and (not url or "/v2/orderbook/" in url):
        # Nobitex marks v2 orderbook as deprecated; v3 is the current documented endpoint.
        url = "https://api.nobitex.ir/v3/orderbook/USDTIRT"
    if not url:
        raise PricingError("USDT/RIAL rate provider is not configured")

    timeout = aiohttp.ClientTimeout(total=8)
    headers = {"Accept": "application/json", "User-Agent": "NEXUS/7.1 pricing"}
    try:
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(url) as response:
                response.raise_for_status()
                payload = await response.json(content_type=None)
        rate = _parse_provider_payload(payload)
        if rate <= 0:
            raise PricingError("provider returned a non-positive USDT/RIAL rate")
        return RateQuote(rate, source, datetime.now(timezone.utc).isoformat())
    except Exception as exc:
        cached = db.get_setting("usdt_rial_last_rate", "").strip()
        cached_at = db.get_setting("usdt_rial_last_rate_at", "").strip()
        try:
            if cached and cached_at:
                age = datetime.now(timezone.utc) - datetime.fromisoformat(cached_at)
                if age <= timedelta(seconds=max(30, settings.usdt_rial_cache_seconds)):
                    return RateQuote(Decimal(cached), "cached:" + source, cached_at)
        except Exception:
            pass
        raise PricingError(
            "USDT/RIAL rate is temporarily unavailable. "
            "Set a valid manual rate in Admin → Pricing Settings, "
            "or restore access to the configured rate provider."
        ) from exc


async def get_usdt_rial_rate() -> RateQuote:
    quote = await fetch_usdt_rial_rate()
    db.set_setting("usdt_rial_last_rate", str(quote.rate))
    db.set_setting("usdt_rial_last_rate_at", quote.fetched_at)
    db.set_setting("usdt_rial_last_rate_source", quote.source)
    return quote


def discounted_usdt(base: Decimal, discount_percent: Decimal = Decimal("0")) -> Decimal:
    pct = max(Decimal("0"), min(Decimal("100"), Decimal(discount_percent)))
    return money_usdt(base * (Decimal("100") - pct) / Decimal("100"))


def plan_setup_fee(plan: dict[str, Any]) -> Decimal:
    return money_usdt(plan.get("setup_fee_usdt", "0"))


def remaining_credit(active_plan: dict[str, Any] | None, expires_at: str | None) -> Decimal:
    if not active_plan or not expires_at:
        return Decimal("0")
    try:
        exp = datetime.fromisoformat(str(expires_at))
        remaining_days = max(0, (exp - datetime.now(timezone.utc)).total_seconds() / 86400)
        duration = max(1, int(active_plan.get("days") or active_plan.get("duration_days") or 1))
        price = money_usdt(active_plan.get("usdt", active_plan.get("price_usdt", "0")))
        return money_usdt(price * Decimal(str(remaining_days)) / Decimal(duration))
    except Exception:
        return Decimal("0")


def quote_purchase(user_id: int, plan_code: str, discount_percent: Decimal = Decimal("0")) -> dict[str, Any]:
    plan = db.get_plan(plan_code, active_only=True)
    if not plan:
        raise PricingError("plan is inactive or does not exist")
    plan_dict = db.plan_dict(plan)
    base = discounted_usdt(money_usdt(plan_dict["usdt"]), discount_percent)
    setup = plan_setup_fee(plan_dict)
    access = db.current_entitlements(user_id)
    active_plan = db.get_plan(str(access["plan_code"])) if access.get("plan_code") else None
    active_dict = db.plan_dict(active_plan) if active_plan else None
    mode = "new"
    credit = Decimal("0")
    plan_vip = bool(plan_dict.get("vip_access"))
    plan_auto = bool(plan_dict.get("autotrade_access"))
    current_vip = bool(access.get("vip"))
    current_auto = bool(access.get("autotrade"))

    proration_enabled = db.get_setting("upgrade_proration_enabled", "true").strip().lower() in {"1","true","yes","on"}

    if plan_vip and not plan_auto:  # VIP-only
        if current_vip:
            mode = "extend"
        elif current_auto:
            mode = "add_vip"
    elif plan_auto and not plan_vip:  # standalone AutoTrade Expert
        if current_auto:
            mode = "extend"
        elif current_vip:
            mode = "add_auto"
    elif plan_vip and plan_auto:  # Bundle
        if current_vip and current_auto:
            mode = "extend"
        elif current_vip:
            mode = "upgrade"
            if proration_enabled:
                credit = remaining_credit(active_dict, access.get("vip_expires_at"))
        elif current_auto:
            mode = "upgrade"
            if proration_enabled:
                credit = remaining_credit(active_dict, access.get("autotrade_expires_at"))

    if mode == "extend" and plan_dict["service_type"] == "auto_trade":
        # Setup & Activation is an initial activation fee, not a recurring renewal fee.
        setup = Decimal("0")
    total = max(Decimal("0"), base + setup - credit)
    return {
        "plan": plan_dict,
        "mode": mode,
        "base_usdt": base,
        "setup_fee_usdt": setup,
        "upgrade_credit_usdt": money_usdt(credit),
        "total_usdt": money_usdt(total),
        "duration_days": int(plan_dict["days"]),
        "discount_percent": Decimal(discount_percent),
    }


async def create_invoice_quote(user_id: int, plan_code: str, payment_method: str, discount_percent: Decimal = Decimal("0"), *, invoice_type: str | None = None) -> dict[str, Any]:
    quote = quote_purchase(user_id, plan_code, discount_percent)
    method = payment_method.lower().strip()
    if method not in {"usdt", "rial"}:
        raise PricingError("unsupported payment method")
    if method == "usdt":
        rate = None
        final_rial = None
        ttl = max(1, int(db.get_setting("rial_invoice_ttl_minutes", str(settings.rial_invoice_ttl_minutes))))
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=ttl)
    else:
        rate_quote = await get_usdt_rial_rate()
        rate = rate_quote.rate
        final_rial = ceil_rial(quote["total_usdt"] * rate)
        ttl = max(1, int(db.get_setting("rial_invoice_ttl_minutes", str(settings.rial_invoice_ttl_minutes))))
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=ttl)
    inv_type = invoice_type or {
        "new": "subscription",
        "extend": "renewal",
        "upgrade": "upgrade",
        "add_vip": "addon",
        "add_auto": "addon",
    }[quote["mode"]]
    invoice_id = db.create_invoice(
        user_id=user_id,
        plan_id=int(quote["plan"]["id"]),
        invoice_type=inv_type,
        payment_method=method,
        base_amount_usdt=quote["total_usdt"],
        usdt_rial_rate=rate,
        final_amount_rial=final_rial,
        wallet_network=settings.usdt_network if method == "usdt" else None,
        wallet_address=settings.usdt_wallet if method == "usdt" else None,
        expires_at=expires_at.isoformat(),
        quote_json=json.dumps({k: str(v) if isinstance(v, Decimal) else v for k, v in quote.items() if k != "plan"} | {"plan": quote["plan"]}, ensure_ascii=False, default=str),
    )
    return {**quote, "invoice_id": invoice_id, "payment_method": method, "usdt_rial_rate": rate, "final_amount_rial": final_rial, "expires_at": expires_at.isoformat()}


def invoice_is_valid(invoice: Any) -> bool:
    if not invoice or str(invoice["payment_status"]) != "pending":
        return False
    try:
        return datetime.fromisoformat(str(invoice["expires_at"])) > datetime.now(timezone.utc)
    except Exception:
        return False
