from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse

from ..ecosystem import ecosystem_settings


# Public is intentionally strict: only these five editorial categories may
# publish to the general NEXUS destination. Everything educational is routed to
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
    message_thread_id: int | None = None


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


def _parse_target(raw: str) -> int | str:
    value = str(raw or "").strip()
    if not value:
        raise ValueError("empty Telegram target")
    try:
        return int(value)
    except ValueError:
        return value


def _topic_id_from_env(name: str, *, fallback_name: str | None = None) -> int | None:
    raw = os.getenv(name, "").strip()
    if not raw and fallback_name:
        raw = os.getenv(fallback_name, "").strip()
    if not raw:
        return None
    try:
        topic_id = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if topic_id <= 0:
        raise RuntimeError(f"{name} must be greater than zero")
    return topic_id


def _public_topic_id() -> int | None:
    return _topic_id_from_env("PUBLIC_CONTENT_TOPIC_ID", fallback_name="MARKET_CONTENT_TOPIC_ID")


def _academy_topic_id() -> int | None:
    return _topic_id_from_env("ACADEMY_CONTENT_TOPIC_ID")


def resolve_channel_destination(core_settings, category_key: str) -> ChannelDestination:
    route = route_key_for_category(category_key)
    if route == "public":
        # v0.6.5+: public editorial may live in a Telegram forum topic instead
        # of a standalone channel. PUBLIC_CONTENT_* is canonical; the older
        # MARKET_CONTENT_CHANNEL_ID remains a backward-compatible target.
        raw_chat = (
            os.getenv("PUBLIC_CONTENT_CHAT_ID", "").strip()
            or os.getenv("MARKET_CONTENT_CHANNEL_ID", "").strip()
        )
        chat_id: int | str = _parse_target(raw_chat) if raw_chat else core_settings.public_channel_id
        channel_url = (
            os.getenv("PUBLIC_CONTENT_URL", "").strip()
            or core_settings.public_channel_url
        )
        return ChannelDestination(
            key="public",
            label_fa="کانال عمومی NEXUS",
            chat_id=chat_id,
            channel_url=channel_url,
            message_thread_id=_public_topic_id(),
        )

    # Academy may either publish to the historical standalone Academy channel
    # or to a dedicated Telegram forum topic. ACADEMY_CONTENT_* is canonical
    # when provided and is intentionally independent from FREE_SIGNAL_*.
    raw_academy_chat = os.getenv("ACADEMY_CONTENT_CHAT_ID", "").strip()
    raw_id = ecosystem_settings.academy_channel_id
    url = (
        os.getenv("ACADEMY_CONTENT_URL", "").strip()
        or ecosystem_settings.academy_channel_url
    )

    target: int | str | None = None
    if raw_academy_chat:
        target = _parse_target(raw_academy_chat)
    elif raw_id:
        try:
            target = int(raw_id)
        except ValueError:
            target = raw_id
    if target is None:
        target = _public_username_target(url)

    if target is None:
        raise RuntimeError(
            "ACADEMY_CONTENT_CHAT_ID, ACADEMY_CHANNEL_ID or a public ACADEMY_CHANNEL_URL is required before educational publishing"
        )
    if not url:
        # A forum topic can still publish without a public permalink URL. Keep
        # routing operational and leave permalink generation disabled upstream.
        url = ""

    return ChannelDestination(
        key="academy",
        label_fa="NEXUS Academy",
        chat_id=target,
        channel_url=url,
        message_thread_id=_academy_topic_id(),
    )
