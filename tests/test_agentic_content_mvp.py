from app.content.agents import BrandGuardianAgent
from app.content.catalog import ICT_SYLLABUS, TEMPLATES
from app.content.models import ContentDraft
from app.content.visuals import render_post_card


def _draft():
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
        hashtags=["#NEXUS", "#ICT"],
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


def test_ict_syllabus_has_nontrivial_rotation():
    assert len(ICT_SYLLABUS) >= 12
    assert len({item.slug for item in ICT_SYLLABUS}) == len(ICT_SYLLABUS)


def test_brand_guardian_accepts_educational_draft():
    ok, errors = BrandGuardianAgent().validate(_draft())
    assert ok, errors


def test_brand_guardian_rejects_guaranteed_profit_claim():
    draft = _draft()
    draft.definition += " سود تضمینی دارد."
    ok, _ = BrandGuardianAgent().validate(draft)
    assert not ok


def test_visual_renderer_returns_png():
    data = render_post_card(_draft())
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(data) > 10_000
