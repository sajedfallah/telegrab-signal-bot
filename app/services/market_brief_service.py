from __future__ import annotations

import asyncio
import hashlib
import html
import json
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import aiohttp


log = logging.getLogger(__name__)

DEFAULT_CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
DEFAULT_NEWS_FEEDS = (
    ("FXStreet", "https://xml.fxstreet.com/news/forex-news/index.xml"),
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
)
DEFAULT_MORNING_TIME = "08:00"
DEFAULT_NEWS_POLL_MINUTES = 10
DEFAULT_CALENDAR_POLL_MINUTES = 15
DEFAULT_EVENT_LEAD_MINUTES = 30
DEFAULT_BRIEF_TTL_SECONDS = 12 * 60 * 60
DEFAULT_NEWS_TTL_SECONDS = 6 * 60 * 60

IMPORTANT_KEYWORDS: dict[str, int] = {
    "fomc": 7,
    "federal reserve": 6,
    "fed chair": 5,
    "powell": 5,
    "interest rate": 6,
    "rate decision": 7,
    "rate hike": 5,
    "rate cut": 5,
    "cpi": 7,
    "inflation": 5,
    "pce": 6,
    "nonfarm": 7,
    "payroll": 6,
    "nfp": 7,
    "unemployment": 5,
    "gdp": 4,
    "retail sales": 4,
    "ecb": 5,
    "boj": 5,
    "boe": 5,
    "treasury": 3,
    "bond yield": 4,
    "yields": 3,
    "dollar index": 5,
    "dxy": 5,
    "gold": 5,
    "xau": 5,
    "bitcoin": 5,
    "btc": 5,
    "ethereum": 4,
    "solana": 4,
    "oil": 4,
    "opec": 5,
    "war": 5,
    "missile": 5,
    "sanction": 4,
    "tariff": 4,
    "sec": 3,
    "etf": 3,
    "hack": 6,
    "exploit": 6,
}


@dataclass(frozen=True)
class NewsItem:
    title: str
    link: str
    source: str
    published_at: datetime | None
    score: int

    @property
    def key(self) -> str:
        raw = f"{self.source}|{self.title}|{self.link}".encode("utf-8", "ignore")
        return hashlib.sha256(raw).hexdigest()[:24]


@dataclass(frozen=True)
class CalendarEvent:
    title: str
    country: str
    impact: str
    when_utc: datetime | None
    time_label: str
    forecast: str = ""
    previous: str = ""
    link: str = ""

    @property
    def key(self) -> str:
        when = self.when_utc.isoformat() if self.when_utc else self.time_label
        raw = f"{self.country}|{self.title}|{when}".encode("utf-8", "ignore")
        return hashlib.sha256(raw).hexdigest()[:24]


def _clean_text(value: str | None) -> str:
    text = re.sub(r"\s+", " ", html.unescape(str(value or ""))).strip()
    return text


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _child_text(node: ET.Element, names: tuple[str, ...]) -> str:
    wanted = {x.lower() for x in names}
    for child in list(node):
        if _local_name(child.tag) in wanted:
            return _clean_text(child.text)
    return ""


