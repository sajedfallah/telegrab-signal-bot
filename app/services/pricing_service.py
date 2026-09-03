from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from decimal import Decimal, ROUND_CEILING, InvalidOperation
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

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


@dataclass(frozen=True)
class RateProvider:
    code: str
    title: str
    url: str
    quote_unit: str = "IRR"


PROVIDER_PRESETS: dict[str, RateProvider] = {
    "nobitex": RateProvider(
        "nobitex",
        "Nobitex",
        "https://api.nobitex.ir/v3/orderbook/USDTIRT",
        "IRR",
    ),
    "wallex": RateProvider(
        "wallex",
        "Wallex",
        "https://api.wallex.ir/v1/depth?symbol=USDTTMN",
        "TMN",
    ),
    "international": RateProvider(
        "international",
        "CoinGecko International",
        "https://api.coingecko.com/api/v3/simple/price?ids=tether&vs_currencies=irr",
        "IRR",
    ),
}


def money_usdt(value: Any) -> Decimal:
    try:
        return Decimal(str(value)).quantize(Q2)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise PricingError("invalid USDT amount") from exc


def ceil_rial(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_CEILING))


def _decimal(value: Any) -> Decimal | None:
    try:
        parsed = Decimal(str(value))
    except Exception:
        return None
    return parsed if parsed > 0 else None


def _first_book_price(rows: Any) -> Decimal | None:
    if not rows or not isinstance(rows, (list, tuple)):
        return None
    first = rows[0]
    if isinstance(first, dict):
        for key in ("price", "rate", "last", "lastPrice"):
            value = _decimal(first.get(key))
            if value is not None:
                return value
    if isinstance(first, (list, tuple)) and first:
        return _decimal(first[0])
    return None


def _parse_provider_payload(payload: Any) -> Decimal:
    if isinstance(payload, dict):
        # CoinGecko simple-price payload: {"tether": {"irr": 12345}}
        tether = payload.get("tether")
        if isinstance(tether, dict):
            value = _decimal(tether.get("irr"))
            if value is not None:
                return value

        for key in ("lastTradePrice", "last", "price", "rate", "last_price", "lastPrice"):
            value = _decimal(payload.get(key))
            if value is not None:
                return value

        # Nobitex commonly returns asks/bids as arrays. Wallex returns result.ask/result.bid
        # where each item is a dict containing a price field.
        for key in ("asks", "ask", "bids", "bid"):
            value = _first_book_price(payload.get(key))
            if value is not None:
                return value

        for key in ("data", "result", "ticker"):
            if key in payload:
                try:
                    return _parse_provider_payload(payload[key])
                except PricingError:
                    pass
    raise PricingError("USDT/RIAL provider returned an unsupported response")


def _configured_source() -> str:
    return (db.get_setting("usdt_rial_rate_source", settings.usdt_rial_rate_source).strip().lower() or "nobitex")


def _configured_secondary(primary: str) -> str:
    configured = db.get_setting("usdt_rial_secondary_source", "").strip().lower()
    if configured and configured != primary:
        return configured
    if primary == "nobitex":
        return "wallex"
    if primary == "wallex":
        return "nobitex"
    return "nobitex"


def provider_url(source: str) -> str:
    source = (source or "").strip().lower()
    if source == "custom":
        return db.get_setting("usdt_rial_rate_url", settings.usdt_rial_rate_url).strip()
    preset = PROVIDER_PRESETS.get(source)
    if preset:
        return preset.url
    return db.get_setting("usdt_rial_rate_url", settings.usdt_rial_rate_url).strip()


def provider_title(source: str) -> str:
    source = (source or "").strip().lower()
    if source == "custom":
        return "Custom URL"
    preset = PROVIDER_PRESETS.get(source)
    return preset.title if preset else source or "Unknown"


