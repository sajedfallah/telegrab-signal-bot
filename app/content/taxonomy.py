from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class ContentCategory:
    key: str
    code: str
    label_fa: str
    emoji: str
    hashtags: tuple[str, ...]
    max_per_day: int
    min_priority: int = 0
    requires_source: bool = False
    urgent: bool = False


CATEGORIES: dict[str, ContentCategory] = {
    "ict_education": ContentCategory(
        "ict_education", "EDU", "آموزش ICT", "📘",
        ("#آموزش", "#آموزش_ICT", "#ICT"), 1,
    ),
    "daily_analysis": ContentCategory(
        "daily_analysis", "ANL", "تحلیل روزانه", "📊",
        ("#تحلیل", "#تحلیل_روزانه", "#Market_Analysis"), 1, 45,
    ),
    "quick_tip": ContentCategory(
        "quick_tip", "TIP", "نکته معاملاتی", "⚡",
        ("#نکته_معاملاتی", "#Quick_Tip"), 1,
    ),
    "market_news": ContentCategory(
        "market_news", "NWS", "خبر بازار", "📰",
        ("#خبر", "#اخبار_بازار"), 1, 70, True,
    ),
    "important_news": ContentCategory(
        "important_news", "IMP", "اخبار مهم", "🚨",
        ("#اخبار_مهم", "#High_Impact"), 3, 80, True, True,
    ),
    "news_alert": ContentCategory(
        "news_alert", "ALT", "هشدار خبر", "⏰",
        ("#هشدار_خبر", "#Economic_Calendar"), 3, 80, True, True,
    ),
    "tools": ContentCategory(
        "tools", "TLS", "ابزار و اندیکاتور", "🧰",
        ("#ابزار_معاملاتی", "#اندیکاتور"), 1,
    ),
    "risk": ContentCategory(
        "risk", "RSK", "مدیریت ریسک", "🛡",
        ("#مدیریت_ریسک", "#Risk_Management"), 1,
    ),
    "trade_review": ContentCategory(
        "trade_review", "RVW", "مرور ستاپ", "🔍",
        ("#مرور_ستاپ", "#Trade_Review"), 1,
    ),
    "mindset": ContentCategory(
        "mindset", "MND", "ذهنیت معامله‌گر", "🧠",
        ("#روانشناسی_ترید", "#Trader_Mindset"), 1,
    ),
}


TEMPLATE_TO_CATEGORY = {
    "ict_education": "ict_education",
    "chart_breakdown": "daily_analysis",
    "quick_tip": "quick_tip",
    "market_news": "market_news",
    "important_news": "important_news",
    "news_alert": "news_alert",
    "tools": "tools",
    "risk": "risk",
    "trade_review": "trade_review",
    "mindset": "mindset",
}


_TOPIC_TAGS = {
    "fvg": "#FVG",
    "order_block": "#Order_Block",
    "liquidity": "#Liquidity",
    "mss": "#MSS",
    "displacement": "#Displacement",
    "premium_discount": "#Premium_Discount",
    "ote": "#OTE",
    "breaker": "#Breaker_Block",
    "pdh_pdl": "#PDH_PDL",
    "session_liquidity": "#Session_Liquidity",
    "fixed_risk": "#Fixed_Risk",
    "confirmation": "#Confirmation",
}

_MARKET_TAGS = (
    ("XAUUSD", "#XAUUSD"),
    ("GOLD", "#GOLD"),
    ("BTCUSD", "#BTCUSD"),
    ("BTC", "#BTC"),
    ("ETH", "#ETH"),
    ("SOL", "#SOL"),
    ("DXY", "#DXY"),
    ("EURUSD", "#EURUSD"),
    ("GBPUSD", "#GBPUSD"),
)


def category_for_template(template_key: str) -> ContentCategory:
    category_key = TEMPLATE_TO_CATEGORY.get(template_key, template_key)
    return CATEGORIES.get(category_key, CATEGORIES["ict_education"])


def category(category_key: str) -> ContentCategory:
    return CATEGORIES.get(category_key, CATEGORIES["ict_education"])


def _slug_token(value: str, fallback: str = "POST") -> str:
    token = re.sub(r"[^A-Za-z0-9_]+", "_", (value or "").strip()).strip("_")
    return (token or fallback).upper()[:28]


def make_post_id(category_key: str, scheduled_date: str, topic_slug: str) -> str:
    cat = category(category_key)
    day = re.sub(r"[^0-9]", "", scheduled_date)[:8] or "00000000"
    topic = _slug_token(topic_slug)
    return f"NX-{cat.code}-{day}-{topic}"


def tracking_hashtag(post_id: str) -> str:
    return "#" + re.sub(r"[^A-Za-z0-9_]+", "_", post_id).strip("_")[:64]


def detect_market_hashtags(text: str) -> list[str]:
    normalized = (text or "").upper()
    result: list[str] = []
    for needle, tag in _MARKET_TAGS:
        if re.search(rf"(?<![A-Z0-9]){re.escape(needle)}(?![A-Z0-9])", normalized):
            result.append(tag)
    return result


def build_hashtags(
    category_key: str,
    topic_slug: str,
    text: str = "",
    extras: list[str] | tuple[str, ...] | None = None,
) -> list[str]:
    tags: list[str] = ["#NEXUS", *category(category_key).hashtags]
    topic_tag = _TOPIC_TAGS.get(topic_slug)
    if topic_tag:
        tags.append(topic_tag)
    tags.extend(detect_market_hashtags(text))
    if extras:
        for raw in extras:
            raw = str(raw).strip()
            if not raw:
                continue
            if not raw.startswith("#"):
                raw = "#" + raw
            raw = re.sub(r"[^#\w\u0600-\u06FF]+", "_", raw, flags=re.UNICODE)
            tags.append(raw)

    result: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        key = tag.casefold()
        if key not in seen:
            seen.add(key)
            result.append(tag)
    return result[:8]


def public_post_link(public_channel_url: str, message_id: int) -> str | None:
    url = (public_channel_url or "").strip().rstrip("/")
    if not url or message_id <= 0:
        return None
    try:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() not in {"t.me", "telegram.me"}:
            return None
        slug = parsed.path.strip("/")
        if not slug or slug.startswith("+") or "/" in slug:
            return None
        return f"https://t.me/{slug}/{int(message_id)}"
    except Exception:
        return None


def safe_source_urls(urls: list[str] | tuple[str, ...] | None) -> list[str]:
    result: list[str] = []
    for raw in urls or ():
        value = str(raw).strip()
        try:
            parsed = urlparse(value)
            if parsed.scheme in {"http", "https"} and parsed.netloc:
                result.append(value)
        except Exception:
            continue
    return result[:4]
