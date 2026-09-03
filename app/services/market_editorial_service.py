from __future__ import annotations

"""Persian editorial enrichment for public NEXUS market/news posts.

Policy:
* Public-channel market editorial is Persian-only.
* Source article URLs are used for enrichment only; the published title is never a clickable article link.
* Related article imagery is best-effort via OpenGraph/Twitter metadata.
* Translation is fail-closed: if a headline cannot be translated to Persian, callers must not publish the English headline.
"""

import asyncio
import html
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import aiohttp


log = logging.getLogger(__name__)
_TRANSLATE_URL = "https://translate.googleapis.com/translate_a/single"
_PERSIAN_RE = re.compile(r"[\u0600-\u06FF]")
_WS_RE = re.compile(r"\s+")
_TAG_RE = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class ArticleMeta:
    description: str = ""
    image_url: str = ""


@dataclass(frozen=True)
class PersianNewsPayload:
    text: str
    image_url: str = ""


class _MetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() != "meta":
            return
        values = {str(k).lower(): str(v or "") for k, v in attrs}
        key = (values.get("property") or values.get("name") or "").strip().lower()
        value = values.get("content", "").strip()
        if key and value and key not in self.meta:
            self.meta[key] = value


def _clean(value: str | None, *, limit: int = 1200) -> str:
    text = html.unescape(str(value or ""))
    text = _TAG_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text).strip()
    if len(text) > limit:
        text = text[: max(1, limit - 1)].rstrip() + "…"
    return text


def _has_persian(value: str) -> bool:
    return bool(_PERSIAN_RE.search(value or ""))


def extract_article_meta(page_html: str, article_url: str) -> ArticleMeta:
    parser = _MetaParser()
    try:
        parser.feed(page_html or "")
    except Exception:
        pass
    description = _clean(
        parser.meta.get("og:description")
        or parser.meta.get("twitter:description")
        or parser.meta.get("description")
        or "",
        limit=800,
    )
    raw_image = _clean(
        parser.meta.get("og:image")
        or parser.meta.get("og:image:url")
        or parser.meta.get("twitter:image")
        or "",
        limit=1000,
    )
    image_url = urljoin(article_url, raw_image) if raw_image else ""
    if image_url and not image_url.startswith(("https://", "http://")):
        image_url = ""
    return ArticleMeta(description=description, image_url=image_url)


async def fetch_article_meta(url: str, *, timeout_seconds: int = 10) -> ArticleMeta:
    if not str(url or "").startswith(("https://", "http://")):
        return ArticleMeta()
    timeout = aiohttp.ClientTimeout(total=max(3, int(timeout_seconds)))
    headers = {
        "Accept": "text/html,application/xhtml+xml",
        "User-Agent": "Mozilla/5.0 (compatible; NEXUS/0.6.5; +market-editorial)",
    }
    try:
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(url, allow_redirects=True) as response:
                response.raise_for_status()
                body = await response.content.read(1_500_000)
                charset = response.charset or "utf-8"
                page = body.decode(charset, errors="replace")
                return extract_article_meta(page, str(response.url))
    except Exception as exc:
        log.info("market article enrichment unavailable: url=%s error=%s", url, exc)
        return ArticleMeta()


async def _translate_remote(text: str, *, timeout_seconds: int = 10) -> str:
    timeout = aiohttp.ClientTimeout(total=max(3, int(timeout_seconds)))
    params = {
        "client": "gtx",
        "sl": "auto",
        "tl": "fa",
        "dt": "t",
        "q": text,
    }
    headers = {"User-Agent": "NEXUS/0.6.5 market-editorial"}
    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        async with session.get(_TRANSLATE_URL, params=params) as response:
            response.raise_for_status()
            payload = await response.json(content_type=None)
    parts = payload[0] if isinstance(payload, list) and payload else []
    translated = "".join(
        str(part[0])
        for part in parts
        if isinstance(part, list) and part and part[0]
    )
    return _clean(translated, limit=1400)


async def translate_to_persian(text: str, *, attempts: int = 3) -> str | None:
    source = _clean(text, limit=1400)
    if not source:
        return None
    if _has_persian(source):
        return source
    last_error: Exception | None = None
    for attempt in range(max(1, int(attempts))):
        try:
            translated = await _translate_remote(source)
            if translated and _has_persian(translated):
                return translated
            last_error = RuntimeError("translation response did not contain Persian text")
        except Exception as exc:
            last_error = exc
        if attempt + 1 < max(1, int(attempts)):
            await asyncio.sleep(0.35 * (attempt + 1))
    log.warning("market Persian translation failed after %s attempts: %s", attempts, last_error)
    return None


def _time_text(item: Any, local_timezone: str) -> str:
    published = getattr(item, "published_at", None)
    if not isinstance(published, datetime):
        return "—"
    try:
        return published.astimezone(ZoneInfo(local_timezone)).strftime("%H:%M")
    except Exception:
        return "—"


async def prepare_persian_news_payload(item: Any, *, local_timezone: str) -> PersianNewsPayload | None:
    """Build a Persian-only, non-linked editorial post and discover a related image."""
    article_url = str(getattr(item, "link", "") or "")
    meta_task = asyncio.create_task(fetch_article_meta(article_url))
    title_task = asyncio.create_task(translate_to_persian(str(getattr(item, "title", "") or "")))
    meta, fa_title = await asyncio.gather(meta_task, title_task)

    # Fail closed: never leak an English headline to the public NEXUS channel.
    if not fa_title or not _has_persian(fa_title):
        return None

    fa_summary = ""
    if meta.description:
        translated_summary = await translate_to_persian(meta.description)
        if translated_summary and _has_persian(translated_summary):
            fa_summary = translated_summary

    title = html.escape(_clean(fa_title, limit=260))
    summary = html.escape(_clean(fa_summary, limit=520)) if fa_summary else ""
    source = html.escape(_clean(str(getattr(item, "source", "خبرگزاری") or "خبرگزاری"), limit=90))
    when = html.escape(_time_text(item, local_timezone))

    lines = [
        "<b>🚨 خبر مهم بازار | NEXUS</b>",
        "",
        f"<b>{title}</b>",
    ]
    if summary:
        lines += ["", f"📝 {summary}"]
    lines += [
        "",
        f"📰 منبع: <b>{source}</b>",
        f"🕒 زمان: <b>{when}</b>",
    ]
    text = "\n".join(lines)
    return PersianNewsPayload(text=text, image_url=meta.image_url)


async def translate_event_title(title: str, *, country: str = "") -> str:
    translated = await translate_to_persian(title)
    if translated and _has_persian(translated):
        return translated
    country_text = _clean(country, limit=20)
    return f"رویداد مهم اقتصادی {country_text}".strip()
