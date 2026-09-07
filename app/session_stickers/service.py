from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot

from app.config import settings
from .storage import VALID_KEYS, get_store


@dataclass(frozen=True)
class SessionEvent:
    key: str
    label: str
    timezone: str
    local_time: str


def enabled() -> bool:
    return os.getenv("SESSION_STICKERS_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def target_chat() -> int | str:
    raw = os.getenv("SESSION_STICKER_CHANNEL_ID", "").strip()
    if not raw:
        return settings.public_channel_id
    try:
        return int(raw)
    except ValueError:
        return raw


def _time(name: str, default: str) -> str:
    value = os.getenv(name, default).strip()
    parts = value.split(":", 1)
    if len(parts) != 2:
        raise RuntimeError(f"{name} must be HH:MM")
    hh, mm = int(parts[0]), int(parts[1])
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        raise RuntimeError(f"{name} must be HH:MM")
    return f"{hh:02d}:{mm:02d}"


def events() -> tuple[SessionEvent, ...]:
    return (
        SessionEvent("asia_open", "Asia Open", os.getenv("SESSION_ASIA_TIMEZONE", "Asia/Tokyo"), _time("SESSION_ASIA_OPEN", "09:00")),
        SessionEvent("asia_close", "Asia Close", os.getenv("SESSION_ASIA_TIMEZONE", "Asia/Tokyo"), _time("SESSION_ASIA_CLOSE", "18:00")),
        SessionEvent("london_open", "London Open", "Europe/London", _time("SESSION_LONDON_OPEN", "08:00")),
        SessionEvent("london_close", "London Close", "Europe/London", _time("SESSION_LONDON_CLOSE", "17:00")),
        SessionEvent("newyork_open", "New York Open", "America/New_York", _time("SESSION_NEWYORK_OPEN", "08:00")),
        SessionEvent("newyork_close", "New York Close", "America/New_York", _time("SESSION_NEWYORK_CLOSE", "17:00")),
    )


def event_by_key(key: str) -> SessionEvent:
    for event in events():
        if event.key == key:
            return event
    raise ValueError(f"unknown session event: {key}")


def due_now(event: SessionEvent, now_utc: datetime, *, tolerance_minutes: int = 2) -> tuple[bool, str]:
    local = now_utc.astimezone(ZoneInfo(event.timezone))
    hh, mm = map(int, event.local_time.split(":"))
    scheduled = local.replace(hour=hh, minute=mm, second=0, microsecond=0)
    delta = abs((local - scheduled).total_seconds())
    return delta <= max(1, tolerance_minutes) * 60, local.date().isoformat()


async def send_event(bot: Bot, event_key: str, *, force: bool = False, local_date: str | None = None) -> tuple[bool, str, int | None]:
    if event_key not in VALID_KEYS:
        return False, "unknown_event", None
    event = event_by_key(event_key)
    store = get_store()
    target = target_chat()
    if local_date is None:
        local_date = datetime.now(ZoneInfo(event.timezone)).date().isoformat()
    if not force and store.was_delivered(event_key, local_date, target):
        return False, "already_sent", None
    row = store.get_sticker(event_key)
    if row is None:
        return False, "missing_sticker", None
    msg = await bot.send_sticker(
        chat_id=target,
        sticker=str(row["file_id"]),
        disable_notification=os.getenv("SESSION_STICKER_SILENT", "false").strip().lower() in {"1", "true", "yes", "on"},
    )
    store.mark_delivered(event_key, local_date, target, int(msg.message_id))
    return True, "sent", int(msg.message_id)
