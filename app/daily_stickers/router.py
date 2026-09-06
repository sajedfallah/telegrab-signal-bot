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
    text = message.text or ""
    return text.split()[1:]


def _parse_day(value: str | None) -> date:
    if not value or value.lower() == "today":
        return datetime.now(ZoneInfo(settings.timezone)).date()
    return date.fromisoformat(value)


@router.message(Command("daily_sticker_help"))
async def daily_sticker_help(message: Message) -> None:
    if not _is_admin(message):
        return
    await message.answer(
        "🗓 <b>NEXUS Daily Stickers</b>\n\n"
        "ثبت یک استیکر: روی استیکر Reply بزنید و ارسال کنید:\n"
        "<code>/daily_sticker_set 2026-09-06</code>\n\n"
        "ایمپورت خودکار یک پک مرتب‌شده از روز اول:\n"
        "روی یکی از استیکرهای همان Pack ریپلای کنید:\n"
        "<code>/daily_sticker_import 2026-08-23 31</code>\n\n"
        "وضعیت: <code>/daily_sticker_status today</code>\n"
        "ارسال آزمایشی/دستی: <code>/daily_sticker_send today</code>\n"
        "حذف: <code>/daily_sticker_delete 2026-09-06</code>",
        parse_mode="HTML",
    )


@router.message(Command("daily_sticker_set"))
async def daily_sticker_set(message: Message) -> None:
    if not _is_admin(message):
        return
    args = _args(message)
    replied = message.reply_to_message
    if not args or not replied or not replied.sticker:
        await message.answer("روی استیکر Reply کنید و بنویسید: /daily_sticker_set YYYY-MM-DD")
        return
    try:
        day = _parse_day(args[0])
    except ValueError:
        await message.answer("تاریخ باید به فرم YYYY-MM-DD باشد.")
        return
    st = replied.sticker
    get_store().set_sticker(
        day,
        st.file_id,
        file_unique_id=st.file_unique_id,
        set_name=st.set_name,
        emoji=st.emoji,
    )
    await message.answer(f"✅ استیکر {day.isoformat()} ذخیره شد.")


@router.message(Command("daily_sticker_import"))
async def daily_sticker_import(message: Message) -> None:
    if not _is_admin(message):
        return
    args = _args(message)
    replied = message.reply_to_message
    if not args or not replied or not replied.sticker or not replied.sticker.set_name:
        await message.answer(
            "روی یک استیکر از Pack ریپلای کنید و بنویسید:\n"
            "/daily_sticker_import YYYY-MM-DD 31"
        )
        return
    try:
        first_day = _parse_day(args[0])
        count = int(args[1]) if len(args) > 1 else 31
        if not (1 <= count <= 120):
            raise ValueError
    except ValueError:
        await message.answer("فرمت صحیح: /daily_sticker_import YYYY-MM-DD 31")
        return

    pack = await message.bot.get_sticker_set(replied.sticker.set_name)
    if len(pack.stickers) < count:
        await message.answer(f"❌ این Pack فقط {len(pack.stickers)} استیکر دارد ولی count={count} وارد شده.")
        return
    imported = get_store().import_pack(first_day, pack.stickers, count)
    last_day = date.fromordinal(first_day.toordinal() + imported - 1)
    await message.answer(
        f"✅ {imported} استیکر از Pack <code>{pack.name}</code> ثبت شد.\n"
        f"از {first_day.isoformat()} تا {last_day.isoformat()}",
        parse_mode="HTML",
    )


@router.message(Command("daily_sticker_status"))
async def daily_sticker_status(message: Message) -> None:
    if not _is_admin(message):
        return
    args = _args(message)
    try:
        day = _parse_day(args[0] if args else None)
    except ValueError:
        await message.answer("تاریخ باید به فرم YYYY-MM-DD باشد.")
        return
    store = get_store()
    row = store.get_sticker(day)
    sent = store.was_delivered(day, target_chat())
    await message.answer(
        f"📅 {day.isoformat()}\n"
        f"Sticker: {'✅' if row else '❌'}\n"
        f"Sent: {'✅' if sent else '❌'}\n"
        f"Configured total: {store.count_configured()}\n"
        f"Target: <code>{target_chat()}</code>",
        parse_mode="HTML",
    )


@router.message(Command("daily_sticker_send"))
async def daily_sticker_send(message: Message) -> None:
    if not _is_admin(message):
        return
    args = _args(message)
    try:
        day = _parse_day(args[0] if args else None)
    except ValueError:
        await message.answer("تاریخ باید به فرم YYYY-MM-DD باشد.")
        return
    ok, reason, message_id = await send_for_date(message.bot, day, force=True)
    if ok:
        await message.answer(f"✅ استیکر {day.isoformat()} ارسال شد. message_id={message_id}")
    else:
        await message.answer(f"❌ ارسال انجام نشد: {reason}")


@router.message(Command("daily_sticker_delete"))
async def daily_sticker_delete(message: Message) -> None:
    if not _is_admin(message):
        return
    args = _args(message)
    if not args:
        await message.answer("/daily_sticker_delete YYYY-MM-DD")
        return
    try:
        day = _parse_day(args[0])
    except ValueError:
        await message.answer("تاریخ باید به فرم YYYY-MM-DD باشد.")
        return
    deleted = get_store().delete_sticker(day)
    await message.answer("✅ حذف شد." if deleted else "ℹ️ برای این تاریخ استیکری ثبت نشده بود.")