def configure_rate_provider(source: str, *, custom_url: str | None = None, secondary_source: str | None = None) -> None:
    code = (source or "").strip().lower()
    if code not in {*PROVIDER_PRESETS, "custom"}:
        raise PricingError("unsupported USDT/RIAL rate provider")
    if code == "custom":
        url = (custom_url or "").strip()
        if not url.startswith(("https://", "http://")):
            raise PricingError("custom provider URL must use http:// or https://")
        db.set_setting("usdt_rial_rate_url", url)
    else:
        db.set_setting("usdt_rial_rate_url", PROVIDER_PRESETS[code].url)
    db.set_setting("usdt_rial_rate_source", code)

    if secondary_source is not None:
        secondary = secondary_source.strip().lower()
        if secondary not in PROVIDER_PRESETS or secondary == code:
            raise PricingError("invalid secondary USDT/RIAL provider")
        db.set_setting("usdt_rial_secondary_source", secondary)


def _append_query(url: str, **params: str) -> str:
    """Append optional provider parameters without destroying existing query values."""
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update({k: v for k, v in params.items() if v})
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


async def _fetch_provider(source: str, *, url_override: str | None = None) -> RateQuote:
    source = (source or "").strip().lower()
    url = (url_override or provider_url(source)).strip()
    if not url:
        raise PricingError(f"USDT/RIAL provider {source or 'unknown'} is not configured")

    # Keep backward compatibility with old Nobitex v2 settings.
    if source == "nobitex" and "/v2/orderbook/" in url:
        url = PROVIDER_PRESETS["nobitex"].url
    if source == "wallex" and "symbol=" not in url:
        url = _append_query(url, symbol="USDTTMN")
    if source == "international" and "vs_currencies=" not in url:
        url = _append_query(url, ids="tether", vs_currencies="irr")

    timeout = aiohttp.ClientTimeout(total=8)
    headers = {"Accept": "application/json", "User-Agent": "NEXUS/7.1 pricing"}
    try:
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(url) as response:
                response.raise_for_status()
                payload = await response.json(content_type=None)
    except Exception as exc:
        raise PricingError(f"{provider_title(source)} rate request failed") from exc

    rate = _parse_provider_payload(payload)
    if source == "wallex":
        # USDTTMN is quoted in toman; NEXUS invoices store/use IRR.
        rate *= Decimal("10")
    if rate <= 0:
        raise PricingError(f"{provider_title(source)} returned a non-positive rate")
    return RateQuote(rate, source, datetime.now(timezone.utc).isoformat())


def _record_rate_success(quote: RateQuote) -> None:
    db.set_setting("usdt_rial_last_rate", str(quote.rate))
    db.set_setting("usdt_rial_last_rate_at", quote.fetched_at)
    db.set_setting("usdt_rial_last_rate_source", quote.source)
    db.set_setting("usdt_rial_consecutive_failures", "0")
    db.set_setting("usdt_rial_last_error", "")
    db.set_setting("usdt_rial_failure_alerted", "0")


def _record_rate_failure(message: str) -> int:
    raw = db.get_setting("usdt_rial_consecutive_failures", "0").strip()
    try:
        count = max(0, int(raw)) + 1
    except Exception:
        count = 1
    db.set_setting("usdt_rial_consecutive_failures", str(count))
    db.set_setting("usdt_rial_last_failure_at", datetime.now(timezone.utc).isoformat())
    db.set_setting("usdt_rial_last_error", str(message)[:1000])
    return count


