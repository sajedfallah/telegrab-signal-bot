from __future__ import annotations

from html import escape

from aiogram import F



def _remove_named_handler(observer, name: str) -> None:
    observer.handlers[:] = [
        handler
        for handler in observer.handlers
        if getattr(handler.callback, "__name__", "") != name
    ]


def _plan_title(plan, plan_code: str | None, lang: str) -> str:
    if plan is not None:
        try:
            keys = set(plan.keys())
        except Exception:
            keys = set()
        for key in (("title_fa", "fa", "code") if lang == "fa" else ("title_en", "en", "code")):
            try:
                value = plan[key] if key in keys else None
            except Exception:
                value = None
            if value:
                return str(value)
    return str(plan_code or "—")


def install(main) -> None:
    """Keep Account as a high-level hub; detailed AutoTrade validity lives in My License."""
    _remove_named_handler(main.router.callback_query, "account")

    async def account(cb, bot):
        if not await main.gated(cb, bot):
            return
        uid = int(cb.from_user.id)
        lang = main.get_lang(uid)
        access = main.license_service.snapshot(uid)
        plan = main.db.get_plan(access.plan_code) if access.plan_code else None
        plan_title = escape(_plan_title(plan, access.plan_code, lang))
        await cb.answer()

        if lang == "fa":
            text = (
                "<b>👤 حساب من</b>\n\n"
                f"🆔 شناسه تلگرام: <code>{uid}</code>\n"
                f"📦 پلن فعلی: <b>{plan_title}</b>\n"
                f"💎 دسترسی VIP: <b>{'فعال' if access.vip else 'غیرفعال'}</b>\n"
                f"🤖 AutoTrade: <b>{'فعال' if access.autotrade else 'غیرفعال'}</b>\n\n"
                "🔑 جزئیات لایسنس AutoTrade شامل کلید، تاریخ شروع/پایان و زمان باقی‌مانده فقط از بخش «مجوز من» نمایش داده می‌شود."
            )
        else:
            text = (
                "<b>👤 My Account</b>\n\n"
                f"🆔 Telegram ID: <code>{uid}</code>\n"
                f"📦 Current plan: <b>{plan_title}</b>\n"
                f"💎 VIP access: <b>{'ACTIVE' if access.vip else 'INACTIVE'}</b>\n"
                f"🤖 AutoTrade: <b>{'ACTIVE' if access.autotrade else 'INACTIVE'}</b>\n\n"
                "🔑 AutoTrade license key, start/expiry and remaining validity are shown only under “My License”."
            )

        await main.screen(
            bot,
            uid,
            cb.message.chat.id,
            text,
            main.account_menu(lang, access.active, access.autotrade),
        )

    main.router.callback_query.register(account, F.data == "account")
