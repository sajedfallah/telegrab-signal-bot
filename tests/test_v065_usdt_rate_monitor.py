from __future__ import annotations

import asyncio
from decimal import Decimal

from app.services import pricing_service
from app.services import usdt_rate_monitor as monitor


class FakeBot:
    def __init__(self):
        self.messages: list[tuple[int, str]] = []

    async def send_message(self, chat_id, text, **kwargs):
        self.messages.append((int(chat_id), text))
        return object()


def _fake_db(monkeypatch):
    values: dict[str, str] = {}
    monkeypatch.setattr(monitor.db, "get_setting", lambda key, default="": values.get(key, default))
    monkeypatch.setattr(monitor.db, "set_setting", lambda key, value: values.__setitem__(key, str(value)))
    return values


def test_successful_refresh_does_not_alert(monkeypatch):
    values = _fake_db(monkeypatch)
    bot = FakeBot()

    async def ok():
        return pricing_service.RateQuote(Decimal("700000"), "nobitex", "2026-09-03T00:00:00+00:00")

    monkeypatch.setattr(monitor.pricing_service, "refresh_usdt_rial_rate", ok)
    assert asyncio.run(monitor.refresh_and_maybe_alert(bot, (1, 2))) is True
    assert bot.messages == []
    assert values.get("usdt_rial_failure_alerted", "0") == "0"


def test_sustained_failure_alert_is_deduplicated(monkeypatch):
    values = _fake_db(monkeypatch)
    values["usdt_rial_failure_alerted"] = "0"
    bot = FakeBot()

    async def fail():
        raise RuntimeError("all providers down")

    monkeypatch.setattr(monitor.pricing_service, "refresh_usdt_rial_rate", fail)
    monkeypatch.setattr(
        monitor.pricing_service,
        "rate_health",
        lambda: {
            "consecutive_failures": 3,
            "primary": "nobitex",
            "primary_title": "Nobitex",
            "secondary": "wallex",
            "secondary_title": "Wallex",
            "last_rate": "700000",
            "last_rate_at": "2026-09-02T00:00:00+00:00",
        },
    )

    assert asyncio.run(monitor.refresh_and_maybe_alert(bot, (10, 20), failure_alert_threshold=3)) is False
    assert [chat_id for chat_id, _ in bot.messages] == [10, 20]
    assert values["usdt_rial_failure_alerted"] == "1"

    bot.messages.clear()
    assert asyncio.run(monitor.refresh_and_maybe_alert(bot, (10, 20), failure_alert_threshold=3)) is False
    assert bot.messages == []


def test_failure_below_threshold_does_not_alert(monkeypatch):
    values = _fake_db(monkeypatch)
    bot = FakeBot()

    async def fail():
        raise RuntimeError("temporary")

    monkeypatch.setattr(monitor.pricing_service, "refresh_usdt_rial_rate", fail)
    monkeypatch.setattr(monitor.pricing_service, "rate_health", lambda: {"consecutive_failures": 2})

    assert asyncio.run(monitor.refresh_and_maybe_alert(bot, (10,), failure_alert_threshold=3)) is False
    assert bot.messages == []
    assert values.get("usdt_rial_failure_alerted", "0") == "0"
