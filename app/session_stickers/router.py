from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.config import settings


router = Router(name="nexus-session-stickers")

STORE_PATH = Path(
    os.getenv(
        "SESSION_STICKER_STORE_PATH",
        "data/session_stickers.json",
    )
)

VALID_KEYS = {
    "asia_open": "ASIA OPEN",
    "asia_close": "ASIA CLOSE",
    "london_open": "LONDON OPEN",
    "london_close": "LONDON CLOSE",
    "newyork_open": "NEW YORK OPEN",
    "newyork_close": "NEW YORK CLOSE",
}


def _is_admin(message: Message) -> bool:
    user = message.from_user
    if not user:
        return False
    return int(user.id) in settings.admin_ids


def _args(message: Message) -> list[str]:
    text = (message.text or "").strip()
    parts = text.split()
    return parts[1:] if len(parts) > 1 else []


def _load_store() -> dict[str, dict]:
    if not STORE_PATH.exists():
        return {}

    try:
        raw = json.loads(STORE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}

    if not isinstance(raw, dict):
        return {}

    result: dict[str, dict] = {}

    for key, value in raw.items():
        if key not in VALID_KEYS:
            continue
        if not isinstance(value, dict):
            continue

        file_id = str(value.get("file_id") or "").strip()
        if not file_id:
            continue

        result[key] = {
            "file_id": file_id,
            "file_unique_id": str(value.get("file_unique_id") or ""),
            "set_name": str(value.get("set_name") or ""),
        }

    return result


def _save_store(data: dict[str, dict]) -> None:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)

    payload = json.dumps(
        data,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )

    fd, temp_name = tempfile.mkstemp(
        prefix="session_stickers_",
        suffix=".tmp",
        dir=str(STORE_PATH.parent),
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)

        os.replace(temp_name, STORE_PATH)
    finally:
        try:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
        except Exception:
            pass


def _parse_key(message: Message) -> str | None:
    args = _args(message)
    if not args:
        return None

    key = args[0].strip().lower()

    if key not in VALID_KEYS:
        return None

    return key


def _target_chat() -> int | str | None:
    raw = (
        os.getenv("SESSION_STICKER_CHAT_ID", "").strip()
        or os.getenv("PUBLIC_CONTENT_CHAT_ID", "").strip()
    )

    if not raw:
        return None

    try:
        return int(raw)
    except ValueError:
        return raw


def _target_thread() -> int | None:
    raw = (
        os.getenv("SESSION_STICKER_TOPIC_ID", "").strip()
        or os.getenv("PUBLIC_CONTENT_TOPIC_ID", "").strip()
    )

    if not raw:
        return None

    try:
        value = int(raw)
        return value if value > 0 else None
    except ValueError:
        return None


@router.message(Command("session_sticker_help"))
async def session_sticker_help(message: Message) -> None:
    if not _is_admin(message):
        return

    await message.answer(
        "NEXUS Session Stickers\n\n"
        "Reply روی استیکر و سپس:\n\n"
        "/session_sticker_set asia_open\n"
        "/session_sticker_set asia_close\n"
        "/session_sticker_set london_open\n"
        "/session_sticker_set london_close\n"
        "/session_sticker_set newyork_open\n"
        "/session_sticker_set newyork_close\n\n"
        "وضعیت:\n"
        "/session_sticker_status\n\n"
        "ارسال دستی:\n"
        "/session_sticker_send asia_open\n\n"
        "حذف:\n"
        "/session_sticker_delete asia_open"
    )


@router.message(Command("session_sticker_set"))
async def session_sticker_set(message: Message) -> None:
    if not _is_admin(message):
        return

    key = _parse_key(message)

    if not key:
        await message.answer(
            "کلید معتبر نیست.\n\n"
            "asia_open / asia_close\n"
            "london_open / london_close\n"
            "newyork_open / newyork_close"
        )
        return

    replied = message.reply_to_message

    if not replied or not replied.sticker:
        await message.answer(
            "روی استیکر موردنظر Reply کنید و سپس دستور ثبت را بفرستید."
        )
        return

    sticker = replied.sticker

    data = _load_store()

    data[key] = {
        "file_id": sticker.file_id,
        "file_unique_id": sticker.file_unique_id,
        "set_name": sticker.set_name or "",
    }

    _save_store(data)

    await message.answer(
        f"✅ استیکر {VALID_KEYS[key]} با موفقیت ثبت شد.\n"
        f"کلید: {key}"
    )


@router.message(Command("session_sticker_status"))
async def session_sticker_status(message: Message) -> None:
    if not _is_admin(message):
        return

    data = _load_store()

    lines = [
        "📋 وضعیت Session Stickers",
        "",
    ]

    for key, title in VALID_KEYS.items():
        configured = key in data
        mark = "✅" if configured else "❌"
        lines.append(f"{mark} {title} — {key}")

    await message.answer("\n".join(lines))


@router.message(Command("session_sticker_send"))
async def session_sticker_send(message: Message) -> None:
    if not _is_admin(message):
        return

    key = _parse_key(message)

    if not key:
        await message.answer(
            "مثال:\n/session_sticker_send asia_open"
        )
        return

    data = _load_store()
    row = data.get(key)

    if not row:
        await message.answer(
            f"❌ برای {VALID_KEYS[key]} هنوز استیکری ثبت نشده است."
        )
        return

    target = _target_chat()

    if target is None:
        await message.answer(
            "❌ SESSION_STICKER_CHAT_ID یا PUBLIC_CONTENT_CHAT_ID تنظیم نشده است."
        )
        return

    kwargs = {
        "chat_id": target,
        "sticker": row["file_id"],
    }

    thread_id = _target_thread()

    if thread_id:
        kwargs["message_thread_id"] = thread_id

    sent = await message.bot.send_sticker(**kwargs)

    await message.answer(
        f"✅ استیکر {VALID_KEYS[key]} ارسال شد.\n"
        f"Message ID: {sent.message_id}"
    )


@router.message(Command("session_sticker_delete"))
async def session_sticker_delete(message: Message) -> None:
    if not _is_admin(message):
        return

    key = _parse_key(message)

    if not key:
        await message.answer(
            "مثال:\n/session_sticker_delete asia_open"
        )
        return

    data = _load_store()

    if key not in data:
        await message.answer(
            f"ℹ️ برای {VALID_KEYS[key]} استیکری ثبت نشده است."
        )
        return

    del data[key]
    _save_store(data)

    await message.answer(
        f"✅ استیکر {VALID_KEYS[key]} حذف شد."
    )