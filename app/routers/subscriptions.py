from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from .. import db
from ..config import settings
from ..services.license_service import plan_access_label

router = Router(name="subscriptions")


def _lang(uid: int) -> str:
    row = db.get_user(uid)
    return row["language"] if row and row["language"] in {"fa", "en"} else "fa"


def _admin(uid: int) -> bool:
    return uid in settings.admin_ids


def _plan_menu(code: str, lang: str) -> InlineKeyboardMarkup:
    p = db.get_plan(code)
    vip = bool(p["vip_access"])
    auto = bool(p["autotrade_access"])
    renew = float(p["renewal_discount_percent"] or 0)
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=("✅ VIP" if vip else "⛔ VIP"), callback_data=f"planent:vip:{code}"),
         InlineKeyboardButton(text=("✅ Auto Trade" if auto else "⛔ Auto Trade"), callback_data=f"planent:auto:{code}")],
        [InlineKeyboardButton(text=(f"🔁 تخفیف تمدید: {renew:g}٪" if lang == "fa" else f"🔁 Renewal discount: {renew:g}%"), callback_data=f"planrenew:{code}")],
        [InlineKeyboardButton(text="⬅️ پلن" if lang == "fa" else "⬅️ Plan", callback_data=f"planadm:{code}")],
        [InlineKeyboardButton(text="🏠 پنل ادمین" if lang == "fa" else "🏠 Admin", callback_data="admin")],
    ])


async def _render(cb: CallbackQuery, text: str, markup: InlineKeyboardMarkup):
    try:
        await cb.message.edit_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
        db.set_last_menu_message(cb.from_user.id, cb.message.message_id)
    except Exception:
        sent = await cb.message.answer(text, reply_markup=markup, parse_mode=ParseMode.HTML)
        db.set_last_menu_message(cb.from_user.id, sent.message_id)


@router.callback_query(F.data.startswith("planaccess:"))
async def plan_access(cb: CallbackQuery):
    if not _admin(cb.from_user.id): return
    code = cb.data.split(":", 1)[1]
    p = db.get_plan(code)
    if not p:
        await cb.answer("Plan not found", show_alert=True); return
    lang = _lang(cb.from_user.id)
    await cb.answer()
    text = (f"<b>دسترسی‌های پلن {escape(code)}</b>\n\n{escape(plan_access_label(p, lang))}" if lang == "fa"
            else f"<b>Plan {escape(code)} entitlements</b>\n\n{escape(plan_access_label(p, lang))}")
    await _render(cb, text, _plan_menu(code, lang))


@router.callback_query(F.data.startswith("planent:"))
async def plan_entitlement_toggle(cb: CallbackQuery):
    if not _admin(cb.from_user.id): return
    _, entitlement, code = cb.data.split(":", 2)
    p = db.get_plan(code)
    if not p or entitlement not in {"vip", "auto"}: return
    current = bool(p["vip_access"] if entitlement == "vip" else p["autotrade_access"])
    db.update_plan_entitlement(code, entitlement, not current)
    db.add_audit(cb.from_user.id, "plan_entitlement", None, f"{code}:{entitlement}:{int(not current)}")
    await cb.answer("✅")
    fresh = db.get_plan(code); lang = _lang(cb.from_user.id)
    text = (f"<b>دسترسی‌های پلن {escape(code)}</b>\n\n{escape(plan_access_label(fresh, lang))}" if lang == "fa"
            else f"<b>Plan {escape(code)} entitlements</b>\n\n{escape(plan_access_label(fresh, lang))}")
    await _render(cb, text, _plan_menu(code, lang))


@router.callback_query(F.data.startswith("planrenew:"))
async def plan_renewal_menu(cb: CallbackQuery):
    if not _admin(cb.from_user.id): return
    code = cb.data.split(":", 1)[1]; lang = _lang(cb.from_user.id)
    if not db.get_plan(code): return
    await cb.answer()
    rows = []
    values = [0, 5, 10, 15, 20, 25, 30]
    for i in range(0, len(values), 3):
        rows.append([InlineKeyboardButton(text=f"{x}%", callback_data=f"planrenewset:{code}:{x}") for x in values[i:i+3]])
    rows.append([InlineKeyboardButton(text="⬅️" , callback_data=f"planaccess:{code}")])
    text = "درصد تخفیف خودکار برای تمدید زودهنگام را انتخاب کنید." if lang == "fa" else "Choose the automatic early-renewal discount."
    await _render(cb, text, InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("planrenewset:"))
async def plan_renewal_set(cb: CallbackQuery):
    if not _admin(cb.from_user.id): return
    _, code, raw = cb.data.split(":", 2)
    pct = float(raw)
    db.update_plan_renewal_discount(code, pct)
    db.add_audit(cb.from_user.id, "plan_renewal_discount", None, f"{code}:{pct:g}")
    lang = _lang(cb.from_user.id)
    await cb.answer("✅")
    text = (f"تخفیف تمدید پلن <b>{escape(code)}</b>: <b>{pct:g}٪</b>" if lang == "fa"
            else f"Renewal discount for <b>{escape(code)}</b>: <b>{pct:g}%</b>")
    await _render(cb, text, _plan_menu(code, lang))
