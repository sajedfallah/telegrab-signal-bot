from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from app.services import market_brief_service as market
from app.services import market_editorial_service as editorial
from app.services import market_public_channel_runtime as runtime


class FakeDB:
    def __init__(self, values=None):
        self.values = dict(values or {})

    def get_setting(self, key, default=""):
        return self.values.get(key, default)


class FakeBot:
    def __init__(self, *, fail_photo: bool = False):
        self.calls = []
        self.fail_photo = fail_photo

    async def send_message(self, target, text, **kwargs):
        self.calls.append(("message", target, text, kwargs))
        return SimpleNamespace(message_id=1)

    async def send_photo(self, target, photo, caption, **kwargs):
        if self.fail_photo:
            raise RuntimeError("photo fetch failed")
        self.calls.append(("photo", target, caption, {"photo": photo, **kwargs}))
        return SimpleNamespace(message_id=2)


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


async def _fa_event(title, *, country=""):
    return "تغییر اشتغال بخش غیرکشاورزی"


async def _fa_headline(title, *, attempts=3):
    return "تورم آمریکا بازار را غافلگیر کرد و طلا جهش کرد"


def test_market_public_channel_install_replaces_all_three_broadcasts():
    original = (market._broadcast_brief, market._broadcast_news_item, market._broadcast_event_alert)
    try:
        runtime.install(_main())
        assert market._broadcast_brief is runtime._broadcast_brief
        assert market._broadcast_news_item is runtime._broadcast_news_item
        assert market._broadcast_event_alert is runtime._broadcast_event_alert
    finally:
        market._broadcast_brief, market._broadcast_news_item, market._broadcast_event_alert = original


def test_morning_brief_is_persian_native_text_without_article_links(monkeypatch):
    monkeypatch.setattr(editorial, "translate_event_title", _fa_event)
    monkeypatch.setattr(editorial, "translate_to_persian", _fa_headline)
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
    kind, target, text, kwargs = bot.calls[0]
    assert kind == "message"
    assert target == main.settings.public_channel_id
    assert "گزارش صبحگاهی NEXUS" in text
    assert "تغییر اشتغال بخش غیرکشاورزی" in text
    assert "تورم آمریکا" in text
    assert "https://" not in text
    assert kwargs["parse_mode"] == "HTML"


def test_important_news_publishes_persian_text_with_related_image(monkeypatch):
    async def fake_prepare(item, *, local_timezone):
        return editorial.PersianNewsPayload(
            text=(
                "<b>🚨 خبر مهم بازار | NEXUS</b>\n\n"
                "<b>طلا با کاهش انتظارات افزایش نرخ بهره فدرال رزرو رشد کرد</b>\n\n"
                "📝 بازار طلا پیش از داده‌های اشتغال آمریکا تقویت شد.\n\n"
                "📰 منبع: <b>FXStreet</b>"
            ),
            image_url="https://cdn.example.com/gold.jpg",
        )

    monkeypatch.setattr(editorial, "prepare_persian_news_payload", fake_prepare)
    main = _main()
    bot = FakeBot()
    result = asyncio.run(runtime._broadcast_news_item(main, bot, _news()))
    assert result == (1, 0)
    assert len(bot.calls) == 1
    kind, target, text, kwargs = bot.calls[0]
    assert kind == "photo"
    assert target == main.settings.public_channel_id
    assert "طلا" in text
    assert "https://example.com/cpi" not in text
    assert kwargs["photo"] == "https://cdn.example.com/gold.jpg"


def test_news_image_failure_falls_back_to_same_persian_text(monkeypatch):
    async def fake_prepare(item, *, local_timezone):
        return editorial.PersianNewsPayload(text="<b>خبر مهم فارسی</b>", image_url="https://cdn.example.com/a.jpg")

    monkeypatch.setattr(editorial, "prepare_persian_news_payload", fake_prepare)
    main = _main()
    bot = FakeBot(fail_photo=True)
    result = asyncio.run(runtime._broadcast_news_item(main, bot, _news()))
    assert result == (1, 0)
    assert len(bot.calls) == 1
    assert bot.calls[0][0] == "message"
    assert "خبر مهم فارسی" in bot.calls[0][2]


def test_untranslated_english_news_is_suppressed(monkeypatch):
    async def no_translation(item, *, local_timezone):
        return None

    monkeypatch.setattr(editorial, "prepare_persian_news_payload", no_translation)
    bot = FakeBot()
    result = asyncio.run(runtime._broadcast_news_item(_main(), bot, _news()))
    assert result == (0, 1)
    assert bot.calls == []


def test_economic_alert_is_persian(monkeypatch):
    monkeypatch.setattr(editorial, "translate_event_title", _fa_event)
    main = _main()
    bot = FakeBot()
    result = asyncio.run(runtime._broadcast_event_alert(main, bot, _event(), 30))
    assert result == (1, 0)
    assert len(bot.calls) == 1
    _, target, text, _ = bot.calls[0]
    assert target == main.settings.public_channel_id
    assert "هشدار خبر اقتصادی NEXUS" in text
    assert "تغییر اشتغال بخش غیرکشاورزی" in text
    assert "30 دقیقه" in text
    assert "پیش‌بینی" in text


def test_public_market_language_is_forced_to_persian():
    assert runtime._channel_lang(_main(lang="en")) == "fa"
    assert runtime._channel_lang(_main(lang="de")) == "fa"


def test_missing_public_channel_fails_closed(monkeypatch):
    async def fake_prepare(item, *, local_timezone):
        return editorial.PersianNewsPayload(text="خبر فارسی")

    monkeypatch.setattr(editorial, "prepare_persian_news_payload", fake_prepare)
    main = SimpleNamespace(settings=SimpleNamespace(public_channel_id="", timezone="UTC"), db=FakeDB())
    bot = FakeBot()
    try:
        asyncio.run(runtime._broadcast_news_item(main, bot, _news()))
    except RuntimeError as exc:
        assert "public channel" in str(exc).lower()
    else:
        raise AssertionError("missing public channel must fail closed")
    assert bot.calls == []
