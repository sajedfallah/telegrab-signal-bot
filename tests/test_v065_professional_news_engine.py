from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.market_brief_service import NewsItem
from app.services import professional_news_engine as engine


class _DB:
    def __init__(self):
        self.values = {}

    def get_setting(self, key, default=""):
        return self.values.get(key, default)

    def set_setting(self, key, value):
        self.values[key] = value


class _Main:
    def __init__(self):
        self.db = _DB()


def _item(title: str, source: str = "Reuters", minutes_old: int = 1) -> NewsItem:
    return NewsItem(
        title=title,
        link="https://example.com/story",
        source=source,
        published_at=datetime.now(timezone.utc) - timedelta(minutes=minutes_old),
        score=7,
    )


def test_systemic_cpi_reaches_all_focus_assets():
    decision = engine.evaluate(_item("US CPI inflation rises above expectations"))
    assert decision.publish is True
    assert set(decision.assets) == {"GOLD", "BTC", "DOW"}
    assert decision.score >= 80


def test_routine_asset_headline_is_not_public_noise():
    decision = engine.evaluate(_item("Gold trades slightly higher in early session", source="FXStreet"))
    assert decision.publish is False
    assert decision.reason == "below_publish_threshold"


def test_tier_c_requires_confirmation():
    decision = engine.evaluate(_item("Bitcoin ETF approval triggers major market move", source="Unknown Blog"))
    assert decision.publish is False
    assert decision.reason == "tier_c_requires_confirmation"


def test_persistent_story_guard_blocks_republication():
    main = _Main()
    item = _item("Federal Reserve rate decision sends markets sharply lower")
    first = engine.evaluate(item, main=main)
    assert first.publish is True
    engine.mark_story_seen(main, first.story_id)
    second = engine.evaluate(item, main=main)
    assert second.publish is False
    assert second.reason == "duplicate_story"


def test_breaking_requires_tier_a_and_breaking_context():
    strong = engine.evaluate(_item("BREAKING: Federal Reserve announces emergency rate decision", source="Reuters"))
    assert strong.category == "breaking_news"
    weaker_source = engine.evaluate(_item("BREAKING: Federal Reserve announces emergency rate decision", source="CoinDesk"))
    assert weaker_source.category == "important_news"


def test_related_article_image_is_allowed_for_important_tier_b_story(monkeypatch):
    monkeypatch.setenv("NEWS_IMAGE_MIN_SCORE", "75")
    item = _item("Bitcoin ETF approval expected after SEC decision", source="CoinDesk")
    decision = engine.evaluate(item)
    assert decision.publish is True
    assert engine.image_allowed(item, "https://cdn.example.com/news/bitcoin-etf.jpg", decision) is True


def test_placeholder_image_is_rejected(monkeypatch):
    monkeypatch.setenv("NEWS_IMAGE_MIN_SCORE", "75")
    item = _item("US CPI inflation rises above expectations", source="Reuters")
    decision = engine.evaluate(item)
    assert engine.image_allowed(item, "https://cdn.example.com/placeholder-logo.png", decision) is False
