from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from aiogram import Bot

from app.config import settings
from .router import VALID_KEYS, _load_store, _target_chat, _target_thread


log = logging.getLogger("nexus.session_stickers")

DELIVERY_PATH = Path(
    os.getenv(
        "SESSION_STICKER_DELIVERY_PATH",
        "data/session_sticker_deliveries.json",
    )
)

_TRUE = {"1", "true", "yes", "on", "enabled"}

SCHEDULES = (
    ("asia_open", "SESSION_ASIA_TIMEZONE", "Asia/Tokyo", "SESSION_ASIA_OPEN_TIME", "09:00"),
    ("asia_close", "SESSION_ASIA_TIMEZONE", "Asia/Tokyo", "SESSION_ASIA_CLOSE_TIME", "18:00"),
    ("london_open", "SESSION_LONDON_TIMEZONE", "Europe/London", "SESSION_LONDON_OPEN_TIME", "08:00"),
    ("london_close", "SESSION_LONDON_TIMEZONE", "Europe/London", "SESSION_LONDON_CLOSE_TIME", "17:00"),
    ("newyork_open", "SESSION_NEWYORK_TIMEZONE", "America/New_York", "SESSION_NEWYORK_OPEN_TIME", "08:00"),
    ("newyork_close", "SESSION_NEWYORK_TIMEZONE", "America/New_York", "SESSION_NEWYORK_CLOSE_TIME", "17:00"),
)


def enabled() -> bool:
    return (
        os.getenv("SESSION_STICKERS_ENABLED", "false")
        .strip()
        .lower()
        in _TRUE
    )


def weekdays_only() -> bool:
    return (
        os.getenv("SESSION_STICKER_WEEKDAYS_ONLY", "true")
        .strip()
        .lower()
        in _TRUE
    )


def catchup_minutes() -> int:
    try:
        return max(
            0,
            min(
                120,
                int(os.getenv("SESSION_STICKER_CATCHUP_MINUTES", "10")),
            ),
        )
    except ValueError:
        return 10


def parse_time(raw: str) -> tuple[int, int]:
    parts = (raw or "").strip().split(":")

    if len(parts) != 2:
        raise ValueError(f"Invalid HH:MM time: {raw}")

    hour = int(parts[0])
    minute = int(parts[1])

    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"Invalid HH:MM time: {raw}")

    return hour, minute


def _load_deliveries() -> dict[str, dict]:
    if not DELIVERY_PATH.exists():
        return {}

    try:
        data = json.loads(
            DELIVERY_PATH.read_text(encoding="utf-8")
        )
    except Exception:
        return {}

    return data if isinstance(data, dict) else {}


def _save_deliveries(data: dict[str, dict]) -> None:
    DELIVERY_PATH.parent.mkdir(parents=True, exist_ok=True)

    payload = json.dumps(
        data,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )

    fd, temp_name = tempfile.mkstemp(
        prefix="session_delivery_",
        suffix=".tmp",
        dir=str(DELIVERY_PATH.parent),
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)

        os.replace(temp_name, DELIVERY_PATH)

    finally:
        try:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
        except Exception:
            pass


def delivery_key(session_key: str, local_date) -> str:
    return f"{session_key}:{local_date.isoformat()}"


async def send_session_sticker(
    bot: Bot,
    session_key: str,
    local_date,
) -> tuple[bool, str, int | None]:

    if session_key not in VALID_KEYS:
        return False, "invalid_session_key", None

    stickers = _load_store()
    row = stickers.get(session_key)

    if not row:
        return False, "missing_sticker", None

    target = _target_chat()

    if target is None:
        return False, "missing_target", None

    deliveries = _load_deliveries()
    key = delivery_key(session_key, local_date)

    if key in deliveries:
        return False, "already_sent", None

    kwargs = {
        "chat_id": target,
        "sticker": row["file_id"],
    }

    thread_id = _target_thread()

    if thread_id:
        kwargs["message_thread_id"] = thread_id

    message = await bot.send_sticker(**kwargs)

    deliveries[key] = {
        "session": session_key,
        "date": local_date.isoformat(),
        "message_id": int(message.message_id),
        "chat_id": str(target),
        "thread_id": thread_id,
        "sent_at_utc": datetime.now(
            ZoneInfo("UTC")
        ).isoformat(),
    }

    if len(deliveries) > 400:
        ordered = list(deliveries.items())
        deliveries = dict(ordered[-300:])

    _save_deliveries(deliveries)

    return True, "sent", int(message.message_id)


async def _check_one(
    bot: Bot,
    session_key: str,
    timezone_env: str,
    timezone_default: str,
    time_env: str,
    time_default: str,
) -> None:

    timezone_name = (
        os.getenv(timezone_env, timezone_default).strip()
        or timezone_default
    )

    tz = ZoneInfo(timezone_name)

    hour, minute = parse_time(
        os.getenv(time_env, time_default)
    )

    now = datetime.now(tz)

    if weekdays_only() and now.weekday() >= 5:
        return

    scheduled = now.replace(
        hour=hour,
        minute=minute,
        second=0,
        microsecond=0,
    )

    deadline = scheduled + timedelta(
        minutes=catchup_minutes()
    )

    if not (scheduled <= now <= deadline):
        return

    sent, reason, message_id = await send_session_sticker(
        bot,
        session_key,
        now.date(),
    )

    if sent:
        log.info(
            "Session sticker sent key=%s local_date=%s timezone=%s message_id=%s",
            session_key,
            now.date(),
            timezone_name,
            message_id,
        )

    elif reason != "already_sent":
        log.warning(
            "Session sticker not sent key=%s reason=%s",
            session_key,
            reason,
        )


async def main() -> None:
    if not enabled():
        log.info(
            "Session sticker automation disabled "
            "(SESSION_STICKERS_ENABLED=false)"
        )
        return

    for (
        session_key,
        timezone_env,
        timezone_default,
        time_env,
        time_default,
    ) in SCHEDULES:
        timezone_name = (
            os.getenv(timezone_env, timezone_default).strip()
            or timezone_default
        )

        ZoneInfo(timezone_name)
        parse_time(os.getenv(time_env, time_default))

    target = _target_chat()
    thread_id = _target_thread()

    bot = Bot(settings.bot_token)

    log.info(
        "Session sticker automation enabled "
        "target=%s thread=%s catchup=%sm weekdays_only=%s",
        target,
        thread_id,
        catchup_minutes(),
        weekdays_only(),
    )

    try:
        while True:
            for schedule in SCHEDULES:
                try:
                    await _check_one(bot, *schedule)
                except Exception:
                    log.exception(
                        "Session sticker schedule check failed key=%s",
                        schedule[0],
                    )

            await asyncio.sleep(20)

    finally:
        await bot.session.close()