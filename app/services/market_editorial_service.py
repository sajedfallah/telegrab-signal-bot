from __future__ import annotations

"""Persian editorial enrichment for public NEXUS market/news posts.

Policy:
* Public-channel market editorial is Persian-only.
* Source article URLs are used for enrichment only; the published title is never a clickable article link.
* Related article imagery is best-effort via OpenGraph/Twitter metadata.
* Translation is fail-closed: if a headline cannot be translated to Persian, callers must not publish the English headline.
* Translation uses a provider chain so a rate-limit at one public provider does not leak English content.
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
_MYMEMORY_URL = "https://api.mymemory.translated.net/get"
_GOOGLE_TRANSLATE_URL = "https://translate.googleapis.com/translate_a/single"
_PERSIAN_RE = re.compile(r"[\u0600-\u06FF]")
_WS_RE = re.compile(r"\s+")
_TAG_RE = re.compile(r"<[^>]+>")
_TRANSLATION_CACHE: dict[str, str] = {}
_TRANSLATION_CACHE_MAX = 500


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


def _fit_utf8(value: str, max_bytes: int = 480) -> str:
    """Keep a request safely below providers' byte limits without breaking UTF-8."""
    raw = str(value or "").encode("utf-8")
    if len(raw) <= max_bytes:
        return str(value or "")
    clipped = raw[: max(1, int(max_bytes))]
    while clipped:
        try:
            return clipped.decode("utf-8").rstrip()
        except UnicodeDecodeError:
            clipped = clipped[:-1]
    return ""


def _cache_get(source: str) -> str | None:
    value = _TRANSLATION_CACHE.get(source)
    return value if value and _has_persian(value) else None


def _cache_put(source: str, translated: str) -> None:
    if not source or not translated:
        return
    if len(_TRANSLATION_CACHE) >= _TRANSLATION_CACHE_MAX:
        # Dict insertion order is stable; discard oldest cached translation.
        try:
            _TRANSLATION_CACHE.pop(next(iter(_TRANSLATION_CACHE)))
        except Exception:
            _TRANSLATION_CACHE.clear()
    _TRANSLATION_CACHE[source] = translated


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


async def _translate_mymemory(text: str, *, timeout_seconds: int = 10) -> str:
    """Translate with MyMemory. Its public GET API accepts at most 500 bytes."""
    source = _fit_utf8(_clean(text, limit=1400), 480)
    if not source:
        return ""
    timeout = aiohttp.ClientTimeout(total=max(3, int(timeout_seconds)))
    params = {
        "q": source,
        "langpair": "en|fa",
        "mt": "1",
    }
    headers = {"User-Agent": "NEXUS/0.6.5 market-editorial"}
    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        async with session.get(_MYMEMORY_URL, params=params) as response:
            response.raise_for_status()
            payload = await response.json(content_type=None)
    data = payload.get("responseData") if isinstance(payload, dict) else None
    translated = _clean(data.get("translatedText") if isinstance(data, dict) else "", limit=1400)
    if not translated or not _has_persian(translated):
        raise RuntimeError("MyMemory response did not contain Persian text")
    return translated


async def _translate_google(text: str, *, timeout_seconds: int = 10) -> str:
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
        async with session.get(_GOOGLE_TRANSLATE_URL, params=params) as response:
            response.raise_for_status()
            payload = await response.json(content_type=None)
    parts = payload[0] if isinstance(payload, list) and payload else []
    translated = "".join(
        str(part[0])
        for part in parts
        if isinstance(part, list) and part and part[0]
    )
    translated = _clean(translated, limit=1400)
    if not translated or not _has_persian(translated):
        raise RuntimeError("Google response did not contain Persian text")
    return translated


async def _translate_remote(text: str, *, timeout_seconds: int = 10) -> str:
    """Try independent public providers in order and return the first Persian result."""
    errors: list[str] = []
    for name, provider in (
        ("mymemory", _translate_mymemory),
        ("google", _translate_google),
    ):
        try:
            translated = await provider(text, timeout_seconds=timeout_seconds)
            if translated and _has_persian(translated):
                return translated
            errors.append(f"{name}: non-Persian response")
        except Exception as exc:
            errors.append(f"{name}: {exc}")
            log.info("market translation provider unavailable: provider=%s error=%s", name, exc)
    raise RuntimeError("; ".join(errors) or "no translation provider available")


async def translate_to_persian(text: str, *, attempts: int = 3) -> str | None:
    source = _clean(text, limit=1400)
    if not source:
        return None
    if _has_persian(source):
        return source
    cached = _cache_get(source)
    if cached:
        return cached
    last_error: Exception | None = None
    tries = max(1, int(attempts))
    for attempt in range(tries):
        try:
            translated = await _translate_remote(source)
            if translated and _has_persian(translated):
                _cache_put(source, translated)
                return translated
            last_error = RuntimeError("translation response did not contain Persian text")
        except Exception as exc:
            last_error = exc
        if attempt + 1 < tries:
            await asyncio.sleep(0.75 * (attempt + 1))
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
        # Summary is optional and clipped for the free translation providers.
        source_summary = _fit_utf8(_clean(meta.description, limit=700), 480)
        translated_summary = await translate_to_persian(source_summary, attempts=2)
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
