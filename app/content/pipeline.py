from __future__ import annotations

import logging
from pathlib import Path

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import BufferedInputFile

from ..config import settings as core_settings
from . import repository
from .agents import (
    BrandGuardianAgent,
    CreativeDirectorAgent,
    ResearchAgent,
    TopicPlannerAgent,
    WriterAgent,
)
from .ai_client import OpenAICompatibleTextClient
from .editorial import ChannelEditorAgent
from .image_client import GeminiImageClient
from .settings import content_settings
from .taxonomy import public_post_link
from .visuals import render_post_card

log = logging.getLogger("nexus-content-pipeline")


class ContentPipeline:
    def __init__(self):
        ai = OpenAICompatibleTextClient(
            content_settings.ai_api_key,
            content_settings.text_model,
            content_settings.ai_base_url,
            content_settings.ai_provider,
        )
        self.image_ai = GeminiImageClient(
            content_settings.ai_api_key,
            content_settings.image_model,
            content_settings.image_ai_enabled,
        )
        self.planner = TopicPlannerAgent()
        self.researcher = ResearchAgent()
        self.writer = WriterAgent(ai)
        self.creative_director = CreativeDirectorAgent()
        self.guardian = BrandGuardianAgent()
        self.editor = ChannelEditorAgent()
        self.assets_dir = Path(__file__).resolve().parents[2] / "assets" / "content_generated"
        self.assets_dir.mkdir(parents=True, exist_ok=True)

    async def run_day(self, bot: Bot, scheduled_date: str) -> bool:
        if not repository.claim_day(scheduled_date):
            return False

        draft = None
        try:
            topic = self.planner.choose(scheduled_date)
            grounded = self.researcher.research(topic)
            draft = await self.writer.write(scheduled_date, grounded)
            visual_brief = self.creative_director.direct(draft)

            ok, errors = self.guardian.validate(draft)
            if not ok:
                raise RuntimeError("brand/quality gate rejected draft: " + "; ".join(errors))

            repository.registry_upsert(
                post_id=draft.post_id,
                scheduled_date=draft.scheduled_date,
                category_key=draft.category_key,
                template_key=draft.template_key,
                topic_slug=draft.topic_slug,
                title=draft.title,
                priority=draft.priority,
                hashtags=draft.hashtags,
                source_urls=draft.source_urls,
                status="proposed",
            )

            decision = self.editor.evaluate(
                scheduled_date=draft.scheduled_date,
                category_key=draft.category_key,
                priority=draft.priority,
            )
            if not decision.allowed:
                repository.mark_skipped(scheduled_date, decision.reason)
                repository.registry_mark_skipped(draft.post_id, decision.reason)
                log.info("content skipped by editor post_id=%s reason=%s", draft.post_id, decision.reason)
                return False

            draft.related_links = repository.related_published(
                draft.category_key,
                draft.post_id,
                limit=2,
            )

            hero_image = await self.image_ai.generate(visual_brief.prompt)
            image_bytes = render_post_card(draft, hero_image_bytes=hero_image)
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
            repository.registry_upsert(
                post_id=draft.post_id,
                scheduled_date=draft.scheduled_date,
                category_key=draft.category_key,
                template_key=draft.template_key,
                topic_slug=draft.topic_slug,
                title=draft.title,
                priority=draft.priority,
                hashtags=draft.hashtags,
                source_urls=draft.source_urls,
                status="ready",
            )

            if content_settings.approval_mode:
                preview_message_id: int | None = None
                for admin_id in core_settings.admin_ids:
                    photo = BufferedInputFile(image_bytes, filename=image_path.name)
                    message = await bot.send_photo(
                        admin_id,
                        photo=photo,
                        caption=caption,
                        parse_mode=ParseMode.HTML,
                        protect_content=False,
                    )
                    if preview_message_id is None:
                        preview_message_id = int(message.message_id)
                repository.mark_previewed(scheduled_date, preview_message_id)
                repository.registry_mark_previewed(draft.post_id, preview_message_id)
                return True

            photo = BufferedInputFile(image_bytes, filename=image_path.name)
            message = await bot.send_photo(
                core_settings.public_channel_id,
                photo=photo,
                caption=caption,
                parse_mode=ParseMode.HTML,
                protect_content=content_settings.protect_content,
            )
            message_id = int(message.message_id)
            permalink = public_post_link(core_settings.public_channel_url, message_id)

            # A Telegram post link is only known after publication. Add it in a
            # second step so every published NEXUS post is directly traceable.
            final_caption = draft.caption(permalink=permalink)
            if final_caption != caption:
                try:
                    await bot.edit_message_caption(
                        chat_id=core_settings.public_channel_id,
                        message_id=message_id,
                        caption=final_caption,
                        parse_mode=ParseMode.HTML,
                    )
                except Exception as exc:
                    log.warning("could not append public permalink to %s: %s", draft.post_id, exc)

            repository.mark_published(scheduled_date, message_id)
            repository.registry_mark_published(draft.post_id, message_id, permalink)
            return True
        except Exception as exc:
            repository.mark_failed(scheduled_date, str(exc))
            if draft is not None and draft.post_id:
                repository.registry_mark_failed(draft.post_id, str(exc))
            log.exception("daily content pipeline failed for %s", scheduled_date)
            return False
