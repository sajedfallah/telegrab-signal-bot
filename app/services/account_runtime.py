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
    """Keep Account as a compact profile/payments hub without duplicate actions."""
    _remove_named_handler(main.router.callback_query, "account")

    def compact_account_menu(lang: str, has_license: bool, has_autotrade: bool = False):
        # AutoTrade management and Buy/Renew already live on the Home screen.
        # Keep Account focused on profile, VIP status, payments and referrals.
        if lang == "fa":
            rows = [
                [("📊 وضعیت VIP", "client_vip_access")],
                [("💳 پرداخت‌های من", "my_payments"), ("🎁 دعوت دوستان", "referral")],
            ]
            if has_license:
                rows.append([("🔐 لینک دسترسی VIP", "new_vip_link")])
            rows.append([("🌐 تغییر زبان", "change_language")])
        else:
            rows = [
                [("📊 VIP Status", "client_vip_access")],
                [("💳 My Payments", "my_payments"), ("🎁 Invite Friends", "referral")],
            ]
            if has_license:
                rows.append([("🔐 VIP Access Link", "new_vip_link")])
            rows.append([("🌐 Change Language", "change_language")])
        rows += main.nav(lang, "main")
        return main.kb(rows)

    # Existing account handler and any other account rendering now use the same
    # compact menu. Keep the legacy signature for compatibility.
    main.account_menu = compact_account_menu

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
                "مدیریت AutoTrade و خرید/تمدید اشتراک از صفحه اصلی انجام می‌شود."
            )
        else:
            text = (
                "<b>👤 My Account</b>\n\n"
                f"🆔 Telegram ID: <code>{uid}</code>\n"
                f"📦 Current plan: <b>{plan_title}</b>\n"
                f"💎 VIP access: <b>{'ACTIVE' if access.vip else 'INACTIVE'}</b>\n"
                f"🤖 AutoTrade: <b>{'ACTIVE' if access.autotrade else 'INACTIVE'}</b>\n\n"
                "AutoTrade management and subscription purchase/renewal are available from Home."
            )

        await main.screen(
            bot,
            uid,
            cb.message.chat.id,
            text,
            compact_account_menu(lang, access.active, access.autotrade),
        )

    main.router.callback_query.register(account, F.data == "account")