async def refresh_usdt_rial_rate() -> RateQuote:
    """Fetch a fresh rate from primary, then secondary, and persist health state.

    Manual overrides are intentionally not treated as provider refreshes. When a
    manual override exists, invoice pricing uses it, while this function can still
    be called by the monitor to verify that automated providers are healthy.
    """
    primary = _configured_source()
    if primary == "custom":
        candidates = [("custom", provider_url("custom")), (_configured_secondary(primary), None)]
    else:
        candidates = [(primary, None), (_configured_secondary(primary), None)]

    seen: set[str] = set()
    errors: list[str] = []
    for source, url_override in candidates:
        source = (source or "").strip().lower()
        if not source or source in seen:
            continue
        seen.add(source)
        try:
            quote = await _fetch_provider(source, url_override=url_override)
            if source != primary:
                quote = RateQuote(quote.rate, f"fallback:{source}", quote.fetched_at)
            _record_rate_success(quote)
            return quote
        except Exception as exc:
            errors.append(f"{source}: {exc}")

    detail = " | ".join(errors) or "no rate provider configured"
    count = _record_rate_failure(detail)
    raise PricingError(f"all USDT/RIAL providers failed (consecutive failures={count}): {detail}")


def _manual_quote() -> RateQuote | None:
    manual = db.get_setting("usdt_rial_manual_rate", "").strip()
    if not manual:
        return None
    rate = _decimal(manual)
    if rate is None:
        return None
    return RateQuote(rate, "manual_override", datetime.now(timezone.utc).isoformat())


def _last_good_quote(*, source_prefix: str = "last_good") -> RateQuote | None:
    cached = db.get_setting("usdt_rial_last_rate", "").strip()
    cached_at = db.get_setting("usdt_rial_last_rate_at", "").strip()
    cached_source = db.get_setting("usdt_rial_last_rate_source", "unknown").strip() or "unknown"
    rate = _decimal(cached)
    if rate is None or not cached_at:
        return None
    try:
        datetime.fromisoformat(cached_at)
    except Exception:
        return None
    return RateQuote(rate, f"{source_prefix}:{cached_source}", cached_at)


async def fetch_usdt_rial_rate() -> RateQuote:
    """Compatibility entry point: return the best usable business rate.

    Order: manual override -> fresh primary/secondary -> last valid rate. The last
    valid rate is explicitly labelled so the admin UI can show that it is stale.
    Provider failure counters are still incremented by refresh_usdt_rial_rate().
    """
    manual = _manual_quote()
    if manual:
        return manual
    try:
        return await refresh_usdt_rial_rate()
    except PricingError:
        fallback = _last_good_quote(source_prefix="last_good")
        if fallback:
            return fallback
        raise PricingError(
            "USDT/RIAL rate is unavailable and no last valid rate exists. "
            "Set a manual rate in Admin → Pricing Settings or restore a configured provider."
        )


async def get_usdt_rial_rate() -> RateQuote:
    quote = await fetch_usdt_rial_rate()
    if quote.source == "manual_override":
        # Keep the provider's last-good sample untouched while a temporary manual
        # override is active; only expose the manual rate to the current invoice.
        return quote
    if not quote.source.startswith("last_good:"):
        # refresh_usdt_rial_rate already persisted the fresh/fallback sample.
        _record_rate_success(quote)
    return quote


def rate_health() -> dict[str, Any]:
    primary = _configured_source()
    secondary = _configured_secondary(primary)
    try:
        failures = max(0, int(db.get_setting("usdt_rial_consecutive_failures", "0") or 0))
    except Exception:
        failures = 0
    return {
        "primary": primary,
        "primary_title": provider_title(primary),
        "primary_url": provider_url(primary),
        "secondary": secondary,
        "secondary_title": provider_title(secondary),
        "manual_override": db.get_setting("usdt_rial_manual_rate", "").strip(),
        "last_rate": db.get_setting("usdt_rial_last_rate", "").strip(),
        "last_rate_at": db.get_setting("usdt_rial_last_rate_at", "").strip(),
        "last_rate_source": db.get_setting("usdt_rial_last_rate_source", "").strip(),
        "consecutive_failures": failures,
        "last_failure_at": db.get_setting("usdt_rial_last_failure_at", "").strip(),
        "last_error": db.get_setting("usdt_rial_last_error", "").strip(),
    }


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

    proration_enabled = db.get_setting("upgrade_proration_enabled", "true").strip().lower() in {"1", "true", "yes", "on"}

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
