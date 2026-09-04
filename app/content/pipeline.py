from __future__ import annotations

import logging
from pathlib import Path

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import BufferedInputFile

from ..config import settings
from . import repository
from .agents import BrandGuardianAgent, ResearchAgent, TopicPlannerAgent, WriterAgent
from .ai_client import OpenAICompatibleTextClient
from .visuals import render_post_card

log = logging.getLogger("nexus-content-pipeline")


class ContentPipeline:
    def __init__(self):
        ai = OpenAICompatibleTextClient(
            settings.content_ai_api_key,
            settings.content_text_model,
            settings.content_ai_base_url,
            settings.content_ai_provider,
        )
        self.planner = TopicPlannerAgent()
        self.researcher = ResearchAgent()
        self.writer = WriterAgent(ai)
        self.guardian = BrandGuardianAgent()
        self.assets_dir = Path(__file__).resolve().parents[2] / "assets" / "content_generated"
        self.assets_dir.mkdir(parents=True, exist_ok=True)

    async def run_day(self, bot: Bot, scheduled_date: str) -> bool:
        if not repository.claim_day(scheduled_date):
            return False
        try:
            topic = self.planner.choose(scheduled_date)
            grounded = self.researcher.research(topic)
            draft = await self.writer.write(scheduled_date, grounded)
            ok, errors = self.guardian.validate(draft)
            if not ok:
                raise RuntimeError("brand/quality gate rejected draft: " + "; ".join(errors))

            image_bytes = render_post_card(draft)
            image_path = self.assets_dir / f"{scheduled_date}_{draft.topic_slug}.png"
            image_path.write_bytes(image_bytes)
            caption = draft.caption()
            repository.save_draft(
                scheduled_date,
                draft.template_key,
                draft.topic_slug,
                draft.title,
                caption,
                str(image_path),
            )

            if settings.content_approval_mode:
                preview_message_id: int | None = None
                for admin_id in settings.admin_ids:
                    photo = BufferedInputFile(image_bytes, filename=image_path.name)
                    message = await bot.send_photo(
                        admin_id,
                        photo=photo,
                        caption="🧪 <b>پیش‌نمایش محتوای روزانه NEXUS</b>\n\n" + caption,
                        parse_mode=ParseMode.HTML,
                        protect_content=False,
                    )
                    if preview_message_id is None:
                        preview_message_id = int(message.message_id)
                repository.mark_previewed(scheduled_date, preview_message_id)
                return True

            photo = BufferedInputFile(image_bytes, filename=image_path.name)
            message = await bot.send_photo(
                settings.public_channel_id,
                photo=photo,
                caption=caption,
                parse_mode=ParseMode.HTML,
                protect_content=settings.content_protect_content,
            )
            repository.mark_published(scheduled_date, int(message.message_id))
            return True
        except Exception as exc:
            repository.mark_failed(scheduled_date, str(exc))
            log.exception("daily content pipeline failed for %s", scheduled_date)
            return False
