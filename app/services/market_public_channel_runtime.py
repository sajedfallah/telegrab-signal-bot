from __future__ import annotations

"""Route NEXUS market editorial automation to the public NEXUS channel.

Product policy:
  * Morning Brief -> public NEXUS channel only.
  * Important market/news alerts -> public NEXUS channel only.
  * High-impact economic alerts -> public NEXUS channel only.

These channel posts are durable editorial content, so they are not scheduled for
transient-message deletion and they do not refresh private user dashboards.
"""

import logging
from datetime import datetime
from typing import Any

from app.services import market_brief_service as market


log = logging.getLogger(__name__)


def _public_target(main: Any) -> Any:
    target = getattr(main.settings, "public_channel_id", None)
    if target is None or str(target).strip() in {"", "0", "None"}:
        raise RuntimeError("NEXUS public channel is not configured")
    return target


def _channel_lang(main: Any) -> str:
    try:
        value = str(main.db.get_setting("market_public_channel_language", "fa") or "fa").strip().lower()
    except Exception:
        value = "fa"
    return value if value in {"fa", "en"} else "fa"


async def _send_public(main: Any, bot: Any, text: str, *, reason: str) -> bool:
    target = _public_target(main)
    try:
        await bot.send_message(
            target,
            text,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        log.info("market public-channel delivery: reason=%s target=%s status=sent", reason, target)
        return True
    except Exception as exc:
        log.warning(
            "market public-channel delivery failed: reason=%s target=%s error=%s",
            reason,
            target,
            exc,
        )
        return False


async def _broadcast_brief(
    main: Any,
    bot: Any,
    events: list[market.CalendarEvent],
    news: list[market.NewsItem],
    now_utc: datetime,
) -> tuple[int, int]:
    text = market.render_morning_brief(
        lang=_channel_lang(main),
        now_utc=now_utc,
        local_timezone=main.settings.timezone,
        events=events,
        news=news,
    )
    ok = await _send_public(main, bot, text, reason="morning_brief")
    return (1, 0) if ok else (0, 1)


async def _broadcast_news_item(main: Any, bot: Any, item: market.NewsItem) -> tuple[int, int]:
    text = market.render_news_alert(
        item,
        lang=_channel_lang(main),
        local_timezone=main.settings.timezone,
    )
    ok = await _send_public(main, bot, text, reason="market_news")
    return (1, 0) if ok else (0, 1)


async def _broadcast_event_alert(
    main: Any,
    bot: Any,
    event: market.CalendarEvent,
    minutes_left: int,
) -> tuple[int, int]:
    text = market.render_event_alert(
        event,
        lang=_channel_lang(main),
        local_timezone=main.settings.timezone,
        minutes_left=minutes_left,
    )
    ok = await _send_public(main, bot, text, reason="economic_alert")
    return (1, 0) if ok else (0, 1)


def install(main: Any) -> None:
    """Replace private-user market broadcasts with public-channel publication."""
    market._broadcast_brief = _broadcast_brief
    market._broadcast_news_item = _broadcast_news_item
    market._broadcast_event_alert = _broadcast_event_alert
    log.info("[NEXUS][MARKET_PUBLIC_CHANNEL][INSTALLED] target=%s", getattr(main.settings, "public_channel_id", None))
