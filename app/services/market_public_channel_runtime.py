from __future__ import annotations

"""Route NEXUS market editorial automation to the public NEXUS channel.

Product policy:
  * Public editorial is Persian-only and durable.
  * Standalone market news is limited to GOLD/XAU, Bitcoin/BTC and Dow Jones/DJIA.
  * Source names/article links are not shown in public news copy.
  * Morning publication is exactly an ordered three-part suite:
      1) NEXUS Morning Brief
      2) GOLD ICT analysis/scenarios
      3) Bitcoin ICT analysis/scenarios
  * High-impact economic alerts remain enabled as separate risk alerts.
  * Related news imagery is best-effort when article metadata provides it.
"""

import asyncio
import html
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from app.services import market_brief_service as market
from app.services import market_editorial_service as editorial
from app.services import market_ict_service as ict


log = logging.getLogger(__name__)

_FOCUS_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("GOLD", re.compile(r"(?:\bgold\b|\bxau(?:usd|usdt)?\b|\bbullion\b)", re.I)),
    ("BTC", re.compile(r"(?:\bbitcoin\b|\bbtc(?:usd|usdt)?\b)", re.I)),
    ("DOW", re.compile(r"(?:\bdow\s+jones\b|\bdjia\b|\bdow\s+30\b|\bdow\s+industrials?\b)", re.I)),
)


def _public_target(main: Any) -> Any:
    target = getattr(main.settings, "public_channel_id", None)
    if target is None or str(target).strip() in {"", "0", "None"}:
        raise RuntimeError("NEXUS public channel is not configured")
    return target


def _channel_lang(main: Any) -> str:
    return "fa"


def _focus_score(title: str) -> int:
    text = str(title or "")
    score = 0
    for _, pattern in _FOCUS_PATTERNS:
        if pattern.search(text):
            score = max(score, 8)
    return score


def _is_focus_news(item: market.NewsItem) -> bool:
    return _focus_score(item.title) > 0


def _focused_important_recent_news(
    items: list[market.NewsItem],
    *,
    now_utc: datetime | None = None,
    minimum_score: int = 5,
    max_age_minutes: int = 180,
) -> list[market.NewsItem]:
    """Return only direct GOLD/BTC/Dow headlines, while preserving importance/age gates."""
    now = now_utc or datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=max(1, int(max_age_minutes)))
    ranked: list[tuple[int, datetime, market.NewsItem]] = []
    for item in items:
        focus = _focus_score(item.title)
        if focus <= 0:
            continue
        effective_score = max(int(item.score), focus)
        if effective_score < max(1, int(minimum_score)):
            continue
        if item.published_at and item.published_at < cutoff:
            continue
        ranked.append((effective_score, item.published_at or now, item))
    ranked.sort(key=lambda row: (row[0], row[1]), reverse=True)
    return [row[2] for row in ranked]


def _strip_source_line(text: str) -> str:
    """Never expose editorial source labels in public news messages/captions."""
    lines = []
    for line in str(text or "").splitlines():
        compact = line.strip()
        if compact.startswith("📰 منبع:") or compact.lower().startswith("source:"):
            continue
        lines.append(line)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


async def _send_public(
    main: Any,
    bot: Any,
    text: str,
    *,
    reason: str,
    image_url: str = "",
) -> bool:
    target = _public_target(main)
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
    headlines = _focused_important_recent_news(
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
    for _, fa_title in zip(headlines, headline_titles):
        if not fa_title:
            continue
        lines.append(f"• {html.escape(fa_title)}")
        written += 1
    if written == 0:
        lines.append("• در حال حاضر خبر مهم تازه‌ای درباره طلا، بیت‌کوین یا داوجونز دریافت نشده است.")

    lines += [
        "",
        "⚠️ اطراف رویدادهای مهم اقتصادی احتمال افزایش نوسان، اسپرد و اسلیپیج وجود دارد.",
    ]
    return "\n".join(lines)


def _component_key(component: str) -> str:
    return f"market_public_morning_{component}_last_date"


def _component_done(main: Any, component: str, today_key: str) -> bool:
    return main.db.get_setting(_component_key(component), "").strip() == today_key


def _mark_component(main: Any, component: str, today_key: str) -> None:
    main.db.set_setting(_component_key(component), today_key)


async def _broadcast_brief(
    main: Any,
    bot: Any,
    events: list[market.CalendarEvent],
    news: list[market.NewsItem],
    now_utc: datetime,
) -> tuple[int, int]:
    """Publish the ordered 3-message morning suite with per-component retry safety."""
    today_key = now_utc.astimezone(ZoneInfo(main.settings.timezone)).date().isoformat()

    if not _component_done(main, "brief", today_key):
        text = await _render_persian_morning_brief(main, events, news, now_utc)
        if not await _send_public(main, bot, text, reason="morning_brief"):
            return (0, 1)
        _mark_component(main, "brief", today_key)

    if not _component_done(main, "gold_ict", today_key):
        try:
            gold_text = await ict.build_daily_ict_message(
                symbol="XAUUSDT",
                asset_fa="طلای جهانی",
                now_utc=now_utc,
                local_timezone=main.settings.timezone,
            )
        except Exception as exc:
            log.warning("morning GOLD ICT preparation failed: %s", exc)
            return (0, 1)
        if not await _send_public(main, bot, gold_text, reason="morning_gold_ict"):
            return (0, 1)
        _mark_component(main, "gold_ict", today_key)

    if not _component_done(main, "btc_ict", today_key):
        try:
            btc_text = await ict.build_daily_ict_message(
                symbol="BTCUSDT",
                asset_fa="بیت‌کوین",
                now_utc=now_utc,
                local_timezone=main.settings.timezone,
            )
        except Exception as exc:
            log.warning("morning BTC ICT preparation failed: %s", exc)
            return (0, 1)
        if not await _send_public(main, bot, btc_text, reason="morning_btc_ict"):
            return (0, 1)
        _mark_component(main, "btc_ict", today_key)

    # The core worker marks morning_brief_last_date only when this suite is complete.
    return (3, 0)


async def _broadcast_news_item(main: Any, bot: Any, item: market.NewsItem) -> tuple[int, int]:
    if not _is_focus_news(item):
        log.info("market news suppressed by GOLD/BTC/Dow focus policy: key=%s", item.key)
        return (0, 0)

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
        _strip_source_line(payload.text),
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
    """Replace private market broadcasts with focused Persian public editorial."""
    market.important_recent_news = _focused_important_recent_news
    market._broadcast_brief = _broadcast_brief
    market._broadcast_news_item = _broadcast_news_item
    market._broadcast_event_alert = _broadcast_event_alert
    log.info(
        "[NEXUS][MARKET_PUBLIC_CHANNEL][INSTALLED] target=%s language=fa focus=GOLD,BTC,DOW morning_suite=3 native_text=true image_enrichment=true",
        getattr(main.settings, "public_channel_id", None),
    )
