from __future__ import annotations

import os
from datetime import date

from aiogram import Bot

from app.config import settings
from .storage import StickerStore, get_store


def enabled() -> bool:
    return os.getenv("DAILY_STICKERS_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def target_chat() -> int | str:
    raw = os.getenv("DAILY_STICKER_CHANNEL_ID", "").strip()
    if not raw:
        return settings.public_channel_id
    try:
        return int(raw)
    except ValueError:
        return raw


def scheduled_time() -> tuple[int, int]:
    raw = os.getenv("DAILY_STICKER_TIME", "07:00").strip()
    try:
        hour_s, minute_s = raw.split(":", 1)
        hour, minute = int(hour_s), int(minute_s)
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError
        return hour, minute
    except (ValueError, TypeError):
        raise RuntimeError("DAILY_STICKER_TIME must be HH:MM, for example 07:00")


def catchup_minutes() -> int:
    try:
        return max(0, int(os.getenv("DAILY_STICKER_CATCHUP_MINUTES", "360")))
    except ValueError as exc:
        raise RuntimeError("DAILY_STICKER_CATCHUP_MINUTES must be an integer") from exc


async def send_for_date(
    bot: Bot,
    day: date,
    *,
    force: bool = False,
    store: StickerStore | None = None,
) -> tuple[bool, str, int | None]:
    store = store or get_store()
    target = target_chat()
    if not force and store.was_delivered(day, target):
        return False, "already_sent", None

    row = store.get_sticker(day)
    if row is None:
        return False, "missing_sticker", None

    msg = await bot.send_sticker(
        chat_id=target,
        sticker=str(row["file_id"]),
        disable_notification=os.getenv("DAILY_STICKER_SILENT", "false").strip().lower() in {"1", "true", "yes", "on"},
    )
    store.mark_delivered(day, target, int(msg.message_id))
    return True, "sent", int(msg.message_id)
