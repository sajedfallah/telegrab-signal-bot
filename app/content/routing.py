from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from ..ecosystem import ecosystem_settings


# Public is intentionally strict: only these five editorial categories may
# publish to the general NEXUS channel. Everything educational is routed to
# Academy. Unknown/new categories fail closed until explicitly classified.
PUBLIC_CATEGORY_KEYS = frozenset({
    "daily_analysis",
    "quick_tip",
    "market_news",
    "important_news",
    "news_alert",
})

ACADEMY_CATEGORY_KEYS = frozenset({
    "ict_education",
    "tools",
    "risk",
    "trade_review",
    "mindset",
})


@dataclass(frozen=True)
class ChannelDestination:
    key: str
    label_fa: str
    chat_id: int | str
    channel_url: str


def route_key_for_category(category_key: str) -> str:
    key = str(category_key or "").strip()
    if key in PUBLIC_CATEGORY_KEYS:
        return "public"
    if key in ACADEMY_CATEGORY_KEYS:
        return "academy"
    raise ValueError(f"unclassified content category: {key or '<empty>'}")


def route_label_fa(category_key: str) -> str:
    route = route_key_for_category(category_key)
    return "NEXUS Academy" if route == "academy" else "کانال عمومی NEXUS"


def _public_username_target(url: str) -> str | None:
    value = str(url or "").strip().rstrip("/")
    if not value:
        return None
    try:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() not in {"t.me", "telegram.me"}:
            return None
        slug = parsed.path.strip("/")
        if not slug or slug.startswith("+") or "/" in slug:
            return None
        return "@" + slug.lstrip("@")
    except Exception:
        return None


def resolve_channel_destination(core_settings, category_key: str) -> ChannelDestination:
    route = route_key_for_category(category_key)
    if route == "public":
        return ChannelDestination(
            key="public",
            label_fa="کانال عمومی NEXUS",
            chat_id=core_settings.public_channel_id,
            channel_url=core_settings.public_channel_url,
        )

    raw_id = ecosystem_settings.academy_channel_id
    url = ecosystem_settings.academy_channel_url
    target: int | str | None = None
    if raw_id:
        try:
            target = int(raw_id)
        except ValueError:
            target = raw_id
    if target is None:
        target = _public_username_target(url)

    if target is None:
        raise RuntimeError(
            "ACADEMY_CHANNEL_ID or a public ACADEMY_CHANNEL_URL is required before direct educational publishing"
        )
    if not url:
        raise RuntimeError("ACADEMY_CHANNEL_URL is required to create traceable Telegram post permalinks")

    return ChannelDestination(
        key="academy",
        label_fa="NEXUS Academy",
        chat_id=target,
        channel_url=url,
    )
