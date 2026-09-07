from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto

from app.config import settings as core_settings
from app.content.routing import resolve_channel_destination

from . import repository
from .agent import AcademyMentorAgent

_INSTALLED = False


def _media_caption(row) -> str:
    # Telegram media captions have a much smaller limit than normal messages.
    # Keep the album caption intentionally compact and move the complete lesson
    # text to a dedicated message immediately after the album.
    return (
        f"<b>📘 NEXUS Academy | درس {row['lesson_number']}</b>\n"
        f"<b>{str(row['title'] or '')[:180]}</b>\n\n"
        "آموزش کامل و تمرین در پیام بعدی 👇"
    )


def _media(images: list[str], caption: str) -> list[InputMediaPhoto]:
    out: list[InputMediaPhoto] = []
    for index, path in enumerate(images):
        data = Path(path).read_bytes()
        out.append(
            InputMediaPhoto(
                media=BufferedInputFile(data, filename=Path(path).name),
                caption=caption if index == 0 else None,
                parse_mode=ParseMode.HTML if index == 0 else None,
            )
        )
    return out


async def _preview(self: AcademyMentorAgent, bot: Bot, day: date) -> bool:
    await self.build_for_day(day)
    row = repository.get_by_day(day.isoformat())
    if row is None:
        return False
    images = json.loads(row["image_paths_json"] or "[]")
    media = _media(images, _media_caption(row)) if images else []
    full_text = str(row["caption"] or "")

    for admin_id in core_settings.admin_ids:
        if media:
            await bot.send_media_group(admin_id, media)
        if full_text:
            await bot.send_message(admin_id, full_text[:4090], parse_mode=ParseMode.HTML)
        await bot.send_message(
            admin_id,
            f"🧭 Academy V2 | درس {row['lesson_number']} آماده است.\n"
            f"/academy_approve {day.isoformat()}\n"
            f"/academy_rebuild {day.isoformat()}\n"
            f"/academy_cancel {day.isoformat()}",
        )
    repository.mark_previewed(day.isoformat())
    return True


async def _publish(self: AcademyMentorAgent, bot: Bot, day: date) -> bool:
    await self.build_for_day(day)
    row = repository.get_by_day(day.isoformat())
    if row is None or str(row["status"]) == "cancelled":
        return False
    if str(row["status"]) == "published":
        return True

    destination = resolve_channel_destination(core_settings, "ict_education")
    images = json.loads(row["image_paths_json"] or "[]")
    if not images:
        raise RuntimeError("academy lesson has no visual assets")

    send_kwargs = {}
    if destination.message_thread_id:
        send_kwargs["message_thread_id"] = destination.message_thread_id

    sent = await bot.send_media_group(
        destination.chat_id,
        _media(images, _media_caption(row)),
        **send_kwargs,
    )
    message_id = int(sent[0].message_id)

    full_text = str(row["caption"] or "")
    if full_text:
        await bot.send_message(
            destination.chat_id,
            full_text[:4090],
            parse_mode=ParseMode.HTML,
            **send_kwargs,
        )

    lesson_id = int(row["id"])
    options = json.loads(row["exercise_options_json"] or "[]")
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{chr(65 + idx)} · {label}",
                    callback_data=f"academy_answer:{lesson_id}:{idx}",
                )
            ]
            for idx, label in enumerate(options[:3])
        ]
    )
    await bot.send_message(
        destination.chat_id,
        f"<b>🧠 آزمون کوتاه درس {row['lesson_number']}</b>\n\n"
        f"{row['exercise_prompt']}\n\n"
        "یک گزینه را انتخاب کن؛ نتیجه همان لحظه ثبت می‌شود.",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
        **send_kwargs,
    )
    repository.mark_published(day.isoformat(), message_id)
    return True


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    AcademyMentorAgent.preview = _preview
    AcademyMentorAgent.publish = _publish
    _INSTALLED = True
