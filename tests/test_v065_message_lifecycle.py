from __future__ import annotations

import asyncio

from app.services import message_lifecycle as lifecycle


class FakeBot:
    def __init__(self, *, fail_delete: bool = False):
        self.fail_delete = fail_delete
        self.deleted: list[tuple[int, int]] = []

    async def delete_message(self, chat_id, message_id):
        if self.fail_delete:
            raise RuntimeError("delete failed")
        self.deleted.append((int(chat_id), int(message_id)))


def test_default_information_ttl_is_30_seconds():
    assert lifecycle.DEFAULT_INFO_TTL_SECONDS == 30


def test_logged_delete_returns_true_on_success():
    bot = FakeBot()
    result = asyncio.run(lifecycle.delete_message_logged(bot, 10, 20, reason="test"))
    assert result is True
    assert bot.deleted == [(10, 20)]


def test_logged_delete_is_best_effort_on_telegram_failure():
    bot = FakeBot(fail_delete=True)
    result = asyncio.run(lifecycle.delete_message_logged(bot, 10, 20, reason="test"))
    assert result is False
    assert bot.deleted == []


def test_delete_after_uses_minimum_observation_delay(monkeypatch):
    waits: list[int] = []
    bot = FakeBot()

    async def fake_sleep(seconds):
        waits.append(int(seconds))

    monkeypatch.setattr(lifecycle.asyncio, "sleep", fake_sleep)
    result = asyncio.run(lifecycle.delete_after(bot, 10, 20, delay_seconds=1, reason="test"))

    assert result is True
    assert waits == [lifecycle.MIN_DELETE_DELAY_SECONDS]
    assert bot.deleted == [(10, 20)]
