from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from app.services import market_editorial_service as editorial


def test_extract_article_meta_finds_description_and_related_image():
    page = """
    <html><head>
      <meta property="og:description" content="Gold rises before US jobs data">
      <meta property="og:image" content="/images/gold.jpg">
    </head></html>
    """
    meta = editorial.extract_article_meta(page, "https://example.com/news/gold")
    assert meta.description == "Gold rises before US jobs data"
    assert meta.image_url == "https://example.com/images/gold.jpg"


def test_translate_to_persian_accepts_existing_persian_without_network(monkeypatch):
    async def should_not_run(*args, **kwargs):
        raise AssertionError("remote translator must not be called")

    monkeypatch.setattr(editorial, "_translate_remote", should_not_run)
    assert asyncio.run(editorial.translate_to_persian("قیمت طلا افزایش یافت")) == "قیمت طلا افزایش یافت"


def test_translate_to_persian_rejects_non_persian_remote_result(monkeypatch):
    editorial._TRANSLATION_CACHE.clear()

    async def bad_remote(*args, **kwargs):
        return "Gold rises"

    monkeypatch.setattr(editorial, "_translate_remote", bad_remote)
    assert asyncio.run(editorial.translate_to_persian("Gold rises", attempts=1)) is None


def test_remote_translation_prefers_mymemory_and_skips_google(monkeypatch):
    calls = []

    async def mymemory(*args, **kwargs):
        calls.append("mymemory")
        return "قیمت طلا افزایش یافت"

    async def google(*args, **kwargs):
        calls.append("google")
        raise AssertionError("Google fallback should not run when MyMemory succeeds")

    monkeypatch.setattr(editorial, "_translate_mymemory", mymemory)
    monkeypatch.setattr(editorial, "_translate_google", google)

    result = asyncio.run(editorial._translate_remote("Gold rises"))
    assert result == "قیمت طلا افزایش یافت"
    assert calls == ["mymemory"]


def test_remote_translation_falls_back_to_google_when_mymemory_fails(monkeypatch):
    calls = []

    async def mymemory(*args, **kwargs):
        calls.append("mymemory")
        raise RuntimeError("provider throttled")

    async def google(*args, **kwargs):
        calls.append("google")
        return "قیمت طلا افزایش یافت"

    monkeypatch.setattr(editorial, "_translate_mymemory", mymemory)
    monkeypatch.setattr(editorial, "_translate_google", google)

    result = asyncio.run(editorial._translate_remote("Gold rises"))
    assert result == "قیمت طلا افزایش یافت"
    assert calls == ["mymemory", "google"]


def test_prepare_payload_never_exposes_source_article_link(monkeypatch):
    async def fake_meta(url, *, timeout_seconds=10):
        return editorial.ArticleMeta(
            description="Gold rises before US jobs data",
            image_url="https://cdn.example.com/gold.jpg",
        )

    translations = {
        "Gold rebounds above $4,450 as Waller tempers Fed rate hike bets ahead US jobs data":
            "طلا بالای ۴۴۵۰ دلار بازگشت؛ والر انتظارات افزایش نرخ بهره فدرال رزرو را تعدیل کرد",
        "Gold rises before US jobs data":
            "طلا پیش از انتشار داده‌های اشتغال آمریکا تقویت شد",
    }

    async def fake_translate(text, *, attempts=3):
        return translations.get(text)

    monkeypatch.setattr(editorial, "fetch_article_meta", fake_meta)
    monkeypatch.setattr(editorial, "translate_to_persian", fake_translate)

    item = SimpleNamespace(
        title="Gold rebounds above $4,450 as Waller tempers Fed rate hike bets ahead US jobs data",
        link="https://www.fxstreet.com/news/example",
        source="FXStreet",
        published_at=datetime(2026, 9, 4, 3, 6, tzinfo=timezone.utc),
    )
    payload = asyncio.run(editorial.prepare_persian_news_payload(item, local_timezone="UTC"))
    assert payload is not None
    assert "طلا" in payload.text
    assert "FXStreet" in payload.text
    assert "https://www.fxstreet.com/news/example" not in payload.text
    assert "Gold rebounds" not in payload.text
    assert payload.image_url == "https://cdn.example.com/gold.jpg"
