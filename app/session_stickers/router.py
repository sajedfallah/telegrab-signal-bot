from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.config import settings
from .service import event_by_key, events, send_event, target_chat
from .storage import VALID_KEYS, get_store

router = Router(name="session-stickers-admin")


def _is_admin(message: Message) -> bool:
    return bool(message.from_user and int(message.from_user.id) in set(settings.admin_ids))


def _arg(message: Message) -> str | None:
    parts = (message.text or "").split(maxsplit=1)
    return parts[1].strip().lower() if len(parts) > 1 else None


@router.message(Command("session_sticker_set"))
async def session_sticker_set(message: Message) -> None:
    if not _is_admin(message):
        return
    key = _arg(message)
    replied = message.reply_to_message
    if not key or key not in VALID_KEYS or not replied or not replied.sticker:
        await message.answer(
            "روی استیکر مربوط Reply کنید و یکی از این دستورها را بفرستید:\n"
            "/session_sticker_set asia_open\n"
            "/session_sticker_set asia_close\n"
            "/session_sticker_set london_open\n"
            "/session_sticker_set london_close\n"
            "/session_sticker_set newyork_open\n"
            "/session_sticker_set newyork_close"
        )
        return
    get_store().set_sticker(key, replied.sticker)
    event = event_by_key(key)
    await message.answer(f"✅ {event.label} ثبت شد | {event.local_time} {event.timezone}")


@router.message(Command("session_sticker_status"))
async def session_sticker_status(message: Message) -> None:
    if not _is_admin(message):
        return
    store = get_store()
    rows = {str(row["event_key"]): row for row in store.all_configured()}
    lines = ["🕒 NEXUS Session Stickers", f"Target: {target_chat()}"]
    for event in events():
        lines.append(f"{'✅' if event.key in rows else '❌'} {event.key} | {event.local_time} {event.timezone}")
    await message.answer("\n".join(lines))


@router.message(Command("session_sticker_send"))
async def session_sticker_send(message: Message) -> None:
    if not _is_admin(message):
        return
    key = _arg(message)
    if not key or key not in VALID_KEYS:
        await message.answer("مثال: /session_sticker_send london_open")
        return
    ok, reason, message_id = await send_event(message.bot, key, force=True)
    if ok:
        await message.answer(f"✅ {key} ارسال شد. message_id={message_id}")
    else:
        await message.answer(f"❌ ارسال انجام نشد: {reason}")


@router.message(Command("session_sticker_help"))
async def session_sticker_help(message: Message) -> None:
    if not _is_admin(message):
        return
    await message.answer(
        "🕒 NEXUS Session Stickers\n\n"
        "ثبت: روی استیکر Reply کنید و /session_sticker_set EVENT را بفرستید.\n"
        "EVENT ها: asia_open, asia_close, london_open, london_close, newyork_open, newyork_close\n\n"
        "وضعیت: /session_sticker_status\n"
        "تست دستی: /session_sticker_send london_open"
    )
