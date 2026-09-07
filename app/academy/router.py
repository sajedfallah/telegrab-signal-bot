from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.config import settings as core_settings
from . import repository
from .agent import AcademyMentorAgent
from .settings import academy_settings

router = Router(name="academy-mentor")
_agent = AcademyMentorAgent()


def _is_admin(message: Message) -> bool:
    return bool(message.from_user and int(message.from_user.id) in set(core_settings.admin_ids))


def _parse_day(raw: str | None) -> date:
    if not raw or raw.lower() == "today":
        return datetime.now(ZoneInfo(academy_settings.timezone)).date()
    return date.fromisoformat(raw)


def _arg(message: Message) -> str | None:
    parts=(message.text or "").split(maxsplit=1); return parts[1].strip() if len(parts)>1 else None


@router.message(Command("academy_preview"))
async def academy_preview(message: Message) -> None:
    if not _is_admin(message): return
    try:
        day=_parse_day(_arg(message)); ok=await _agent.preview(message.bot,day)
        await message.answer("✅ پیش‌نمایش Academy V2 آماده شد." if ok else "❌ پیش‌نمایش ساخته نشد.")
    except Exception as exc:
        repository.record_failure(_parse_day(None).isoformat(),"manual_preview",str(exc))
        await message.answer(f"❌ خطا در ساخت پیش‌نمایش: {str(exc)[:500]}")


@router.message(Command("academy_rebuild"))
async def academy_rebuild(message: Message) -> None:
    if not _is_admin(message): return
    try:
        day=_parse_day(_arg(message)); repository.reset_for_rebuild(day); ok=await _agent.preview(message.bot,day)
        await message.answer("♻️ درس با قالب V2 دوباره ساخته شد." if ok else "❌ بازسازی انجام نشد.")
    except Exception as exc:
        await message.answer(f"❌ خطای بازسازی: {str(exc)[:500]}")


@router.message(Command("academy_approve"))
async def academy_approve(message: Message) -> None:
    if not _is_admin(message): return
    try:
        day=_parse_day(_arg(message)); ok=await _agent.publish(message.bot,day)
        await message.answer("✅ درس Academy V2 منتشر شد." if ok else "❌ انتشار انجام نشد.")
    except Exception as exc:
        await message.answer(f"❌ خطای انتشار: {str(exc)[:500]}")


@router.message(Command("academy_cancel"))
async def academy_cancel(message: Message) -> None:
    if not _is_admin(message): return
    try:
        day=_parse_day(_arg(message)); repository.mark_cancelled(day.isoformat()); await message.answer(f"⛔ درس {day.isoformat()} لغو شد.")
    except Exception: await message.answer("فرمت تاریخ: YYYY-MM-DD یا today")


@router.message(Command("academy_today"))
async def academy_today(message: Message) -> None:
    if not _is_admin(message): return
    row=repository.get_by_day(_parse_day(None))
    if row is None: await message.answer("ℹ️ برای امروز هنوز درسی ساخته نشده است."); return
    total,correct=repository.stats_for_lesson(int(row["id"])); pct=round((correct/total)*100) if total else 0
    await message.answer(f"📘 درس {row['lesson_number']}\n{row['title']}\nوضعیت: {row['status']}\nپاسخ‌ها: {total} | صحیح: {pct}%")


@router.message(Command("academy_stats"))
async def academy_stats(message: Message) -> None:
    if not _is_admin(message): return
    rows=repository.recent_lessons(10)
    if not rows: await message.answer("هنوز آماری ثبت نشده است."); return
    lines=["📊 آمار ۱۰ درس اخیر"]
    for row in rows:
        total,correct=repository.stats_for_lesson(int(row["id"])); pct=round((correct/total)*100) if total else 0
        lines.append(f"• درس {row['lesson_number']} | {row['status']} | مشارکت {total} | صحیح {pct}%")
    await message.answer("\n".join(lines))


@router.callback_query(F.data.startswith("academy_answer:"))
async def academy_answer(callback: CallbackQuery) -> None:
    try:
        _,lesson_raw,choice_raw=str(callback.data).split(":",2); lesson_id=int(lesson_raw); choice=int(choice_raw)
        row=repository.get_by_id(lesson_id)
        if row is None or callback.from_user is None:
            await callback.answer("این تمرین در دسترس نیست.",show_alert=True); return
        correct=choice==int(row["correct_option"] or 0)
        repository.record_answer(lesson_id,int(callback.from_user.id),choice,correct)
        feedback=("✅ درست است. پاسخ ثبت شد؛ حالا همین الگو را روی یک نمودار واقعی پیدا کن."
                  if correct else
                  "❌ این گزینه دقیق نیست. اسلاید «تشخیص» را دوباره ببین و یک بار دیگر الگو را روی نمودار بررسی کن.")
        await callback.answer("پاسخ ثبت شد ✅" if correct else "پاسخ ثبت شد؛ نیاز به مرور دارد",show_alert=True)
        if callback.message:
            try: await callback.message.edit_reply_markup(reply_markup=None)
            except Exception: pass
            try: await callback.message.reply(feedback)
            except Exception: pass
    except Exception:
        try: await callback.answer("ثبت پاسخ انجام نشد. دوباره امتحان کن.",show_alert=True)
        except Exception: pass
