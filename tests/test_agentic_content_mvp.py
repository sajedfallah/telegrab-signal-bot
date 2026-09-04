from app.content.agents import BrandGuardianAgent, CreativeDirectorAgent
from app.content.catalog import ICT_SYLLABUS, TEMPLATES
from app.content.models import ContentDraft
from app.content.taxonomy import (
    CATEGORIES,
    build_hashtags,
    make_post_id,
    public_post_link,
    tracking_hashtag,
)
from app.content.visuals import render_post_card


def _draft():
    post_id = make_post_id("ict_education", "2026-09-04", "fvg")
    return ContentDraft(
        scheduled_date="2026-09-04",
        template_key="ict_education",
        topic_slug="fvg",
        title="Fair Value Gap (FVG)",
        kicker="درس امروز",
        definition="FVG ناحیه‌ای آموزشی از عدم‌تعادل قیمت است که باید در متن ساختار بازار بررسی شود.",
        key_points=[
            "ساختار تایم‌فریم بالاتر را ببین.",
            "ناحیه به‌تنهایی ورود نیست.",
            "تأیید ساختاری لازم است.",
            "مدیریت ریسک مقدم است.",
        ],
        example="پس از Displacement، بازگشت به ناحیه فقط برای بررسی بیشتر استفاده می‌شود.",
        cta="این محتوا آموزشی است و توصیه مالی نیست.",
        category_key="ict_education",
        post_id=post_id,
        hashtags=["#NEXUS", "#آموزش", "#ICT", tracking_hashtag(post_id)],
    )


def test_approved_template_family_is_present():
    assert set(TEMPLATES) == {
        "ict_education",
        "chart_breakdown",
        "quick_tip",
        "market_news",
        "tools",
        "risk",
        "trade_review",
        "mindset",
    }


def test_taxonomy_covers_public_channel_families():
    assert {
        "ict_education",
        "daily_analysis",
        "quick_tip",
        "market_news",
        "important_news",
        "news_alert",
        "tools",
        "risk",
        "trade_review",
        "mindset",
    }.issubset(CATEGORIES)
    assert CATEGORIES["market_news"].requires_source
    assert CATEGORIES["important_news"].urgent


def test_ict_syllabus_has_nontrivial_rotation():
    assert len(ICT_SYLLABUS) >= 12
    assert len({item.slug for item in ICT_SYLLABUS}) == len(ICT_SYLLABUS)


def test_tracking_id_hashtag_and_category_tags():
    post_id = make_post_id("ict_education", "2026-09-04", "fvg")
    assert post_id == "NX-EDU-20260904-FVG"
    tags = build_hashtags("ict_education", "fvg", "BTC FVG")
    assert "#آموزش" in tags
    assert "#FVG" in tags
    assert "#BTC" in tags
    assert tracking_hashtag(post_id) == "#NX_EDU_20260904_FVG"


def test_public_post_link_only_accepts_public_telegram_slug():
    assert public_post_link("https://t.me/nexustrade", 123) == "https://t.me/nexustrade/123"
    assert public_post_link("https://t.me/+privateInvite", 123) is None


def test_brand_guardian_accepts_educational_draft():
    ok, errors = BrandGuardianAgent().validate(_draft())
    assert ok, errors


def test_brand_guardian_rejects_guaranteed_profit_claim():
    draft = _draft()
    draft.definition += " سود تضمینی دارد."
    ok, _ = BrandGuardianAgent().validate(draft)
    assert not ok


def test_brand_guardian_requires_source_for_news():
    draft = _draft()
    draft.category_key = "important_news"
    ok, errors = BrandGuardianAgent().validate(draft)
    assert not ok
    assert any("source URL required" in item for item in errors)


def test_creative_director_adds_topic_specific_prompt():
    draft = _draft()
    brief = CreativeDirectorAgent().direct(draft)
    assert "fair-value-gap" in brief.prompt
    assert draft.metadata["visual_prompt"] == brief.prompt


def test_caption_contains_category_tracking_and_clickable_post_link():
    draft = _draft()
    caption = draft.caption(permalink="https://t.me/nexustrade/123")
    assert "#آموزش" in caption
    assert "NX-EDU-20260904-FVG" in caption
    assert "https://t.me/nexustrade/123" in caption
    assert len(caption) <= 1010


def test_visual_renderer_returns_png():
    data = render_post_card(_draft())
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(data) > 10_000
