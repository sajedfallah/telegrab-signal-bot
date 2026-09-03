from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from app.services import market_brief_service as market
from app.services import market_public_channel_runtime as runtime


class FakeDB:
    def __init__(self, values=None):
        self.values = dict(values or {})

    def get_setting(self, key, default=""):
        return self.values.get(key, default)


class FakeBot:
    def __init__(self):
        self.calls = []

    async def send_message(self, target, text, **kwargs):
        self.calls.append((target, text, kwargs))
        return SimpleNamespace(message_id=1)


def _main(lang="fa"):
    return SimpleNamespace(
        settings=SimpleNamespace(public_channel_id=-1001234567890, timezone="UTC"),
        db=FakeDB({"market_public_channel_language": lang}),
    )


def _news():
    return market.NewsItem(
        title="Breaking: US CPI inflation surprises markets as Gold jumps",
        link="https://example.com/cpi",
        source="FXStreet",
        published_at=datetime(2026, 9, 4, 1, 0, tzinfo=timezone.utc),
        score=19,
    )


def _event():
    return market.CalendarEvent(
        title="Non-Farm Employment Change",
        country="USD",
        impact="High",
        when_utc=datetime(2026, 9, 4, 16, 0, tzinfo=timezone.utc),
        time_label="4:00pm",
        forecast="80K",
        previous="75K",
    )


def test_market_public_channel_install_replaces_all_three_broadcasts():
    original = (market._broadcast_brief, market._broadcast_news_item, market._broadcast_event_alert)
    try:
        runtime.install(_main())
        assert market._broadcast_brief is runtime._broadcast_brief
        assert market._broadcast_news_item is runtime._broadcast_news_item
        assert market._broadcast_event_alert is runtime._broadcast_event_alert
    finally:
        market._broadcast_brief, market._broadcast_news_item, market._broadcast_event_alert = original


def test_morning_brief_publishes_once_to_public_channel_only():
    main = _main()
    bot = FakeBot()
    result = asyncio.run(
        runtime._broadcast_brief(
            main,
            bot,
            [_event()],
            [_news()],
            datetime(2026, 9, 4, 8, 0, tzinfo=timezone.utc),
        )
    )
    assert result == (1, 0)
    assert len(bot.calls) == 1
    target, text, kwargs = bot.calls[0]
    assert target == main.settings.public_channel_id
    assert "NEXUS Morning Brief" in text
    assert "Non-Farm Employment Change" in text
    assert kwargs["parse_mode"] == "HTML"


def test_important_news_publishes_once_to_public_channel_only():
    main = _main()
    bot = FakeBot()
    result = asyncio.run(runtime._broadcast_news_item(main, bot, _news()))
    assert result == (1, 0)
    assert len(bot.calls) == 1
    target, text, _ = bot.calls[0]
    assert target == main.settings.public_channel_id
    assert "NEXUS Market News" in text
    assert "US CPI inflation surprises markets" in text


def test_economic_alert_publishes_once_to_public_channel_only():
    main = _main()
    bot = FakeBot()
    result = asyncio.run(runtime._broadcast_event_alert(main, bot, _event(), 30))
    assert result == (1, 0)
    assert len(bot.calls) == 1
    target, text, _ = bot.calls[0]
    assert target == main.settings.public_channel_id
    assert "هشدار خبر اقتصادی NEXUS" in text
    assert "30 دقیقه" in text


def test_invalid_channel_language_falls_back_to_persian():
    main = _main(lang="de")
    assert runtime._channel_lang(main) == "fa"


def test_missing_public_channel_fails_closed():
    main = SimpleNamespace(settings=SimpleNamespace(public_channel_id="", timezone="UTC"), db=FakeDB())
    bot = FakeBot()
    try:
        asyncio.run(runtime._broadcast_news_item(main, bot, _news()))
    except RuntimeError as exc:
        assert "public channel" in str(exc).lower()
    else:
        raise AssertionError("missing public channel must fail closed")
    assert bot.calls == []
