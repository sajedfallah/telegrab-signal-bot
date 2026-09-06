from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from pathlib import Path

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto

from app.config import settings as core_settings
from app.content.agents import BrandGuardianAgent, CreativeDirectorAgent, ResearchAgent, WriterAgent
from app.content.ai_client import OpenAICompatibleTextClient
from app.content.image_client import GeminiImageClient
from app.content.models import ContentDraft, Topic
from app.content.routing import resolve_channel_destination
from app.content.settings import content_settings
from app.content.taxonomy import build_hashtags, make_post_id, tracking_hashtag
from app.content.visuals import render_post_card

from . import repository
from .curriculum import LessonSpec, lesson_for_index
from .settings import academy_settings


class AcademyMentorAgent:
    def __init__(self) -> None:
        ai = OpenAICompatibleTextClient(
            content_settings.ai_api_key,
            content_settings.text_model,
            content_settings.ai_base_url,
            content_settings.ai_provider,
        )
        self.researcher = ResearchAgent()
        self.writer = WriterAgent(ai)
        self.guardian = BrandGuardianAgent()
        self.director = CreativeDirectorAgent()
        self.image_ai = GeminiImageClient(
            content_settings.ai_api_key,
            content_settings.image_model,
            content_settings.image_ai_enabled,
        )
        self.assets_dir = Path(__file__).resolve().parents[2] / "assets" / "academy_generated"
        self.assets_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _topic(spec: LessonSpec) -> Topic:
        return Topic(
            slug=spec.topic_slug,
            template_key="ict_education",
            title_fa=spec.title_fa,
            definition_fa=spec.objective_fa,
            key_points_fa=(
                "تعریف را ساده و دقیق یاد بگیر.",
                "محل شکل‌گیری مفهوم را روی نمودار پیدا کن.",
                "فقط با تأیید ساختاری از مفهوم استفاده کن.",
                "تمرین امروز را روی یک نمودار واقعی انجام بده.",
            ),
            example_fa=spec.exercise_prompt_fa,
            level="foundation",
        )

    @staticmethod
    def _seo(spec: LessonSpec) -> dict[str, object]:
        return {
            "primary_keyword": spec.primary_keyword,
            "secondary_keywords": [spec.title_fa, "آموزش ICT", "آموزش معامله‌گری"],
            "meta_description": f"آموزش کوتاه و کاربردی {spec.primary_keyword} همراه با نکات کلیدی و تمرین عملی در NEXUS Academy.",
            "slug": f"academy-{spec.topic_slug}",
        }

    @staticmethod
    def _exercise(spec: LessonSpec) -> tuple[str, list[str], int]:
        return (
            spec.exercise_prompt_fa,
            ["انجام شد و مفهوم روشن است", "نیاز به تمرین بیشتر دارم", "هنوز برایم مبهم است"],
            0,
        )

    @staticmethod
    def _caption(draft: ContentDraft, spec: LessonSpec) -> str:
        points = "\n".join(f"• {x}" for x in draft.key_points[:4])
        return (
            f"<b>📘 NEXUS Academy | درس {spec.lesson_number}</b>\n\n"
            f"<b>{draft.title}</b>\n\n"
            f"{draft.definition}\n\n"
            f"<b>🔑 نکات کلیدی</b>\n{points}\n\n"
            f"<b>🧩 تمرین امروز</b>\n{spec.exercise_prompt_fa}\n\n"
            "<b>✅ جمع‌بندی</b>\nمفهوم را روی نمودار پیدا کن؛ دیدن و تکرار، بخش اصلی یادگیری است.\n\n"
            "💬 وضعیت تمرینت را از دکمه‌های زیر ثبت کن."
        )[:1000]

    async def build_for_day(self, day: date) -> int:
        day_key = day.isoformat()
        existing = repository.get_by_day(day_key)
        if existing and str(existing["status"]) in {"ready", "previewed", "published"}:
            return int(existing["id"])

        spec = lesson_for_index(repository.next_sequence_index())
        topic = self.researcher.research(self._topic(spec))
        draft = await self.writer.write(day_key, topic)
        draft.category_key = "ict_education"
        draft.post_id = make_post_id("ict_education", day_key, spec.topic_slug)
        draft.hashtags = build_hashtags("ict_education", spec.topic_slug, " ".join([draft.title, draft.definition, *draft.key_points]))
        draft.hashtags.append(tracking_hashtag(draft.post_id))
        draft.cta = "تمرین امروز را انجام بده و نتیجه را ثبت کن."

        ok, errors = self.guardian.validate(draft)
        if not ok:
            raise RuntimeError("academy quality gate rejected lesson: " + "; ".join(errors))

        seo = self._seo(spec)
        exercise_prompt, exercise_options, correct_option = self._exercise(spec)
        visual = self.director.direct(draft)
        hero = await self.image_ai.generate(visual.prompt)

        slides: list[bytes] = [render_post_card(draft, hero_image_bytes=hero)]
        key_draft = replace(draft)
        key_draft.title = "نکات کلیدی | " + draft.title
        key_draft.definition = "این چهار نکته را قبل از رفتن به مرحله بعد مرور کن."
        key_draft.example = ""
        slides.append(render_post_card(key_draft, hero_image_bytes=None))

        exercise_draft = replace(draft)
        exercise_draft.title = "تمرین امروز | " + draft.title
        exercise_draft.definition = exercise_prompt
        exercise_draft.key_points = ["یک نمودار واقعی باز کن.", "مفهوم امروز را روی نمودار علامت بزن.", "دلیل انتخابت را در یک جمله بنویس."]
        exercise_draft.example = ""
        slides.append(render_post_card(exercise_draft, hero_image_bytes=None))

        image_paths: list[str] = []
        for idx, data in enumerate(slides[: academy_settings.image_count], start=1):
            path = self.assets_dir / f"{day_key}_{spec.topic_slug}_{idx}.png"
            path.write_bytes(data)
            image_paths.append(str(path))

        return repository.save_ready(
            scheduled_date=day_key,
            course_key=spec.course_key,
            module_key=spec.module_key,
            lesson_number=spec.lesson_number,
            topic_slug=spec.topic_slug,
            title=draft.title,
            primary_keyword=str(seo["primary_keyword"]),
            secondary_keywords=list(seo["secondary_keywords"]),
            meta_description=str(seo["meta_description"]),
            slug=str(seo["slug"]),
            caption=self._caption(draft, spec),
            image_paths=image_paths,
            exercise_prompt=exercise_prompt,
            exercise_options=exercise_options,
            correct_option=correct_option,
        )

    async def preview(self, bot: Bot, day: date) -> bool:
        await self.build_for_day(day)
        row = repository.get_by_day(day.isoformat())
        if row is None:
            return False
        images = json.loads(row["image_paths_json"] or "[]")
        caption = str(row["caption"] or "")
        for admin_id in core_settings.admin_ids:
            media = []
            for index, path in enumerate(images):
                data = Path(path).read_bytes()
                media.append(InputMediaPhoto(media=BufferedInputFile(data, filename=Path(path).name), caption=caption if index == 0 else None, parse_mode=ParseMode.HTML if index == 0 else None))
            if media:
                await bot.send_media_group(admin_id, media)
            await bot.send_message(admin_id, f"🧭 درس {row['lesson_number']} آماده است.\n/academy_approve {day.isoformat()}\n/academy_cancel {day.isoformat()}")
        repository.mark_previewed(day.isoformat())
        return True

    async def publish(self, bot: Bot, day: date) -> bool:
        await self.build_for_day(day)
        row = repository.get_by_day(day.isoformat())
        if row is None or str(row["status"]) == "cancelled":
            return False
        if str(row["status"]) == "published":
            return True

        destination = resolve_channel_destination(core_settings, "ict_education")
        images = json.loads(row["image_paths_json"] or "[]")
        caption = str(row["caption"] or "")
        media = []
        for index, path in enumerate(images):
            data = Path(path).read_bytes()
            media.append(InputMediaPhoto(media=BufferedInputFile(data, filename=Path(path).name), caption=caption if index == 0 else None, parse_mode=ParseMode.HTML if index == 0 else None))
        if not media:
            raise RuntimeError("academy lesson has no visual assets")

        send_kwargs = {}
        if destination.message_thread_id:
            send_kwargs["message_thread_id"] = destination.message_thread_id
        sent = await bot.send_media_group(destination.chat_id, media, **send_kwargs)
        message_id = int(sent[0].message_id)

        lesson_id = int(row["id"])
        options = json.loads(row["exercise_options_json"] or "[]")
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=str(label), callback_data=f"academy_answer:{lesson_id}:{idx}")]
            for idx, label in enumerate(options[:3])
        ])
        await bot.send_message(destination.chat_id, "✍️ تمرین امروز را انجام دادی؟", reply_markup=keyboard, **send_kwargs)
        repository.mark_published(day.isoformat(), message_id)
        return True
