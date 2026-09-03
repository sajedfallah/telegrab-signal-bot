from __future__ import annotations

"""Route NEXUS market editorial automation to the public NEXUS channel.

Product policy:
  * Morning Brief -> public NEXUS channel only.
  * Important market/news alerts -> public NEXUS channel only.
  * High-impact economic alerts -> public NEXUS channel only.
  * Public market editorial is Persian-only.
  * News is published as native Telegram text/caption, not as a clickable source headline.
  * A related article image is attached when OpenGraph/Twitter metadata provides one.

These channel posts are durable editorial content, so they are not scheduled for
transient-message deletion and they do not refresh private user dashboards.
"""

import asyncio
import html
import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.services import market_brief_service as market
from app.services import market_editorial_service as editorial


log = logging.getLogger(__name__)


def _public_target(main: Any) -> Any:
    target = getattr(main.settings, "public_channel_id", None)
    if target is None or str(target).strip() in {"", "0", "None"}:
        raise RuntimeError("NEXUS public channel is not configured")
    return target


def _channel_lang(main: Any) -> str:
    # Product requirement: public NEXUS market/news editorial is always Persian.
    return "fa"


async def _send_public(
    main: Any,
    bot: Any,
    text: str,
    *,
    reason: str,
    image_url: str = "",
) -> bool:
    target = _public_target(main)

    # Prefer a real related image when the source article exposes one. If Telegram
    # cannot fetch that image, fall back to the same Persian native-text post.
    if image_url:
        try:
            await bot.send_photo(
                target,
                photo=image_url,
                caption=text,
                parse_mode="HTML",
            )
            log.info(
                "market public-channel delivery: reason=%s target=%s status=sent_with_image",
                reason,
                target,
            )
            return True
        except Exception as exc:
            log.info(
                "market public-channel image unavailable; falling back to text: reason=%s target=%s error=%s",
                reason,
                target,
                exc,
            )

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


async def _render_persian_morning_brief(
    main: Any,
    events: list[market.CalendarEvent],
    news: list[market.NewsItem],
    now_utc: datetime,
) -> str:
    tz = ZoneInfo(main.settings.timezone)
    local_now = now_utc.astimezone(tz)
    high = market.today_high_impact_events(
        events,
        now_utc=now_utc,
        local_timezone=main.settings.timezone,
    )[:8]
    headlines = market.important_recent_news(
        news,
        now_utc=now_utc,
        minimum_score=4,
        max_age_minutes=12 * 60,
    )[:5]

    event_titles = await asyncio.gather(
        *(editorial.translate_event_title(x.title, country=x.country) for x in high)
    ) if high else []
    headline_titles = await asyncio.gather(
        *(editorial.translate_to_persian(x.title) for x in headlines)
    ) if headlines else []

    lines = [
        "<b>☀️ گزارش صبحگاهی NEXUS</b>",
        f"📅 {local_now.strftime('%Y/%m/%d')}",
        "",
        "<b>🔴 رویدادهای مهم اقتصادی امروز</b>",
    ]

    if high:
        for event, fa_title in zip(high, event_titles):
            forecast = html.escape(event.forecast or "—")
            previous = html.escape(event.previous or "—")
            country = html.escape(event.country or "—")
            title = html.escape(fa_title)
            extra = ""
            if event.forecast or event.previous:
                extra = f" | پیش‌بینی: {forecast} | قبلی: {previous}"
            lines.append(
                f"• {market._event_time_text(event, tz)} | <b>{country}</b> | {title}{extra}"
            )
    else:
        lines.append("• رویداد مهم اقتصادی ثبت‌شده‌ای برای امروز پیدا نشد.")

    lines += ["", "<b>📰 مهم‌ترین خبرهای بازار</b>"]
    written = 0
    for item, fa_title in zip(headlines, headline_titles):
        if not fa_title:
            continue
        lines.append(
            f"• {html.escape(fa_title)} — <b>{html.escape(item.source or 'خبرگزاری')}</b>"
        )
        written += 1
    if written == 0:
        lines.append("• در حال حاضر خبر مهم تازه و قابل انتشار به فارسی دریافت نشده است.")

    lines += [
        "",
        "⚠️ اطراف رویدادهای مهم اقتصادی احتمال افزایش نوسان، اسپرد و اسلیپیج وجود دارد.",
    ]
    return "\n".join(lines)


async def _broadcast_brief(
    main: Any,
    bot: Any,
    events: list[market.CalendarEvent],
    news: list[market.NewsItem],
    now_utc: datetime,
) -> tuple[int, int]:
    text = await _render_persian_morning_brief(main, events, news, now_utc)
    ok = await _send_public(main, bot, text, reason="morning_brief")
    return (1, 0) if ok else (0, 1)


async def _broadcast_news_item(main: Any, bot: Any, item: market.NewsItem) -> tuple[int, int]:
    payload = await editorial.prepare_persian_news_payload(
        item,
        local_timezone=main.settings.timezone,
    )
    if payload is None:
        log.warning(
            "market news suppressed because Persian editorial translation was unavailable: key=%s source=%s",
            item.key,
            item.source,
        )
        return (0, 1)

    ok = await _send_public(
        main,
        bot,
        payload.text,
        reason="market_news",
        image_url=payload.image_url,
    )
    return (1, 0) if ok else (0, 1)


async def _broadcast_event_alert(
    main: Any,
    bot: Any,
    event: market.CalendarEvent,
    minutes_left: int,
) -> tuple[int, int]:
    tz = ZoneInfo(main.settings.timezone)
    fa_title = await editorial.translate_event_title(event.title, country=event.country)
    when = market._event_time_text(event, tz)
    country = html.escape(event.country or "—")
    title = html.escape(fa_title)
    forecast = html.escape(event.forecast or "—")
    previous = html.escape(event.previous or "—")
    text = (
        "<b>⏰ هشدار خبر اقتصادی NEXUS</b>\n\n"
        f"🔴 <b>{country} — {title}</b>\n"
        f"🕒 زمان: <b>{when}</b> | حدود <b>{max(0, minutes_left)} دقیقه</b> دیگر\n"
        f"📊 پیش‌بینی: <b>{forecast}</b> | قبلی: <b>{previous}</b>\n\n"
        "⚠️ احتمال افزایش نوسان، اسپرد و اسلیپیج وجود دارد."
    )
    ok = await _send_public(main, bot, text, reason="economic_alert")
    return (1, 0) if ok else (0, 1)


def install(main: Any) -> None:
    """Replace private-user market broadcasts with Persian public-channel publication."""
    market._broadcast_brief = _broadcast_brief
    market._broadcast_news_item = _broadcast_news_item
    market._broadcast_event_alert = _broadcast_event_alert
    log.info(
        "[NEXUS][MARKET_PUBLIC_CHANNEL][INSTALLED] target=%s language=fa native_text=true image_enrichment=true",
        getattr(main.settings, "public_channel_id", None),
    )
