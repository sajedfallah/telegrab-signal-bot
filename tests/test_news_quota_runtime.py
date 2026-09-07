from datetime import datetime, timezone
from types import SimpleNamespace

from app.services import news_quota_runtime as quota
from app.services.professional_news_engine import NewsDecision


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
        self.settings = SimpleNamespace(timezone="Asia/Tehran")


def _decision(score=95, category="important_news", tier="A", publish=True):
    return NewsDecision(
        story_id="abc",
        score=score,
        category=category,
        publish=publish,
        reason="eligible",
        assets=("GOLD",),
        source_tier=tier,
        macro_score=30,
        relevance_score=25,
        source_score=15,
        volatility_score=15,
        freshness_score=10,
        novelty_score=5,
        impact_level="HIGH",
    )


def test_parse_slots_caps_to_five(monkeypatch):
    monkeypatch.setenv("NEWS_DAILY_SLOTS", "08:00,10:00,12:00,14:00,16:00,18:00")
    assert quota._parse_slots() == ((8, 0), (10, 0), (12, 0), (14, 0), (16, 0))


def test_only_very_important_ab_tier_is_eligible(monkeypatch):
    monkeypatch.setenv("NEWS_SLOT_MIN_SCORE", "90")
    monkeypatch.setenv("NEWS_SLOT_ALLOWED_SOURCE_TIERS", "A,B")
    assert quota._eligible(_decision(score=95, tier="A")) is True
    assert quota._eligible(_decision(score=89, tier="A")) is False
    assert quota._eligible(_decision(score=95, tier="C")) is False
    assert quota._eligible(_decision(score=95, category="market_update", tier="A")) is False


def test_daily_counter_and_slot_are_durable(monkeypatch):
    monkeypatch.setenv("NEWS_DAILY_SLOTS", "12:15")
    monkeypatch.setenv("NEWS_SLOT_WINDOW_MINUTES", "75")
    main = _Main()
    now = datetime(2026, 9, 7, 9, 0, tzinfo=timezone.utc)  # 12:30 Tehran
    local = quota._local_now(main, now)
    slot = quota._due_slot(main, now)
    assert slot == (12, 15)
    quota._mark_sent(main, local, slot)
    assert quota._daily_count(main, local) == 1
    assert quota._due_slot(main, now) is None