def _parse_datetime_text(value: str) -> datetime | None:
    raw = _clean_text(value)
    if not raw:
        return None
    try:
        parsed = parsedate_to_datetime(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        pass
    candidate = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def score_headline(title: str) -> int:
    lower = f" {title.lower()} "
    score = 0
    for keyword, weight in IMPORTANT_KEYWORDS.items():
        if keyword in lower:
            score += weight
    if any(token in lower for token in ("breaking", "urgent", "surges", "plunges", "jumps", "slumps")):
        score += 2
    return score


def parse_rss(xml_text: str, source_hint: str = "News") -> list[NewsItem]:
    root = ET.fromstring(xml_text)
    items: list[NewsItem] = []
    for node in root.iter():
        if _local_name(node.tag) not in {"item", "entry"}:
            continue
        title = _child_text(node, ("title",))
        if not title:
            continue
        link = _child_text(node, ("link", "guid"))
        if not link:
            for child in list(node):
                if _local_name(child.tag) == "link":
                    link = _clean_text(child.attrib.get("href"))
                    if link:
                        break
        published = _child_text(node, ("pubdate", "published", "updated", "date"))
        source = _child_text(node, ("source",)) or source_hint
        items.append(
            NewsItem(
                title=title,
                link=link,
                source=source,
                published_at=_parse_datetime_text(published),
                score=score_headline(title),
            )
        )
    return items


def _parse_calendar_when(date_text: str, time_text: str, feed_timezone: str = "UTC") -> datetime | None:
    date_raw = _clean_text(date_text)
    time_raw = _clean_text(time_text)
    if not date_raw or not time_raw or time_raw.lower() in {"all day", "tentative"}:
        return None
    parsed_date = None
    for fmt in ("%m-%d-%Y", "%m/%d/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            parsed_date = datetime.strptime(date_raw, fmt).date()
            break
        except ValueError:
            continue
    if parsed_date is None:
        return None
    parsed_time = None
    normalized = time_raw.replace(" ", "").upper()
    for fmt in ("%I:%M%p", "%I%p", "%H:%M"):
        try:
            parsed_time = datetime.strptime(normalized, fmt).time()
            break
        except ValueError:
            continue
    if parsed_time is None:
        return None
    try:
        tz = ZoneInfo(feed_timezone)
    except Exception:
        tz = timezone.utc
    local = datetime.combine(parsed_date, parsed_time, tzinfo=tz)
    return local.astimezone(timezone.utc)


def parse_forex_factory_calendar(xml_text: str, *, feed_timezone: str = "UTC") -> list[CalendarEvent]:
    root = ET.fromstring(xml_text)
    events: list[CalendarEvent] = []
    for node in root.iter():
        if _local_name(node.tag) != "event":
            continue
        title = _child_text(node, ("title",))
        country = _child_text(node, ("country", "currency"))
        impact = _child_text(node, ("impact",))
        date_text = _child_text(node, ("date",))
        time_text = _child_text(node, ("time",))
        if not title:
            continue
        events.append(
            CalendarEvent(
                title=title,
                country=country,
                impact=impact,
                when_utc=_parse_calendar_when(date_text, time_text, feed_timezone),
                time_label=time_text or "—",
                forecast=_child_text(node, ("forecast",)),
                previous=_child_text(node, ("previous",)),
                link=_child_text(node, ("url", "link")),
            )
        )
    return events


async def _fetch_text(url: str, *, timeout_seconds: int = 10) -> str:
    timeout = aiohttp.ClientTimeout(total=max(3, int(timeout_seconds)))
    headers = {
        "Accept": "application/xml,text/xml,application/rss+xml,application/atom+xml,text/plain,*/*",
        "User-Agent": "NEXUS/0.6.5 market-brief",
    }
    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        async with session.get(url) as response:
            response.raise_for_status()
            return await response.text(errors="replace")


async def fetch_news(feeds: tuple[tuple[str, str], ...] = DEFAULT_NEWS_FEEDS) -> list[NewsItem]:
    collected: list[NewsItem] = []
    for source, url in feeds:
        try:
            xml_text = await _fetch_text(url)
            collected.extend(parse_rss(xml_text, source))
        except Exception as exc:
            log.warning("market news feed failed: source=%s url=%s error=%s", source, url, exc)
    dedup: dict[str, NewsItem] = {}
    for item in collected:
        dedup.setdefault(item.key, item)
    return sorted(
        dedup.values(),
        key=lambda x: (x.published_at or datetime.min.replace(tzinfo=timezone.utc), x.score),
        reverse=True,
    )


async def fetch_calendar(url: str = DEFAULT_CALENDAR_URL, *, feed_timezone: str = "UTC") -> list[CalendarEvent]:
    xml_text = await _fetch_text(url)
    return parse_forex_factory_calendar(xml_text, feed_timezone=feed_timezone)


def important_recent_news(
    items: list[NewsItem],
    *,
    now_utc: datetime | None = None,
    minimum_score: int = 5,
    max_age_minutes: int = 180,
) -> list[NewsItem]:
    now = now_utc or datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=max(1, int(max_age_minutes)))
    out = []
    for item in items:
        if item.score < max(1, int(minimum_score)):
            continue
        if item.published_at and item.published_at < cutoff:
            continue
        out.append(item)
    return sorted(out, key=lambda x: (x.score, x.published_at or now), reverse=True)


def today_high_impact_events(events: list[CalendarEvent], *, now_utc: datetime, local_timezone: str) -> list[CalendarEvent]:
    tz = ZoneInfo(local_timezone)
    target_date = now_utc.astimezone(tz).date()
    out: list[CalendarEvent] = []
    for event in events:
        if event.impact.strip().lower() != "high":
            continue
        if event.when_utc is not None and event.when_utc.astimezone(tz).date() != target_date:
            continue
        out.append(event)
    return sorted(out, key=lambda e: e.when_utc or datetime.max.replace(tzinfo=timezone.utc))


def _event_time_text(event: CalendarEvent, tz: ZoneInfo) -> str:
    if event.when_utc is None:
        return event.time_label or "—"
    return event.when_utc.astimezone(tz).strftime("%H:%M")


def render_morning_brief(
    *,
    lang: str,
    now_utc: datetime,
    local_timezone: str,
    events: list[CalendarEvent],
    news: list[NewsItem],
) -> str:
    tz = ZoneInfo(local_timezone)
    local_now = now_utc.astimezone(tz)
    high = today_high_impact_events(events, now_utc=now_utc, local_timezone=local_timezone)[:8]
    headlines = important_recent_news(news, now_utc=now_utc, minimum_score=4, max_age_minutes=12 * 60)[:5]

    if lang == "fa":
        lines = [
            "<b>☀️ NEXUS Morning Brief</b>",
            f"📅 {local_now.strftime('%Y/%m/%d')}",
            "",
            "<b>🔴 رویدادهای مهم امروز</b>",
        ]
        if high:
            for event in high:
                extra = ""
                if event.forecast or event.previous:
                    extra = f" | F: {html.escape(event.forecast or '—')} | P: {html.escape(event.previous or '—')}"
                lines.append(
                    f"• {_event_time_text(event, tz)} | <b>{html.escape(event.country or '—')}</b> | {html.escape(event.title)}{extra}"
                )
        else:
            lines.append("• رویداد High Impact ثبت‌شده‌ای برای امروز پیدا نشد.")
        lines += ["", "<b>📰 مهم‌ترین تیترهای بازار</b>"]
        if headlines:
            for item in headlines:
                title = html.escape(item.title)
                source = html.escape(item.source)
                if item.link.startswith(("https://", "http://")):
                    lines.append(f"• <a href=\"{html.escape(item.link, quote=True)}\">{title}</a> — {source}")
                else:
                    lines.append(f"• {title} — {source}")
        else:
            lines.append("• در حال حاضر تیتر مهم تازه‌ای از منابع فعال دریافت نشده است.")
        lines += ["", "⚠️ قبل از رویدادهای High Impact، نوسان و اسلیپیج می‌تواند افزایش پیدا کند."]
        return "\n".join(lines)

    lines = [
        "<b>☀️ NEXUS Morning Brief</b>",
        f"📅 {local_now.strftime('%Y-%m-%d')}",
        "",
        "<b>🔴 Today's high-impact events</b>",
    ]
    if high:
        for event in high:
            extra = ""
            if event.forecast or event.previous:
                extra = f" | F: {html.escape(event.forecast or '—')} | P: {html.escape(event.previous or '—')}"
            lines.append(f"• {_event_time_text(event, tz)} | <b>{html.escape(event.country or '—')}</b> | {html.escape(event.title)}{extra}")
    else:
        lines.append("• No registered high-impact event was found for today.")
    lines += ["", "<b>📰 Top market headlines</b>"]
    if headlines:
        for item in headlines:
            title = html.escape(item.title)
            source = html.escape(item.source)
            if item.link.startswith(("https://", "http://")):
                lines.append(f"• <a href=\"{html.escape(item.link, quote=True)}\">{title}</a> — {source}")
            else:
                lines.append(f"• {title} — {source}")
    else:
        lines.append("• No fresh high-priority headline is available from active sources.")
    lines += ["", "⚠️ Volatility and slippage can rise around high-impact releases."]
    return "\n".join(lines)


def render_news_alert(item: NewsItem, *, lang: str, local_timezone: str) -> str:
    tz = ZoneInfo(local_timezone)
    time_text = "—"
    if item.published_at:
        time_text = item.published_at.astimezone(tz).strftime("%H:%M")
    link = html.escape(item.link, quote=True)
    title = html.escape(item.title)
    source = html.escape(item.source)
    title_line = f"<a href=\"{link}\">{title}</a>" if item.link.startswith(("https://", "http://")) else title
    if lang == "fa":
        return (
            "<b>🚨 NEXUS Market News</b>\n\n"
            f"{title_line}\n\n"
            f"منبع: <b>{source}</b> | زمان: <b>{time_text}</b>"
        )
    return (
        "<b>🚨 NEXUS Market News</b>\n\n"
        f"{title_line}\n\n"
        f"Source: <b>{source}</b> | Time: <b>{time_text}</b>"
    )


def render_event_alert(event: CalendarEvent, *, lang: str, local_timezone: str, minutes_left: int) -> str:
    tz = ZoneInfo(local_timezone)
    when = _event_time_text(event, tz)
    country = html.escape(event.country or "—")
    title = html.escape(event.title)
    forecast = html.escape(event.forecast or "—")
    previous = html.escape(event.previous or "—")
    if lang == "fa":
        return (
            "<b>⏰ هشدار خبر اقتصادی NEXUS</b>\n\n"
            f"🔴 <b>{country} — {title}</b>\n"
            f"زمان: <b>{when}</b> | حدود <b>{max(0, minutes_left)} دقیقه</b> دیگر\n"
            f"Forecast: <b>{forecast}</b> | Previous: <b>{previous}</b>\n\n"
            "⚠️ احتمال افزایش نوسان، اسپرد و اسلیپیج وجود دارد."
        )
    return (
        "<b>⏰ NEXUS Economic News Alert</b>\n\n"
        f"🔴 <b>{country} — {title}</b>\n"
        f"Time: <b>{when}</b> | about <b>{max(0, minutes_left)} min</b> remaining\n"
        f"Forecast: <b>{forecast}</b> | Previous: <b>{previous}</b>\n\n"
        "⚠️ Volatility, spreads and slippage may increase."
    )


def _bool_setting(main, key: str, default: bool) -> bool:
    raw = main.db.get_setting(key, "true" if default else "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _int_setting(main, key: str, default: int, minimum: int, maximum: int) -> int:
    raw = main.db.get_setting(key, str(default)).strip()
    try:
        value = int(raw)
    except Exception:
        value = default
    return max(minimum, min(maximum, value))


def _parse_hm(value: str, fallback: tuple[int, int] = (8, 0)) -> tuple[int, int]:
    try:
        hh, mm = value.strip().split(":", 1)
        hour, minute = int(hh), int(mm)
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour, minute
    except Exception:
        pass
    return fallback


def _feed_config(main) -> tuple[tuple[str, str], ...]:
    raw = main.db.get_setting("market_news_rss_urls", "").strip()
    if not raw:
        return DEFAULT_NEWS_FEEDS
    feeds: list[tuple[str, str]] = []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            for entry in parsed:
                if isinstance(entry, dict):
                    title = _clean_text(entry.get("name") or entry.get("source") or "News")
                    url = _clean_text(entry.get("url"))
                    if url.startswith(("https://", "http://")):
                        feeds.append((title or urlparse(url).netloc, url))
    except Exception:
        feeds = []
    return tuple(feeds) or DEFAULT_NEWS_FEEDS


def _load_keys(main, key: str) -> list[str]:
    raw = main.db.get_setting(key, "[]")
    try:
        values = json.loads(raw)
        if isinstance(values, list):
            return [str(x) for x in values][-300:]
    except Exception:
        pass
    return []


def _save_keys(main, key: str, values: list[str]) -> None:
    main.db.set_setting(key, json.dumps(values[-300:]))


def _audience_ids(main, key: str, default: str = "all") -> list[int]:
    audience = main.db.get_setting(key, default).strip().lower() or default
    if audience not in {"all", "vip", "nonvip", "expired", "highpoints"}:
        audience = default
    try:
        return [int(x) for x in main.db.broadcast_targets(audience)]
    except Exception:
        log.exception("market brief audience resolution failed: %s", audience)
        return []


async def _send_editorial_message(main, bot, user_id: int, text: str, *, ttl_seconds: int, reason: str) -> bool:
    try:
        msg = await bot.send_message(
            int(user_id),
            text,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        task = asyncio.create_task(main._delete_transient_notification(bot, int(user_id), int(msg.message_id), int(ttl_seconds)))
        main.BACKGROUND_TASKS.add(task)
        task.add_done_callback(main.BACKGROUND_TASKS.discard)
        try:
            await main.push_home_to_bottom(bot, int(user_id))
        except Exception as exc:
            log.warning("market editorial dashboard refresh failed for %s: %s", user_id, exc)
        return True
    except Exception as exc:
        log.warning("market editorial delivery failed: user=%s reason=%s error=%s", user_id, reason, exc)
        return False


async def _broadcast_brief(main, bot, events: list[CalendarEvent], news: list[NewsItem], now_utc: datetime) -> tuple[int, int]:
    sent = failed = 0
    ttl = _int_setting(main, "morning_brief_ttl_seconds", DEFAULT_BRIEF_TTL_SECONDS, 300, 86400)
    for uid in _audience_ids(main, "morning_brief_audience", "all"):
        text = render_morning_brief(
            lang=main.get_lang(uid),
            now_utc=now_utc,
            local_timezone=main.settings.timezone,
            events=events,
            news=news,
        )
        if await _send_editorial_message(main, bot, uid, text, ttl_seconds=ttl, reason="morning_brief"):
            sent += 1
        else:
            failed += 1
        await asyncio.sleep(0.05)
    return sent, failed


async def _broadcast_news_item(main, bot, item: NewsItem) -> tuple[int, int]:
    sent = failed = 0
    ttl = _int_setting(main, "market_news_ttl_seconds", DEFAULT_NEWS_TTL_SECONDS, 300, 86400)
    for uid in _audience_ids(main, "market_news_audience", "all"):
        text = render_news_alert(item, lang=main.get_lang(uid), local_timezone=main.settings.timezone)
        if await _send_editorial_message(main, bot, uid, text, ttl_seconds=ttl, reason="market_news"):
            sent += 1
        else:
            failed += 1
        await asyncio.sleep(0.05)
    return sent, failed


async def _broadcast_event_alert(main, bot, event: CalendarEvent, minutes_left: int) -> tuple[int, int]:
    sent = failed = 0
    ttl = _int_setting(main, "economic_alert_ttl_seconds", 2 * 60 * 60, 300, 43200)
    for uid in _audience_ids(main, "market_news_audience", "all"):
        text = render_event_alert(event, lang=main.get_lang(uid), local_timezone=main.settings.timezone, minutes_left=minutes_left)
        if await _send_editorial_message(main, bot, uid, text, ttl_seconds=ttl, reason="economic_alert"):
            sent += 1
        else:
            failed += 1
        await asyncio.sleep(0.05)
    return sent, failed


async def market_information_worker(bot, main) -> None:
    """Automatic Morning Brief + important market/news alerts without adding user menus.

    Defaults:
      * Morning Brief: 08:00 in the configured NEXUS timezone, all bot users.
      * High-impact economic alert: about 30 minutes before the event.
      * Important headline scan: every 10 minutes with persistent de-duplication.
      * First news scan seeds the seen-set to avoid flooding users with old headlines.
    All controls are stored in app_settings so the current Telegram menu structure is unchanged.
    """
    tz = ZoneInfo(main.settings.timezone)
    cached_events: list[CalendarEvent] = []
    cached_news: list[NewsItem] = []
    last_news_fetch: datetime | None = None
    last_calendar_fetch: datetime | None = None

    while True:
        try:
            now_utc = datetime.now(timezone.utc)
            local_now = now_utc.astimezone(tz)

            news_poll = _int_setting(main, "market_news_poll_minutes", DEFAULT_NEWS_POLL_MINUTES, 5, 120)
            calendar_poll = _int_setting(main, "economic_calendar_poll_minutes", DEFAULT_CALENDAR_POLL_MINUTES, 10, 180)

            if last_news_fetch is None or (now_utc - last_news_fetch) >= timedelta(minutes=news_poll):
                cached_news = await fetch_news(_feed_config(main))
                last_news_fetch = now_utc

                if _bool_setting(main, "market_news_enabled", True):
                    seen = _load_keys(main, "market_news_seen_keys")
                    seen_set = set(seen)
                    initialized = main.db.get_setting("market_news_initialized", "0").strip() == "1"
                    candidates = important_recent_news(
                        cached_news,
                        now_utc=now_utc,
                        minimum_score=_int_setting(main, "market_news_min_score", 5, 1, 30),
                        max_age_minutes=_int_setting(main, "market_news_max_age_minutes", 180, 15, 1440),
                    )
                    if not initialized:
                        _save_keys(main, "market_news_seen_keys", seen + [x.key for x in cached_news[:100]])
                        main.db.set_setting("market_news_initialized", "1")
                    else:
                        fresh = [item for item in candidates if item.key not in seen_set][:_int_setting(main, "market_news_max_per_poll", 3, 1, 10)]
                        for item in reversed(fresh):
                            sent, failed = await _broadcast_news_item(main, bot, item)
                            log.info("market news broadcast: key=%s sent=%s failed=%s", item.key, sent, failed)
                            seen.append(item.key)
                        _save_keys(main, "market_news_seen_keys", seen)

            if last_calendar_fetch is None or (now_utc - last_calendar_fetch) >= timedelta(minutes=calendar_poll):
                calendar_url = main.db.get_setting("economic_calendar_url", DEFAULT_CALENDAR_URL).strip() or DEFAULT_CALENDAR_URL
                feed_tz = main.db.get_setting("economic_calendar_feed_timezone", "UTC").strip() or "UTC"
                try:
                    cached_events = await fetch_calendar(calendar_url, feed_timezone=feed_tz)
                except Exception as exc:
                    log.warning("economic calendar fetch failed: %s", exc)
                last_calendar_fetch = now_utc

            if _bool_setting(main, "morning_brief_enabled", True):
                hh, mm = _parse_hm(main.db.get_setting("morning_brief_time", DEFAULT_MORNING_TIME))
                scheduled = local_now.replace(hour=hh, minute=mm, second=0, microsecond=0)
                catchup_hours = _int_setting(main, "morning_brief_catchup_hours", 4, 1, 12)
                due = scheduled <= local_now <= scheduled + timedelta(hours=catchup_hours)
                today_key = local_now.date().isoformat()
                if due and main.db.get_setting("morning_brief_last_date", "") != today_key:
                    sent, failed = await _broadcast_brief(main, bot, cached_events, cached_news, now_utc)
                    if sent > 0 or failed == 0:
                        main.db.set_setting("morning_brief_last_date", today_key)
                    log.info("morning brief broadcast: date=%s sent=%s failed=%s", today_key, sent, failed)

            if _bool_setting(main, "economic_alerts_enabled", True):
                lead = _int_setting(main, "economic_alert_lead_minutes", DEFAULT_EVENT_LEAD_MINUTES, 5, 180)
                alerted = _load_keys(main, "economic_alert_seen_keys")
                alerted_set = set(alerted)
                for event in cached_events:
                    if event.impact.strip().lower() != "high" or event.when_utc is None or event.key in alerted_set:
                        continue
                    minutes_left = int((event.when_utc - now_utc).total_seconds() // 60)
                    if 0 <= minutes_left <= lead:
                        sent, failed = await _broadcast_event_alert(main, bot, event, minutes_left)
                        log.info("economic alert broadcast: key=%s sent=%s failed=%s", event.key, sent, failed)
                        alerted.append(event.key)
                        alerted_set.add(event.key)
                _save_keys(main, "economic_alert_seen_keys", alerted)

        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("market information worker loop failure")

        await asyncio.sleep(30)


def install(main) -> None:
    """Attach the market-information worker without changing app.main or Telegram menus."""
    original_report_worker = main.report_worker

    async def report_rate_and_market_worker(bot):
        core_task = asyncio.create_task(original_report_worker(bot))
        market_task = asyncio.create_task(market_information_worker(bot, main))
        try:
            await asyncio.gather(core_task, market_task)
        finally:
            core_task.cancel()
            market_task.cancel()
            await asyncio.gather(core_task, market_task, return_exceptions=True)

    main.report_worker = report_rate_and_market_worker
