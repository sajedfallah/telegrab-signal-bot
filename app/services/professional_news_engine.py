from __future__ import annotations

"""Deterministic newsroom gate for NEXUS public-channel market news.

The engine intentionally does not depend on the general Agentic Content pipeline.
It scores, classifies and de-duplicates market headlines before editorial rendering.
"""

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


TIER_A = {
    "reuters", "bloomberg", "federal reserve", "fed", "bls", "bea", "sec",
    "us treasury", "u.s. treasury", "treasury", "cnbc",
}
TIER_B = {
    "fxstreet", "coindesk", "the block", "marketwatch", "investing",
    "yahoo finance", "cointelegraph", "ap", "associated press",
}

ASSET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("GOLD", re.compile(r"\b(?:gold|xau(?:usd)?|bullion)\b", re.I)),
    ("BTC", re.compile(r"\b(?:bitcoin|btc(?:usd)?|spot bitcoin etf)\b", re.I)),
    ("DOW", re.compile(r"\b(?:dow jones|dow 30|djia|dji|us30|wall street 30)\b", re.I)),
)

MACRO_RULES: tuple[tuple[re.Pattern[str], int], ...] = (
    (re.compile(r"\b(?:fomc|rate decision|interest rate decision|cpi|nonfarm|nfp)\b", re.I), 30),
    (re.compile(r"\b(?:powell|federal reserve|inflation|pce|unemployment|jobs report|treasury yields?)\b", re.I), 25),
    (re.compile(r"\b(?:gdp|retail sales|sec|bitcoin etf|etf approval|banking stress|bank failure)\b", re.I), 20),
    (re.compile(r"\b(?:war|attack|missile|sanction|tariff|geopolitic|emergency)\b", re.I), 25),
    (re.compile(r"\b(?:earnings|guidance|policy comment|regulation)\b", re.I), 15),
)

VOLATILITY_RULES: tuple[tuple[re.Pattern[str], int], ...] = (
    (re.compile(r"\b(?:breaking|urgent|emergency|rate decision|cpi|nfp|nonfarm|fomc|war|attack|halt|crash|plunge|surge)\b", re.I), 15),
    (re.compile(r"\b(?:powell|inflation|pce|treasury yield|etf|sec|jobs|unemployment|gdp)\b", re.I), 10),
)

SYSTEMIC_MACRO = re.compile(
    r"\b(?:fomc|federal reserve|powell|interest rates?|rate decision|cpi|inflation|pce|"
    r"nonfarm|nfp|unemployment|jobs report|gdp|treasury yields?|dxy|dollar index|"
    r"war|attack|sanction|tariff|banking stress)\b",
    re.I,
)
BREAKING_CONFIRM_RE = re.compile(
    r"\b(?:breaking|urgent|emergency|rate decision|fomc|cpi|nfp|war|attack|halt|default|bank failure)\b",
    re.I,
)


@dataclass(frozen=True)
class NewsDecision:
    story_id: str
    score: int
    category: str
    publish: bool
    reason: str
    assets: tuple[str, ...]
    source_tier: str
    macro_score: int
    relevance_score: int
    source_score: int
    volatility_score: int
    freshness_score: int
    novelty_score: int
    impact_level: str

    @property
    def is_breaking(self) -> bool:
        return self.category == "breaking_news"

    @property
    def is_important(self) -> bool:
        return self.category in {"important_news", "breaking_news"}


def _env_int(name: str, default: int, minimum: int = 0, maximum: int = 100000) -> int:
    try:
        value = int(str(os.getenv(name, str(default))).strip())
    except Exception:
        value = default
    return max(minimum, min(maximum, value))


