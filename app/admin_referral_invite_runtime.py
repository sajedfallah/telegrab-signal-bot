from __future__ import annotations

"""Admin-side NEXUS bot invitation shortcut.

Adds a compact "bot invite link" action under the existing Referral & Loyalty
admin group without changing the core referral engine. The generated deep link
uses the current admin's existing referral code, so successful joins continue
to be measurable by the current referral statistics/leaderboard.
"""

from html import escape
from urllib.parse import urlencode

from aiogram import F
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


_INSTALLED = False


def invite_copy(lang: str) -> str:
    if lang == "en":
        return "⚡ NEXUS — analyze smarter, trade with more discipline.\nStart here 👇"
    return "⚡ NEXUS؛ هوشمندتر تحلیل کن، منظم‌تر معامله کن.\nهمین حالا شروع کن 👇"


def build_invite_link(bot_username: str, referral_code: str | None) -> str:
    username = str(bot_username or "").strip().lstrip("@")
    if not username:
        return ""
    code = str(referral_code or "").strip()
    if code:
        return f"https://t.me/{username}?start=ref_{code}"
    return f"https://t.me/{username}"


def build_share_url(link: str, text: str) -> str:
    return "https://t.me/share/url?" + urlencode({"url": link, "text": text})


def install(main_module) -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    original_rewards_menu = main_module.admin_rewards_group

    def _admin_rewards_group_with_invite(lang: str) -> InlineKeyboardMarkup:
        original = original_rewards_menu(lang)
        rows = [list(row) for row in original.inline_keyboard]
        label = "🔗 لینک دعوت به ربات" if lang == "fa" else "🔗 Bot Invite Link"
        rows.insert(0, [InlineKeyboardButton(text=label, callback_data="admin_bot_invite")])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    main_module.admin_rewards_group = _admin_rewards_group_with_invite

    @main_module.router.callback_query(F.data == "admin_bot_invite")
    async def admin_bot_invite(cb, bot):
        if not main_module.is_admin(cb.from_user.id):
            await cb.answer()
            return

        await cb.answer()

        # Keep referral attribution compatible with the existing /start ref_...
        # flow. Admin users are normal DB users too, so use their native code.
        main_module.db.upsert_user(
            cb.from_user.id,
            cb.from_user.username,
            cb.from_user.first_name,
        )
        user = main_module.db.get_user(cb.from_user.id)
        code = user["referral_code"] if user else None

        me = await bot.get_me()
        link = build_invite_link(me.username or "", code)
        lang = main_module.get_lang(cb.from_user.id)
        copy = invite_copy(lang)

        if not link:
            text = main_module.tr(
                lang,
                "⚠️ نام کاربری ربات در Telegram تنظیم نشده و لینک دعوت قابل ساخت نیست.",
                "⚠️ The bot username is not configured in Telegram, so an invite link cannot be generated.",
            )
            markup = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(
                        text="⬅️ بازگشت" if lang == "fa" else "⬅️ Back",
                        callback_data="admin_group_rewards",
                    )]
                ]
            )
            await main_module.screen(bot, cb.from_user.id, cb.message.chat.id, text, markup)
            return

        share_url = build_share_url(link, copy)
        if lang == "fa":
            text = (
                "<b>🔗 دعوت به NEXUS</b>\n\n"
                f"{escape(copy)}\n\n"
                f"<code>{escape(link)}</code>\n\n"
                "ورود از این لینک در آمار رفرال شما ثبت می‌شود."
            )
            share_label = "📤 اشتراک‌گذاری دعوت"
            back_label = "⬅️ بازگشت"
        else:
            text = (
                "<b>🔗 Invite to NEXUS</b>\n\n"
                f"{escape(copy)}\n\n"
                f"<code>{escape(link)}</code>\n\n"
                "Joins through this link are recorded in your referral statistics."
            )
            share_label = "📤 Share Invite"
            back_label = "⬅️ Back"

        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=share_label, url=share_url)],
                [InlineKeyboardButton(text=back_label, callback_data="admin_group_rewards")],
            ]
        )
        await main_module.screen(
            bot,
            cb.from_user.id,
            cb.message.chat.id,
            text,
            markup,
        )

    _INSTALLED = True
