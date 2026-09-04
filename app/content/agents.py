from __future__ import annotations

import hashlib
from dataclasses import replace

from . import repository
from .ai_client import OpenAICompatibleTextClient, extract_json_object
from .catalog import ICT_SYLLABUS, TEMPLATES
from .models import ContentDraft, Topic, VisualBrief
from .taxonomy import (
    build_hashtags,
    category,
    category_for_template,
    make_post_id,
    tracking_hashtag,
)


class TopicPlannerAgent:
    """Pick one non-repetitive ICT education topic for the scheduled day."""

    def choose(self, scheduled_date: str) -> Topic:
        recent = set(repository.recent_topic_slugs(12))
        educational = [item for item in ICT_SYLLABUS if item.template_key == "ict_education"]
        candidates = [item for item in educational if item.slug not in recent] or educational
        seed = int(hashlib.sha256(scheduled_date.encode("utf-8")).hexdigest()[:8], 16)
        return candidates[seed % len(candidates)]


class ResearchAgent:
    """Ground the MVP in the curated NEXUS ICT knowledge base.

    Live market/news claims are intentionally excluded from this worker. They
    require a separate source-backed pipeline with freshness checks.
    """

    def research(self, topic: Topic) -> Topic:
        return topic


class WriterAgent:
    def __init__(self, ai: OpenAICompatibleTextClient | None = None):
        self.ai = ai

    def _base(self, scheduled_date: str, topic: Topic) -> ContentDraft:
        cat = category_for_template(topic.template_key)
        post_id = make_post_id(cat.key, scheduled_date, topic.slug)
        combined = " ".join((topic.title_fa, topic.definition_fa, *topic.key_points_fa, topic.example_fa))
        hashtags = build_hashtags(cat.key, topic.slug, combined)
        hashtags.append(tracking_hashtag(post_id))
        return ContentDraft(
            scheduled_date=scheduled_date,
            template_key=topic.template_key,
            topic_slug=topic.slug,
            title=topic.title_fa,
            kicker=TEMPLATES.get(topic.template_key, {}).get("kicker", "NEXUS"),
            definition=topic.definition_fa,
            key_points=list(topic.key_points_fa),
            example=topic.example_fa,
            cta="این آموزش برای یادگیری است، نه توصیه مالی. قبل از ورود، Context و مدیریت ریسک را بررسی کن.",
            hashtags=hashtags,
            category_key=cat.key,
            post_id=post_id,
            priority=max(50, cat.min_priority),
        )

    async def write(self, scheduled_date: str, topic: Topic) -> ContentDraft:
        base = self._base(scheduled_date, topic)
        if not self.ai or not self.ai.enabled:
            return base

        prompt = f"""
تو نویسنده آموزشی رسمی NEXUS هستی. محتوای مرجع زیر را فقط برای آموزش معامله‌گری ICT به فارسی روان بازنویسی کن.
قوانین قطعی:
- هیچ سیگنال خرید/فروش، Entry/SL/TP زنده یا وعده سود تولید نکن.
- تعریف فنی را تغییر نده و ادعای قطعی درباره رفتار آینده بازار نکن.
- متن کوتاه، حرفه‌ای و مناسب کانال تلگرام باشد.
- خروجی فقط JSON معتبر با کلیدهای title, definition, key_points, example, cta باشد.
- key_points دقیقاً 4 رشته کوتاه باشد.

موضوع: {topic.title_fa}
تعریف مرجع: {topic.definition_fa}
نکات مرجع: {list(topic.key_points_fa)}
مثال مرجع: {topic.example_fa}
""".strip()

        obj = extract_json_object(await self.ai.complete(prompt))
        if not obj:
            return base

        try:
            points = [str(item).strip() for item in obj.get("key_points", []) if str(item).strip()][:4]
            if len(points) < 3:
                points = base.key_points
            draft = replace(
                base,
                title=str(obj.get("title") or base.title).strip()[:80],
                definition=str(obj.get("definition") or base.definition).strip()[:420],
                key_points=points,
                example=str(obj.get("example") or base.example).strip()[:360],
                cta=str(obj.get("cta") or base.cta).strip()[:220],
            )
            combined = " ".join((draft.title, draft.definition, *draft.key_points, draft.example))
            draft.hashtags = build_hashtags(draft.category_key, draft.topic_slug, combined)
            draft.hashtags.append(tracking_hashtag(draft.post_id))
            return draft
        except Exception:
            return base


class CreativeDirectorAgent:
    """Create a topic-aware visual direction while keeping the NEXUS frame fixed."""

    _MOTIFS = {
        "fvg": "clean three-candle imbalance with a luminous fair-value-gap zone",
        "order_block": "institutional order-block zone before a strong displacement move",
        "liquidity": "equal highs and equal lows with liquidity pools and a sweep",
        "mss": "clear market-structure shift after a liquidity sweep",
        "displacement": "powerful directional displacement candles leaving imbalance",
        "premium_discount": "dealing range split into premium and discount halves",
        "ote": "retracement area with subtle Fibonacci geometry and confluence",
        "breaker": "failed order block turning into a breaker on retest",
        "pdh_pdl": "previous-day high and low as clean intraday liquidity landmarks",
        "session_liquidity": "Asia, London and New York session liquidity ranges",
    }

    def direct(self, draft: ContentDraft) -> VisualBrief:
        cat = category(draft.category_key)
        motif = self._MOTIFS.get(draft.topic_slug, "premium institutional trading market structure")
        prompt = (
            "Create a premium editorial trading visual for NEXUS. "
            "Dark navy and charcoal palette, refined cyan and warm gold accents, cinematic depth, "
            "professional fintech art direction, sophisticated and realistic, no logos, no readable text, "
            "no watermarks, no people, no fake news screenshots. "
            f"The educational concept is: {motif}. "
            f"Content category: {cat.label_fa}. "
            "Leave clean negative space near the top and lower third because the NEXUS compositor will overlay typography. "
            "Vertical 4:5 composition, high contrast, premium Telegram editorial artwork."
        )
        draft.metadata["visual_prompt"] = prompt
        draft.metadata["visual_motif"] = motif
        draft.metadata["category_label"] = cat.label_fa
        return VisualBrief(prompt=prompt, motif=motif)


class BrandGuardianAgent:
    """Hard quality gate for language, sourcing and NEXUS brand consistency."""

    BLOCKED = (
        "سود تضمینی",
        "تضمین سود",
        "بدون ضرر",
        "صددرصد",
        "100% win",
        "حتماً می‌ریزد",
        "حتماً صعود",
        "سیگنال قطعی",
    )

    def validate(self, draft: ContentDraft) -> tuple[bool, list[str]]:
        errors: list[str] = []
        merged = " ".join(
            [draft.title, draft.definition, draft.example, *draft.key_points, draft.cta]
        ).lower()
        for phrase in self.BLOCKED:
            if phrase.lower() in merged:
                errors.append(f"blocked claim: {phrase}")
        if len(draft.title) < 3:
            errors.append("title too short")
        if len(draft.definition) < 40:
            errors.append("definition too short")
        if len(draft.key_points) < 3:
            errors.append("not enough key points")
        if draft.template_key not in TEMPLATES:
            errors.append("unknown visual template")
        if not draft.post_id:
            errors.append("missing tracking post id")
        if not any(tag.startswith("#NX_") for tag in draft.hashtags):
            errors.append("missing tracking hashtag")
        cat = category(draft.category_key)
        if cat.requires_source and not draft.source_urls:
            errors.append(f"source URL required for {cat.key}")
        return not errors, errors