def _env_bool(name: str, default: bool) -> bool:
    raw = str(os.getenv(name, "true" if default else "false")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def enabled() -> bool:
    return _env_bool("NEXUS_NEWS_ENGINE_ENABLED", True)


def thresholds() -> tuple[int, int, int]:
    minimum = _env_int("NEWS_MIN_PUBLISH_SCORE", 65, 1, 100)
    important = _env_int("NEWS_IMPORTANT_SCORE", 80, minimum, 100)
    breaking = _env_int("NEWS_BREAKING_SCORE", 90, important, 100)
    return minimum, important, breaking


def _clean_source(source: str) -> str:
    return re.sub(r"\s+", " ", str(source or "")).strip().lower()


def source_tier(source: str) -> tuple[str, int]:
    cleaned = _clean_source(source)
    if any(name in cleaned for name in TIER_A):
        return "A", 15
    if any(name in cleaned for name in TIER_B):
        return "B", 10
    return "C", 4


def detect_assets(title: str) -> tuple[str, ...]:
    text = str(title or "")
    assets = [asset for asset, pattern in ASSET_PATTERNS if pattern.search(text)]
    if SYSTEMIC_MACRO.search(text):
        for asset in ("GOLD", "BTC", "DOW"):
            if asset not in assets:
                assets.append(asset)
    return tuple(assets)


def story_fingerprint(title: str) -> str:
    text = str(title or "").lower()
    text = re.sub(r"\b(?:breaking|urgent|update|exclusive|live)\b", " ", text)
    text = re.sub(r"[^a-z0-9%$]+", " ", text)
    stop = {"the", "a", "an", "to", "of", "in", "on", "for", "and", "as", "says", "said", "with", "after", "amid"}
    tokens = [token for token in text.split() if token not in stop]
    normalized = " ".join(sorted(dict.fromkeys(tokens))[:18])
    return hashlib.sha256(normalized.encode("utf-8", "ignore")).hexdigest()[:20]


def _macro_score(title: str) -> int:
    best = 5
    for pattern, value in MACRO_RULES:
        if pattern.search(title or ""):
            best = max(best, value)
    return min(30, best)


def _relevance_score(title: str, assets: tuple[str, ...]) -> int:
    if not assets:
        return 0
    if SYSTEMIC_MACRO.search(title or ""):
        return 25
    direct = sum(1 for _, pattern in ASSET_PATTERNS if pattern.search(title or ""))
    if direct >= 2:
        return 25
    if direct == 1:
        return 22
    return 15


def _volatility_score(title: str) -> int:
    best = 5
    for pattern, value in VOLATILITY_RULES:
        if pattern.search(title or ""):
            best = max(best, value)
    return min(15, best)


def _freshness_score(published_at: datetime | None, now_utc: datetime) -> int:
    if not isinstance(published_at, datetime):
        return 4
    published = published_at
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    age_minutes = max(0, int((now_utc - published.astimezone(timezone.utc)).total_seconds() // 60))
    if age_minutes < 5:
        return 10
    if age_minutes < 15:
        return 8
    if age_minutes < 30:
        return 6
    if age_minutes < 60:
        return 4
    if age_minutes < 180:
        return 2
    return 0


def _story_key() -> str:
    return "professional_news_story_ids"


def _load_seen(main: Any) -> list[str]:
    if main is None:
        return []
    try:
        raw = main.db.get_setting(_story_key(), "[]")
        value = json.loads(raw)
        return [str(x) for x in value][-500:] if isinstance(value, list) else []
    except Exception:
        return []


def story_seen(main: Any, story_id: str) -> bool:
    return story_id in set(_load_seen(main))


def mark_story_seen(main: Any, story_id: str) -> None:
    if main is None or not story_id:
        return
    values = _load_seen(main)
    if story_id not in values:
        values.append(story_id)
    main.db.set_setting(_story_key(), json.dumps(values[-500:]))


def evaluate(item: Any, *, main: Any = None, now_utc: datetime | None = None) -> NewsDecision:
    now = now_utc or datetime.now(timezone.utc)
    title = str(getattr(item, "title", "") or "")
    assets = detect_assets(title)
    story_id = story_fingerprint(title)
    tier, source_score = source_tier(str(getattr(item, "source", "") or ""))
    duplicate = story_seen(main, story_id)

    macro = _macro_score(title)
    relevance = _relevance_score(title, assets)
    volatility = _volatility_score(title)
    freshness = _freshness_score(getattr(item, "published_at", None), now)
    novelty = 0 if duplicate else 5
    total = min(100, macro + relevance + source_score + volatility + freshness + novelty)

    minimum, important, breaking = thresholds()
    category = "market_update"
    publish = total >= minimum and bool(assets) and not duplicate
    reason = "eligible"

    if duplicate:
        publish = False
        reason = "duplicate_story"
    elif not assets:
        publish = False
        reason = "outside_focus"
    elif tier == "C" and _env_bool("NEWS_REQUIRE_TIER_C_CONFIRMATION", True):
        publish = False
        reason = "tier_c_requires_confirmation"
    elif total < minimum:
        publish = False
        reason = "below_publish_threshold"

    if total >= breaking:
        # A high score alone must not create a BREAKING label.
        if tier == "A" and BREAKING_CONFIRM_RE.search(title):
            category = "breaking_news"
        else:
            category = "important_news"
    elif total >= important:
        category = "important_news"

    impact_level = "HIGH" if total >= important else "MEDIUM"
    return NewsDecision(
        story_id=story_id,
        score=total,
        category=category,
        publish=publish,
        reason=reason,
        assets=assets,
        source_tier=tier,
        macro_score=macro,
        relevance_score=relevance,
        source_score=source_score,
        volatility_score=volatility,
        freshness_score=freshness,
        novelty_score=novelty,
        impact_level=impact_level,
    )


def image_score(item: Any, image_url: str, decision: NewsDecision) -> int:
    if not image_url:
        return 0
    score = 55  # exact article OpenGraph/Twitter image is the preferred candidate
    if decision.assets:
        score += 10
    if decision.source_tier == "A":
        score += 10
    elif decision.source_tier == "B":
        score += 5
    url_text = image_url.lower()
    title = str(getattr(item, "title", "") or "").lower()
    if any(token in url_text for token in ("bitcoin", "btc", "gold", "xau", "powell", "fed", "dow", "wall-street")):
        if any(token in title for token in ("bitcoin", "btc", "gold", "xau", "powell", "fed", "dow", "wall street")):
            score += 10
    if any(token in url_text for token in ("logo", "avatar", "icon", "placeholder")):
        score -= 35
    return max(0, min(100, score))


def image_allowed(item: Any, image_url: str, decision: NewsDecision) -> bool:
    minimum = _env_int("NEWS_IMAGE_MIN_SCORE", 75, 1, 100)
    return _env_bool("NEWS_IMAGES_ENABLED", True) and image_score(item, image_url, decision) >= minimum
