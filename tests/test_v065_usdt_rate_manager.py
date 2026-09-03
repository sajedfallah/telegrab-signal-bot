from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from app.services import pricing_service as pricing


def _fake_settings(monkeypatch):
    values: dict[str, str] = {}

    def get_setting(key: str, default: str = "") -> str:
        return values.get(key, default)

    def set_setting(key: str, value: str) -> None:
        values[key] = str(value)

    monkeypatch.setattr(pricing.db, "get_setting", get_setting)
    monkeypatch.setattr(pricing.db, "set_setting", set_setting)
    return values


def test_provider_presets_have_primary_sources():
    assert pricing.PROVIDER_PRESETS["nobitex"].url.endswith("/v3/orderbook/USDTIRT")
    assert "USDTTMN" in pricing.PROVIDER_PRESETS["wallex"].url
    assert "tether" in pricing.PROVIDER_PRESETS["international"].url


def test_payload_parser_supports_nobitex_wallex_and_coingecko():
    assert pricing._parse_provider_payload({"asks": [["700000", "1"]]}) == Decimal("700000")
    assert pricing._parse_provider_payload({"result": {"ask": [{"price": "70000"}]}}) == Decimal("70000")
    assert pricing._parse_provider_payload({"tether": {"irr": 700000}}) == Decimal("700000")


def test_configure_preset_persists_provider_and_secondary(monkeypatch):
    values = _fake_settings(monkeypatch)
    pricing.configure_rate_provider("wallex", secondary_source="nobitex")
    assert values["usdt_rial_rate_source"] == "wallex"
    assert values["usdt_rial_secondary_source"] == "nobitex"
    assert "USDTTMN" in values["usdt_rial_rate_url"]


def test_custom_provider_requires_http_url(monkeypatch):
    _fake_settings(monkeypatch)
    with pytest.raises(pricing.PricingError):
        pricing.configure_rate_provider("custom", custom_url="not-a-url")


def test_refresh_uses_secondary_and_resets_failure_counter(monkeypatch):
    values = _fake_settings(monkeypatch)
    values["usdt_rial_rate_source"] = "nobitex"
    values["usdt_rial_secondary_source"] = "wallex"
    values["usdt_rial_consecutive_failures"] = "2"

    async def fake_fetch(source: str, *, url_override=None):
        if source == "nobitex":
            raise pricing.PricingError("primary down")
        return pricing.RateQuote(Decimal("710000"), source, "2026-09-03T00:00:00+00:00")

    monkeypatch.setattr(pricing, "_fetch_provider", fake_fetch)
    quote = asyncio.run(pricing.refresh_usdt_rial_rate())

    assert quote.rate == Decimal("710000")
    assert quote.source == "fallback:wallex"
    assert values["usdt_rial_consecutive_failures"] == "0"
    assert values["usdt_rial_last_rate_source"] == "fallback:wallex"


def test_all_provider_failures_increment_counter(monkeypatch):
    values = _fake_settings(monkeypatch)
    values["usdt_rial_rate_source"] = "nobitex"
    values["usdt_rial_secondary_source"] = "wallex"
    values["usdt_rial_consecutive_failures"] = "3"

    async def fail(source: str, *, url_override=None):
        raise pricing.PricingError(source + " down")

    monkeypatch.setattr(pricing, "_fetch_provider", fail)
    with pytest.raises(pricing.PricingError):
        asyncio.run(pricing.refresh_usdt_rial_rate())

    assert values["usdt_rial_consecutive_failures"] == "4"
    assert values["usdt_rial_last_failure_at"]


def test_invoice_rate_falls_back_to_last_good_after_provider_failure(monkeypatch):
    values = _fake_settings(monkeypatch)
    values.update({
        "usdt_rial_rate_source": "nobitex",
        "usdt_rial_secondary_source": "wallex",
        "usdt_rial_last_rate": "705000",
        "usdt_rial_last_rate_at": "2026-09-02T00:00:00+00:00",
        "usdt_rial_last_rate_source": "nobitex",
    })

    async def fail_refresh():
        pricing._record_rate_failure("providers down")
        raise pricing.PricingError("providers down")

    monkeypatch.setattr(pricing, "refresh_usdt_rial_rate", fail_refresh)
    quote = asyncio.run(pricing.fetch_usdt_rial_rate())

    assert quote.rate == Decimal("705000")
    assert quote.source == "last_good:nobitex"
    assert values["usdt_rial_consecutive_failures"] == "1"
