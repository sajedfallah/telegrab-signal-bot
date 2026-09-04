from __future__ import annotations

"""Focused NEXUS market editorial for the public channel.

Product policy:
  * Public editorial is Persian-only and durable.
  * Market news is strictly limited to GOLD/XAU, Bitcoin/BTC and Dow Jones/DJI/US30.
  * Source names/article links are never shown in public copy.
  * Every morning is one ordered, retry-safe three-message suite:
      1) NEXUS Morning Brief
      2) XAU/USD ICT analysis/scenarios
      3) BTC/USD ICT analysis/scenarios
  * Routine standalone news/economic alerts are quiet during the morning window;
    only extraordinary focused breaking news can bypass that quiet window.
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
    ("GOLD", re.compile(r"(?:\bgold\b|\bxau(?:[/_-]?usd|usd|usdt)?\b|\bbullion\b)", re.I)),
    ("BTC", re.compile(r"(?:\bbitcoin\b|\bbtc(?:[/_-]?usd|usd|usdt)?\b)", re.I)),
    (
        "DOW",
        re.compile(
            r"(?:\bdow\s+jones\b|\bdow\s*30\b|\bdjia\b|\bdji\b|\bus30\b|\bwall\s+street\s+30\b|\bdow\s+industrials?\b)",
            re.I,
        ),
    ),
)
_EXTRAORDINARY_RE = re.compile(
    r"(?:\bbreaking\b|\burgent\b|\bflash\b|\bemergency\b|\bcrash\w*\b|\bplung\w*\b|"
    r"\bsurg\w*\b|\bspik\w*\b|\battack\w*\b|\bwar\b|\bintervention\b|\bhalt\w*\b|"
    r"\brecord\s+high\b|\brecord\s+low\b)",
    re.I,
)
_KNOWN_SOURCE_NAMES = (
    "FXStreet",
    "CoinDesk",
    "Reuters",
    "Bloomberg",
    "CNBC",
    "Associated Press",
    "Wall Street Journal",
    "WSJ",
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
    return 8 if any(pattern.search(text) for _, pattern in _FOCUS_PATTERNS) else 0


def _is_focus_news(item: market.NewsItem) -> bool:
    return _focus_score(item.title) > 0


def _focused_important_recent_news(
    items: list[market.NewsItem],
    *,
    now_utc: datetime | None = None,
    minimum_score: int = 5,
    max_age_minutes: int = 180,
) -> list[market.NewsItem]:
    """Return only direct GOLD/BTC/Dow headlines while preserving freshness gates."""
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


def _morning_quiet(main: Any, now_utc: datetime | None = None) -> bool:
    now = now_utc or datetime.now(timezone.utc)
    local = now.astimezone(ZoneInfo(main.settings.timezone))
    return 0 <= local.hour < 12


def _extraordinary_focus_news(item: market.NewsItem) -> bool:
    return _is_focus_news(item) and bool(_EXTRAORDINARY_RE.search(str(item.title or ""))) and max(
        int(item.score), _focus_score(item.title)
    ) >= 8


def _sanitize_public_news_text(text: str, item: market.NewsItem) -> str:
    """Remove source labels/names from public Telegram news copy."""
    source_names = [str(getattr(item, "source", "") or "").strip(), *_KNOWN_SOURCE_NAMES]
    lines: list[str] = []
    for line in str(text or "").splitlines():
        compact = re.sub(r"<[^>]+>", "", line).strip().lower()
        if compact.startswith("📰 منبع:") or compact.startswith("منبع:") or compact.startswith("source:"):
            continue
        cleaned = line
        for name in source_names:
            if name:
                cleaned = re.sub(re.escape(name), "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s{2,}", " ", cleaned).rstrip()
        lines.append(cleaned)
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
    for item, fa_title in zip(headlines, headline_titles):
        if not fa_title:
            continue
        clean_title = _sanitize_public_news_text(str(fa_title), item).strip()
        if not clean_title:
            continue
        lines.append(f"• {html.escape(clean_title)}")
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
    return str(main.db.get_setting(_component_key(component), "") or "").strip() == today_key


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

    # Prepare all content before the first Telegram send. A temporary market-data
    # failure therefore cannot intentionally produce a one-message morning pack.
    try:
        brief_task = asyncio.create_task(_render_persian_morning_brief(main, events, news, now_utc))
        gold_task = asyncio.create_task(
            ict.build_daily_ict_message(
                symbol="XAUUSD",
                asset_fa="طلای جهانی (XAU/USD)",
                now_utc=now_utc,
                local_timezone=main.settings.timezone,
            )
        )
        btc_task = asyncio.create_task(
            ict.build_daily_ict_message(
                symbol="BTCUSD",
                asset_fa="بیت‌کوین (BTC/USD)",
                now_utc=now_utc,
                local_timezone=main.settings.timezone,
            )
        )
        brief_text, gold_text, btc_text = await asyncio.gather(brief_task, gold_task, btc_task)
    except Exception as exc:
        log.warning("morning 3-message suite preparation failed: %s", exc)
        return (0, 1)

    messages = (
        ("brief", brief_text, "morning_brief"),
        ("gold_ict", gold_text, "morning_gold_ict"),
        ("btc_ict", btc_text, "morning_btc_ict"),
    )
    failed = 0
    for component, text, reason in messages:
        if _component_done(main, component, today_key):
            continue
        if await _send_public(main, bot, text, reason=reason):
            _mark_component(main, component, today_key)
        else:
            failed += 1
            break

    complete = all(_component_done(main, component, today_key) for component, _, _ in messages)
    if complete:
        # The core worker can now safely set morning_brief_last_date.
        return (3, 0)
    # Returning sent=0 prevents the legacy worker from falsely marking the suite
    # complete when one Telegram send succeeded but a later component failed.
    return (0, max(1, failed))


async def _broadcast_news_item(main: Any, bot: Any, item: market.NewsItem) -> tuple[int, int]:
    if not _is_focus_news(item):
        log.info("market news suppressed by GOLD/BTC/Dow focus policy: key=%s", item.key)
        return (0, 0)

    if _morning_quiet(main) and not _extraordinary_focus_news(item):
        log.info("routine focused news suppressed during morning quiet window: key=%s", item.key)
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

    public_text = _sanitize_public_news_text(payload.text, item)
    ok = await _send_public(
        main,
        bot,
        public_text,
        reason="market_news_extraordinary" if _morning_quiet(main) else "market_news",
        image_url=payload.image_url,
    )
    return (1, 0) if ok else (0, 1)


async def _broadcast_event_alert(
    main: Any,
    bot: Any,
    event: market.CalendarEvent,
    minutes_left: int,
) -> tuple[int, int]:
    # Morning high-impact events are already consolidated into message #1.
    if _morning_quiet(main):
        log.info("routine economic alert suppressed during morning quiet window: event=%s", event.key)
        return (0, 0)

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
    # The worker calls market.important_recent_news before dispatching items. Patch
    # that selector too, so unrelated assets are discarded before publication.
    market.important_recent_news = _focused_important_recent_news
    market._broadcast_brief = _broadcast_brief
    market._broadcast_news_item = _broadcast_news_item
    market._broadcast_event_alert = _broadcast_event_alert
    log.info(
        "[NEXUS][MARKET_PUBLIC_CHANNEL][INSTALLED] target=%s language=fa focus=GOLD,BTC,DOW morning_suite=3 morning_quiet=true source_hidden=true image_enrichment=true",
        getattr(main.settings, "public_channel_id", None),
    )
