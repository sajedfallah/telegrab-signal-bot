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


@router.message(Command("daily_sticker_help"))
async def daily_sticker_help(message: Message) -> None:
    if not _is_admin(message):
        return
    await message.answer(
        "🗓 <b>استیکر روزانه نکسوس</b>\n\n"
        "ایمپورت پک: روی یکی از استیکرهای پک ریپلای کنید:\n"
        "<code>/daily_sticker_import 2026-09-01 30</code>\n\n"
        "ثبت تکی: <code>/daily_sticker_set 2026-09-06</code>\n"
        "وضعیت: <code>/daily_sticker_status today</code>\n"
        "ارسال تست: <code>/daily_sticker_send today</code>",
        parse_mode="HTML",
    )


@router.message(Command("daily_sticker_import"))
async def daily_sticker_import(message: Message) -> None:
    if not _is_admin(message):
        return
    args = _args(message)
    replied = message.reply_to_message
    if not args or not replied or not replied.sticker or not replied.sticker.set_name:
        await message.answer("روی یک استیکر از پک ریپلای کنید: /daily_sticker_import YYYY-MM-DD COUNT")
        return
    try:
        first_day = _parse_day(args[0])
        count = int(args[1]) if len(args) > 1 else 31
        if not (1 <= count <= 366):
            raise ValueError
    except ValueError:
        await message.answer("فرمت صحیح: /daily_sticker_import YYYY-MM-DD COUNT")
        return
    pack = await message.bot.get_sticker_set(replied.sticker.set_name)
    if len(pack.stickers) < count:
        await message.answer(f"❌ پک {len(pack.stickers)} استیکر دارد ولی {count} وارد شده.")
        return
    imported = get_store().import_pack(first_day, pack.stickers, count)
    last_day = date.fromordinal(first_day.toordinal() + imported - 1)
    await message.answer(f"✅ {imported} استیکر ثبت شد؛ از {first_day.isoformat()} تا {last_day.isoformat()}")


@router.message(Command("daily_sticker_set"))
async def daily_sticker_set(message: Message) -> None:
    if not _is_admin(message):
        return
    args = _args(message)
    replied = message.reply_to_message
    if not args or not replied or not replied.sticker:
        await message.answer("روی استیکر ریپلای کنید: /daily_sticker_set YYYY-MM-DD")
        return
    try:
        day = _parse_day(args[0])
    except ValueError:
        await message.answer("تاریخ باید YYYY-MM-DD باشد.")
        return
    st = replied.sticker
    get_store().set_sticker(day, st.file_id, file_unique_id=st.file_unique_id, set_name=st.set_name, emoji=st.emoji)
    await message.answer(f"✅ استیکر {day.isoformat()} ذخیره شد.")


@router.message(Command("daily_sticker_status"))
async def daily_sticker_status(message: Message) -> None:
    if not _is_admin(message):
        return
    args = _args(message)
    try:
        day = _parse_day(args[0] if args else None)
    except ValueError:
        await message.answer("تاریخ باید YYYY-MM-DD باشد.")
        return
    store = get_store()
    await message.answer(
        f"📅 {day.isoformat()}\n"
        f"استیکر: {'✅' if store.get_sticker(day) else '❌'}\n"
        f"ارسال‌شده: {'✅' if store.was_delivered(day, target_chat()) else '❌'}\n"
        f"کل ثبت‌شده: {store.count_configured()}"
    )


@router.message(Command("daily_sticker_send"))
async def daily_sticker_send(message: Message) -> None:
    if not _is_admin(message):
        return
    args = _args(message)
    try:
        day = _parse_day(args[0] if args else None)
    except ValueError:
        await message.answer("تاریخ باید YYYY-MM-DD باشد.")
        return
    ok, reason, message_id = await send_for_date(message.bot, day, force=True)
    await message.answer(f"{'✅' if ok else '❌'} {reason}" + (f" | {message_id}" if message_id else ""))
