from __future__ import annotations

"""Telegram admin controls for the NEXUS AutoTrade capital-protection firewall."""

from aiogram import F
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .autotrade.risk_firewall import (
    DEFAULT_DAILY_LOSS_LIMIT_R,
    global_kill_switch,
    set_global_kill_switch,
)

_INSTALLED = False


def install(main_module) -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    original_system_menu = main_module.admin_system_group

    def _system_menu_with_risk(lang: str) -> InlineKeyboardMarkup:
        base = original_system_menu(lang)
        rows = [list(row) for row in base.inline_keyboard]
        label = "🛡 حفاظت سرمایه AutoTrade" if lang == "fa" else "🛡 AutoTrade Capital Protection"
        rows.insert(0, [InlineKeyboardButton(text=label, callback_data="admin_risk_center")])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    main_module.admin_system_group = _system_menu_with_risk

    def _risk_markup(lang: str) -> InlineKeyboardMarkup:
        stopped = global_kill_switch()
        if lang == "fa":
            action = (
                InlineKeyboardButton(text="✅ بازگشایی معاملات جدید", callback_data="admin_risk_global_off")
                if stopped
                else InlineKeyboardButton(text="🚨 توقف معاملات جدید", callback_data="admin_risk_global_on")
            )
            back = InlineKeyboardButton(text="⬅️ بازگشت", callback_data="admin_group_system")
        else:
            action = (
                InlineKeyboardButton(text="✅ Resume New Trades", callback_data="admin_risk_global_off")
                if stopped
                else InlineKeyboardButton(text="🚨 Stop New Trades", callback_data="admin_risk_global_on")
            )
            back = InlineKeyboardButton(text="⬅️ Back", callback_data="admin_group_system")
        return InlineKeyboardMarkup(inline_keyboard=[[action], [back]])

    async def _show(cb, bot) -> None:
        if not main_module.is_admin(cb.from_user.id):
            await cb.answer()
            return
        lang = main_module.get_lang(cb.from_user.id)
        stopped = global_kill_switch()
        if lang == "fa":
            text = (
                "<b>🛡 مرکز حفاظت سرمایه NEXUS</b>\n\n"
                f"وضعیت معاملات جدید: <b>{'متوقف 🔴' if stopped else 'فعال 🟢'}</b>\n"
                f"حد پیش‌فرض ضرر روزانه: <b>{DEFAULT_DAILY_LOSS_LIMIT_R:g}R</b>\n"
                "Dynamic Risk: <b>فعال</b>\n"
                "Loss-Streak Guard: <b>فعال</b>\n\n"
                "Kill Switch فقط ارسال <b>معاملات جدید</b> را متوقف می‌کند؛ "
                "مدیریت معاملات باز و فرمان‌های SL/TP/Close ادامه دارد."
            )
        else:
            text = (
                "<b>🛡 NEXUS Capital Protection Center</b>\n\n"
                f"New trades: <b>{'STOPPED 🔴' if stopped else 'ACTIVE 🟢'}</b>\n"
                f"Default daily loss limit: <b>{DEFAULT_DAILY_LOSS_LIMIT_R:g}R</b>\n"
                "Dynamic Risk: <b>ON</b>\n"
                "Loss-Streak Guard: <b>ON</b>\n\n"
                "The kill switch blocks <b>new trades only</b>; management of open trades "
                "and SL/TP/Close commands remains available."
            )
        await main_module.screen(bot, cb.from_user.id, cb.message.chat.id, text, _risk_markup(lang))

    @main_module.router.callback_query(F.data == "admin_risk_center")
    async def admin_risk_center(cb, bot):
        await cb.answer()
        await _show(cb, bot)

    @main_module.router.callback_query(F.data == "admin_risk_global_on")
    async def admin_risk_global_on(cb, bot):
        if not main_module.is_admin(cb.from_user.id):
            await cb.answer()
            return
        set_global_kill_switch(True)
        await cb.answer("معاملات جدید متوقف شد" if main_module.get_lang(cb.from_user.id) == "fa" else "New trades stopped", show_alert=True)
        await _show(cb, bot)

    @main_module.router.callback_query(F.data == "admin_risk_global_off")
    async def admin_risk_global_off(cb, bot):
        if not main_module.is_admin(cb.from_user.id):
            await cb.answer()
            return
        set_global_kill_switch(False)
        await cb.answer("معاملات جدید فعال شد" if main_module.get_lang(cb.from_user.id) == "fa" else "New trades resumed", show_alert=True)
        await _show(cb, bot)

    _INSTALLED = True
