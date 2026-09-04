from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from app.services import market_brief_service as market
from app.services import market_editorial_service as editorial
from app.services import market_ict_service as ict
from app.services import market_public_channel_runtime as runtime


class FakeDB:
    def __init__(self, values=None):
        self.values = dict(values or {})

    def get_setting(self, key, default=""):
        return self.values.get(key, default)

    def set_setting(self, key, value):
        self.values[key] = str(value)


class FakeBot:
    def __init__(self, *, fail_photo: bool = False, fail_message_on: int | None = None):
        self.calls = []
        self.fail_photo = fail_photo
        self.fail_message_on = fail_message_on
        self.message_attempts = 0

    async def send_message(self, target, text, **kwargs):
        self.message_attempts += 1
        if self.fail_message_on == self.message_attempts:
            raise RuntimeError("message send failed")
        self.calls.append(("message", target, text, kwargs))
        return SimpleNamespace(message_id=len(self.calls))

    async def send_photo(self, target, photo, caption, **kwargs):
        if self.fail_photo:
            raise RuntimeError("photo fetch failed")
        self.calls.append(("photo", target, caption, {"photo": photo, **kwargs}))
        return SimpleNamespace(message_id=len(self.calls))


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


def _dow_news():
    return market.NewsItem(
        title="Dow Jones rises as Wall Street awaits US jobs data",
        link="https://example.com/dow",
        source="Reuters",
        published_at=datetime(2026, 9, 4, 1, 10, tzinfo=timezone.utc),
        score=0,
    )


def _btc_news():
    return market.NewsItem(
        title="Bitcoin breaks above a major resistance level",
        link="https://example.com/btc",
        source="CoinDesk",
        published_at=datetime(2026, 9, 4, 1, 20, tzinfo=timezone.utc),
        score=5,
    )


