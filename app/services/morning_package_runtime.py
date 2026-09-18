from __future__ import annotations

import asyncio
import html
import logging
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from app.daily_stickers.service import enabled as daily_stickers_enabled
from app.daily_stickers.service import send_for_date
from app.services import market_brief_service as market
from app.services import market_ict_service as ict
from app.services import market_public_channel_runtime as public

log = logging.getLogger(__name__)


def _fa_digits(value: object) -> str:
    text = str(value)
    table = str.maketrans("0123456789,.:-", "۰۱۲۳۴۵۶۷۸۹٬٫:−")
    return text.translate(table)


def _price(value: float | None, symbol: str) -> str:
    return _fa_digits(ict._fmt(value, symbol))


def _zone(zone: Any, symbol: str) -> str:
    if zone is None:
        return "—"
    return f"{_price(zone.low, symbol)} تا {_price(zone.high, symbol)}"


def _entry_status(snapshot: Any) -> str:
    trigger = str(snapshot.trigger_state or "")
    if "MSS صعودی" in trigger and "دیده می‌شود" in trigger:
        return "🟢 آماده بررسی خرید"
    if "MSS نزولی" in trigger and "دیده می‌شود" in trigger:
        return "🔴 آماده بررسی فروش"
    return "🟡 صبر"


def render_concise_ict(snapshot: Any, *, asset_fa: str, now_utc: datetime, local_timezone: str) -> str:
    bias_fa = {"BULLISH": "صعودی", "BEARISH": "نزولی", "NEUTRAL": "خنثی"}.get(snapshot.bias, "خنثی")
    if snapshot.bias == "BULLISH":
        primary_zone = snapshot.bullish_fvg or snapshot.bullish_ob
        target = snapshot.buy_liquidity
        zone_label = "ناحیه حمایتی"
    elif snapshot.bias == "BEARISH":
        primary_zone = snapshot.bearish_fvg or snapshot.bearish_ob
        target = snapshot.sell_liquidity
        zone_label = "ناحیه مقاومتی"
    else:
        primary_zone = snapshot.bullish_fvg or snapshot.bearish_fvg or snapshot.bullish_ob or snapshot.bearish_ob
        target = snapshot.buy_liquidity
        zone_label = "ناحیه واکنش"

    asset_name = "طلا" if "طلا" in asset_fa else "بیت‌کوین"
    emoji = "🥇" if asset_name == "طلا" else "₿"
    return "\n".join(
        [
            f"<b>{emoji} نقشه امروز {asset_name}</b>",
            f"جهت روز: <b>{bias_fa}</b>",
            f"ساختار یک‌ساعته: <b>{'مثبت' if snapshot.bias == 'BULLISH' else 'منفی' if snapshot.bias == 'BEARISH' else 'رنج'}</b>",
            f"{zone_label} پانزده‌دقیقه: <b>{_zone(primary_zone, snapshot.symbol)}</b>",
            f"هدف نقدینگی: <b>{_price(target, snapshot.symbol)}</b>",
            "تأیید پنج‌دقیقه: جمع‌آوری نقدینگی + تغییر ساختار + بازآزمایی",
            f"وضعیت: <b>{_entry_status(snapshot)}</b>",
            "ورود فقط بعد از تأیید کامل.",
        ]
    )


async def render_concise_morning(main: Any, events: list[market.CalendarEvent], news: list[market.NewsItem], now_utc: datetime) -> str:
    tz = ZoneInfo(main.settings.timezone)
    local_now = now_utc.astimezone(tz)
    high = market.today_high_impact_events(events, now_utc=now_utc, local_timezone=main.settings.timezone)[:4]
    headlines = public._focused_important_recent_news(news, now_utc=now_utc, minimum_score=5, max_age_minutes=12 * 60)[:3]

    event_titles = await asyncio.gather(*(public.editorial.translate_event_title(x.title, country=x.country) for x in high)) if high else []
    headline_titles = await asyncio.gather(*(public.editorial.translate_to_persian(x.title) for x in headlines)) if headlines else []

    lines = [
        "<b>☀️ صبح بخیر از نکسوس</b>",
        f"📅 {_fa_digits(local_now.strftime('%Y/%m/%d'))}",
    ]
    if high:
        lines += ["", "<b>🔴 زمان خبرهای مهم امروز</b>"]
        for event, title in zip(high, event_titles):
            lines.append(f"• {_fa_digits(market._event_time_text(event, tz))} — {html.escape(title)}")
    else:
        lines += ["", "🔴 امروز خبر مهم زمان‌بندی‌شده‌ای نداریم."]

    clean_headlines: list[str] = []
    for item, title in zip(headlines, headline_titles):
        if title:
            clean = public._sanitize_public_news_text(str(title), item).strip()
            if clean:
                clean_headlines.append(clean)
    if clean_headlines:
        lines += ["", "<b>📰 خبرهای منتخب</b>"]
        lines.extend(f"• {html.escape(x)}" for x in clean_headlines)

    lines += ["", "نزدیک خبر عجله نکن؛ کیفیت ورود مهم‌تر از تعداد معامله‌هاست."]
    return "\n".join(lines)


