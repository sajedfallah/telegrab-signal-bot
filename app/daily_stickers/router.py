from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from app.config import settings
from .service import send_for_date, target_chat
from .storage import get_store

router = Router(name="daily-stickers-admin")


def _is_admin(message: Message) -> bool:
    return bool(message.from_user and message.from_user.id in settings.admin_ids)


def _args(message: Message) -> list[str]:
    return (message.text or "").split()[1:]


def _parse_day(value: str | None) -> date:
    if not value or value.lower() == "today":
        return datetime.now(ZoneInfo(settings.timezone)).date()
    return date.fromisoformat(value)


@router.message(Command("daily_sticker_import"))
async def daily_sticker_import(message: Message) -> None:
    if not _is_admin(message): return
    args = _args(message); replied = message.reply_to_message
    if not args or not replied or not replied.sticker or not replied.sticker.set_name:
        await message.answer("روی یک استیکر از Pack ریپلای کن و بزن:\n/daily_sticker_import YYYY-MM-DD COUNT")
        return
    try:
        first_day = _parse_day(args[0]); count = int(args[1]) if len(args) > 1 else 31
        if not 1 <= count <= 120: raise ValueError
    except ValueError:
        await message.answer("فرمت صحیح: /daily_sticker_import YYYY-MM-DD 31"); return
    pack = await message.bot.get_sticker_set(replied.sticker.set_name)
    if len(pack.stickers) < count:
        await message.answer(f"❌ پک {len(pack.stickers)} استیکر دارد ولی count={count} است."); return
    imported = get_store().import_pack(first_day, pack.stickers, count)
    await message.answer(f"✅ {imported} استیکر ثبت شد؛ اولین روز: {first_day.isoformat()} | ارسال روزانه ساعت 08:00")


@router.message(Command("daily_sticker_set"))
async def daily_sticker_set(message: Message) -> None:
    if not _is_admin(message): return
    args = _args(message); replied = message.reply_to_message
    if not args or not replied or not replied.sticker:
        await message.answer("روی استیکر Reply کن: /daily_sticker_set YYYY-MM-DD"); return
    day = _parse_day(args[0]); st = replied.sticker
    get_store().set_sticker(day, st.file_id, file_unique_id=st.file_unique_id, set_name=st.set_name, emoji=st.emoji)
    await message.answer(f"✅ استیکر {day.isoformat()} ذخیره شد.")


@router.message(Command("daily_sticker_status"))
async def daily_sticker_status(message: Message) -> None:
    if not _is_admin(message): return
    args = _args(message); day = _parse_day(args[0] if args else None); store = get_store()
    await message.answer(
        f"📅 {day.isoformat()}\nSticker: {'✅' if store.get_sticker(day) else '❌'}\n"
        f"Sent: {'✅' if store.was_delivered(day, target_chat()) else '❌'}\n"
        f"Configured: {store.count_configured()}\nTarget: {target_chat()}\nTime: 08:00"
    )


@router.message(Command("daily_sticker_send"))
async def daily_sticker_send(message: Message) -> None:
    if not _is_admin(message): return
    args = _args(message); day = _parse_day(args[0] if args else None)
    ok, reason, mid = await send_for_date(message.bot, day, force=True)
    await message.answer(f"{'✅' if ok else '❌'} {day.isoformat()} | {reason} | message_id={mid}")