def _nonfocus_news():
    return market.NewsItem(
        title="EUR/USD steadies after ECB official comments",
        link="https://example.com/eurusd",
        source="FXStreet",
        published_at=datetime(2026, 9, 4, 1, 5, tzinfo=timezone.utc),
        score=8,
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
    if "Dow" in title:
        return "شاخص داوجونز پیش از داده‌های اشتغال آمریکا رشد کرد"
    if "Bitcoin" in title:
        return "بیت‌کوین از مقاومت مهم عبور کرد"
    return "تورم آمریکا بازار را غافلگیر کرد و طلا جهش کرد"


async def _fake_ict(*, symbol, asset_fa, now_utc, local_timezone):
    return f"<b>تحلیل ICT {asset_fa}</b>\n{symbol}\n1H / 15M / 5M"


def test_market_public_channel_install_replaces_broadcasts_and_focus_filter():
    original = (
        market.important_recent_news,
        market._broadcast_brief,
        market._broadcast_news_item,
        market._broadcast_event_alert,
    )
    try:
        runtime.install(_main())
        assert market.important_recent_news is runtime._focused_important_recent_news
        assert market._broadcast_brief is runtime._broadcast_brief
        assert market._broadcast_news_item is runtime._broadcast_news_item
        assert market._broadcast_event_alert is runtime._broadcast_event_alert
    finally:
        (
            market.important_recent_news,
            market._broadcast_brief,
            market._broadcast_news_item,
            market._broadcast_event_alert,
        ) = original


def test_focus_filter_allows_gold_bitcoin_and_dow_only():
    now = datetime(2026, 9, 4, 2, 0, tzinfo=timezone.utc)
    selected = runtime._focused_important_recent_news(
        [_news(), _dow_news(), _btc_news(), _nonfocus_news()],
        now_utc=now,
        minimum_score=5,
        max_age_minutes=180,
    )
    titles = [x.title for x in selected]
    assert _news().title in titles
    assert _dow_news().title in titles
    assert _btc_news().title in titles
    assert _nonfocus_news().title not in titles


def test_focus_filter_recognizes_xau_btc_dji_and_us30_aliases():
    for title in (
        "XAU/USD extends gains after US data",
        "BTC/USD slips below support",
        "DJI futures rise before the open",
        "US30 volatility jumps after CPI",
    ):
        item = market.NewsItem(title=title, link="", source="Any", published_at=None, score=0)
        assert runtime._is_focus_news(item)


def test_morning_suite_is_exactly_three_ordered_messages_without_sources(monkeypatch):
    monkeypatch.setattr(editorial, "translate_event_title", _fa_event)
    monkeypatch.setattr(editorial, "translate_to_persian", _fa_headline)
    monkeypatch.setattr(ict, "build_daily_ict_message", _fake_ict)
    main = _main()
    bot = FakeBot()
    result = asyncio.run(
        runtime._broadcast_brief(
            main,
            bot,
            [_event()],
            [_news(), _dow_news(), _btc_news(), _nonfocus_news()],
            datetime(2026, 9, 4, 8, 0, tzinfo=timezone.utc),
        )
    )
    assert result == (3, 0)
    assert len(bot.calls) == 3
    assert "گزارش صبحگاهی NEXUS" in bot.calls[0][2]
    assert "تحلیل ICT طلای جهانی" in bot.calls[1][2]
    assert "XAUUSD" in bot.calls[1][2]
    assert "تحلیل ICT بیت‌کوین" in bot.calls[2][2]
    assert "BTCUSD" in bot.calls[2][2]
    assert "تورم آمریکا" in bot.calls[0][2]
    assert "داوجونز" in bot.calls[0][2]
    assert "بیت‌کوین" in bot.calls[0][2]
    assert "EUR/USD" not in bot.calls[0][2]
    assert "FXStreet" not in bot.calls[0][2]
    assert "Reuters" not in bot.calls[0][2]
    assert "CoinDesk" not in bot.calls[0][2]
    assert "https://" not in bot.calls[0][2]

    again = asyncio.run(
        runtime._broadcast_brief(
            main,
            bot,
            [_event()],
            [_news()],
            datetime(2026, 9, 4, 8, 5, tzinfo=timezone.utc),
        )
    )
    assert again == (3, 0)
    assert len(bot.calls) == 3


def test_morning_suite_retry_does_not_duplicate_completed_component(monkeypatch):
    monkeypatch.setattr(editorial, "translate_event_title", _fa_event)
    monkeypatch.setattr(editorial, "translate_to_persian", _fa_headline)
    monkeypatch.setattr(ict, "build_daily_ict_message", _fake_ict)
    main = _main()
    now = datetime(2026, 9, 4, 8, 0, tzinfo=timezone.utc)

    first_bot = FakeBot(fail_message_on=2)
    first = asyncio.run(runtime._broadcast_brief(main, first_bot, [_event()], [_news()], now))
    assert first == (0, 1)
    assert len(first_bot.calls) == 1
    assert "گزارش صبحگاهی NEXUS" in first_bot.calls[0][2]

    retry_bot = FakeBot()
    retry = asyncio.run(runtime._broadcast_brief(main, retry_bot, [_event()], [_news()], now))
    assert retry == (3, 0)
    assert len(retry_bot.calls) == 2
    assert "تحلیل ICT طلای جهانی" in retry_bot.calls[0][2]
    assert "تحلیل ICT بیت‌کوین" in retry_bot.calls[1][2]


def test_important_news_publishes_persian_text_with_image_and_hides_all_source_mentions(monkeypatch):
    async def fake_prepare(item, *, local_timezone):
        return editorial.PersianNewsPayload(
            text=(
                "<b>🚨 خبر مهم بازار | NEXUS</b>\n\n"
                "<b>طلا با کاهش انتظارات افزایش نرخ بهره رشد کرد</b>\n\n"
                "📝 FXStreet می‌گوید بازار طلا پیش از داده‌های اشتغال آمریکا تقویت شد.\n\n"
                "📰 منبع: <b>FXStreet</b>\n"
                "🕒 زمان: <b>14:30</b>"
            ),
            image_url="https://cdn.example.com/gold.jpg",
        )

    monkeypatch.setattr(editorial, "prepare_persian_news_payload", fake_prepare)
    monkeypatch.setattr(runtime, "_morning_quiet", lambda *args, **kwargs: False)
    main = _main()
    bot = FakeBot()
    result = asyncio.run(runtime._broadcast_news_item(main, bot, _news()))
    assert result == (1, 0)
    assert len(bot.calls) == 1
    kind, target, text, kwargs = bot.calls[0]
    assert kind == "photo"
    assert target == main.settings.public_channel_id
    assert "طلا" in text
    assert "FXStreet" not in text
    assert "منبع" not in text
    assert "https://example.com/cpi" not in text
    assert kwargs["photo"] == "https://cdn.example.com/gold.jpg"


def test_non_focus_news_is_suppressed_before_translation(monkeypatch):
    async def should_not_prepare(*args, **kwargs):
        raise AssertionError("non-focus headline must never reach translation")

    monkeypatch.setattr(editorial, "prepare_persian_news_payload", should_not_prepare)
    bot = FakeBot()
    result = asyncio.run(runtime._broadcast_news_item(_main(), bot, _nonfocus_news()))
    assert result == (0, 0)
    assert bot.calls == []


def test_routine_focus_news_is_suppressed_during_morning_quiet(monkeypatch):
    async def should_not_prepare(*args, **kwargs):
        raise AssertionError("routine morning headline must not be published")

    monkeypatch.setattr(editorial, "prepare_persian_news_payload", should_not_prepare)
    monkeypatch.setattr(runtime, "_morning_quiet", lambda *args, **kwargs: True)
    bot = FakeBot()
    result = asyncio.run(runtime._broadcast_news_item(_main(), bot, _btc_news()))
    assert result == (0, 0)
    assert bot.calls == []


def test_extraordinary_breaking_focus_news_can_bypass_morning_quiet(monkeypatch):
    async def fake_prepare(item, *, local_timezone):
        return editorial.PersianNewsPayload(text="<b>خبر فوری مهم طلا</b>")

    monkeypatch.setattr(editorial, "prepare_persian_news_payload", fake_prepare)
    monkeypatch.setattr(runtime, "_morning_quiet", lambda *args, **kwargs: True)
    bot = FakeBot()
    result = asyncio.run(runtime._broadcast_news_item(_main(), bot, _news()))
    assert result == (1, 0)
    assert len(bot.calls) == 1


def test_news_image_failure_falls_back_to_same_persian_text(monkeypatch):
    async def fake_prepare(item, *, local_timezone):
        return editorial.PersianNewsPayload(text="<b>خبر مهم طلا</b>", image_url="https://cdn.example.com/a.jpg")

    monkeypatch.setattr(editorial, "prepare_persian_news_payload", fake_prepare)
    monkeypatch.setattr(runtime, "_morning_quiet", lambda *args, **kwargs: False)
    main = _main()
    bot = FakeBot(fail_photo=True)
    result = asyncio.run(runtime._broadcast_news_item(main, bot, _news()))
    assert result == (1, 0)
    assert len(bot.calls) == 1
    assert bot.calls[0][0] == "message"


def test_untranslated_focus_news_is_suppressed(monkeypatch):
    async def no_translation(item, *, local_timezone):
        return None

    monkeypatch.setattr(editorial, "prepare_persian_news_payload", no_translation)
    monkeypatch.setattr(runtime, "_morning_quiet", lambda *args, **kwargs: False)
    bot = FakeBot()
    result = asyncio.run(runtime._broadcast_news_item(_main(), bot, _news()))
    assert result == (0, 1)
    assert bot.calls == []


def test_economic_alert_is_persian_outside_morning(monkeypatch):
    monkeypatch.setattr(editorial, "translate_event_title", _fa_event)
    monkeypatch.setattr(runtime, "_morning_quiet", lambda *args, **kwargs: False)
    main = _main()
    bot = FakeBot()
    result = asyncio.run(runtime._broadcast_event_alert(main, bot, _event(), 30))
    assert result == (1, 0)
    assert len(bot.calls) == 1
    _, target, text, _ = bot.calls[0]
    assert target == main.settings.public_channel_id
    assert "هشدار خبر اقتصادی NEXUS" in text
    assert "30 دقیقه" in text


def test_economic_alert_is_suppressed_during_morning(monkeypatch):
    monkeypatch.setattr(runtime, "_morning_quiet", lambda *args, **kwargs: True)
    bot = FakeBot()
    result = asyncio.run(runtime._broadcast_event_alert(_main(), bot, _event(), 30))
    assert result == (0, 0)
    assert bot.calls == []


def test_public_market_language_is_forced_to_persian():
    assert runtime._channel_lang(_main(lang="en")) == "fa"
    assert runtime._channel_lang(_main(lang="de")) == "fa"


def test_missing_public_channel_fails_closed(monkeypatch):
    async def fake_prepare(item, *, local_timezone):
        return editorial.PersianNewsPayload(text="خبر فوری مهم طلا")

    monkeypatch.setattr(editorial, "prepare_persian_news_payload", fake_prepare)
    monkeypatch.setattr(runtime, "_morning_quiet", lambda *args, **kwargs: False)
    main = SimpleNamespace(settings=SimpleNamespace(public_channel_id="", timezone="UTC"), db=FakeDB())
    bot = FakeBot()
    try:
        asyncio.run(runtime._broadcast_news_item(main, bot, _news()))
    except RuntimeError as exc:
        assert "public channel" in str(exc).lower()
    else:
        raise AssertionError("missing public channel must fail closed")
    assert bot.calls == []