async def _send_sticker_first(main: Any, bot: Any, now_utc: datetime) -> bool:
    if not daily_stickers_enabled():
        log.info("daily stickers disabled; morning text package continues")
        return True
    day = now_utc.astimezone(ZoneInfo(main.settings.timezone)).date()
    try:
        sent, reason, _ = await send_for_date(bot, day)
    except Exception:
        log.exception("daily sticker delivery failed for %s; morning package paused to preserve order", day)
        return False
    if sent:
        await asyncio.sleep(2.0)
        return True
    if reason == "already_sent":
        return True
    if reason == "missing_sticker":
        log.warning("daily sticker missing for %s; morning text package continues", day)
        return True
    log.warning("daily sticker not sent for %s: %s", day, reason)
    return False


def _concise_event_text(main: Any, event: market.CalendarEvent, fa_title: str, minutes_left: int) -> str:
    tz = ZoneInfo(main.settings.timezone)
    when = _fa_digits(market._event_time_text(event, tz))
    return (
        "<b>⏰ هشدار خبر اقتصادی نکسوس</b>\n\n"
        f"🔴 <b>{html.escape(fa_title)}</b>\n"
        f"زمان خبر: <b>{when}</b>\n"
        f"حدود <b>{_fa_digits(max(0, minutes_left))} دقیقه</b> دیگر\n\n"
        "نزدیک خبر، نوسان و اسلیپیج می‌تواند بیشتر شود."
    )


def install(main: Any) -> None:
    """Install sticker-first morning package, concise Persian copy and dual economic alerts."""
    original_brief = market._broadcast_brief

    async def sticker_first_brief(main_arg: Any, bot: Any, events: list[market.CalendarEvent], news: list[market.NewsItem], now_utc: datetime):
        if not await _send_sticker_first(main_arg, bot, now_utc):
            return (0, 1)
        result = await original_brief(main_arg, bot, events, news, now_utc)
        return result

    async def dual_event_alert(main_arg: Any, bot: Any, event: market.CalendarEvent, minutes_left: int):
        fa_title = await public.editorial.translate_event_title(event.title, country=event.country)
        text = _concise_event_text(main_arg, event, fa_title, minutes_left)

        sent = failed = 0
        if await public._send_public(main_arg, bot, text, reason="economic_alert"):
            sent += 1
        else:
            failed += 1

        ttl = market._int_setting(main_arg, "economic_alert_ttl_seconds", 2 * 60 * 60, 300, 43200)
        for uid in market._audience_ids(main_arg, "market_news_audience", "all"):
            user_text = text if main_arg.get_lang(uid) == "fa" else market.render_event_alert(
                event,
                lang="en",
                local_timezone=main_arg.settings.timezone,
                minutes_left=minutes_left,
            )
            if await market._send_editorial_message(main_arg, bot, uid, user_text, ttl_seconds=ttl, reason="economic_alert"):
                sent += 1
            else:
                failed += 1
            await asyncio.sleep(0.05)
        return sent, failed

    public._render_persian_morning_brief = render_concise_morning
    ict.render_persian_ict = render_concise_ict
    market._broadcast_brief = sticker_first_brief
    market._broadcast_event_alert = dual_event_alert

    log.info("[NEXUS][MORNING_PACKAGE][INSTALLED] order=sticker,brief,gold,btc concise_fa=true dual_news_alert=true")
