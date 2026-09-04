from __future__ import annotations

from html import escape

from aiogram import F
from aiogram.enums import ParseMode
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup

from .ecosystem import ecosystem_settings
from .portal import build_nexus_folder_qr


def build_nexus_main_menu(lang: str, is_admin: bool = False) -> InlineKeyboardMarkup:
    """Central customer gateway while keeping commercial/account actions in-bot."""
    if lang == "fa":
        rows = [
            [InlineKeyboardButton(text="🚀 ورود به NEXUS", url=ecosystem_settings.folder_url)],
            [
                InlineKeyboardButton(text="📊 مدیریت سیگنال‌ها", callback_data="client_signals"),
                InlineKeyboardButton(text="💎 خرید اشتراک", callback_data="vip"),
            ],
            [
                InlineKeyboardButton(text="👤 حساب من", callback_data="account"),
                InlineKeyboardButton(text="🎓 راهنما", callback_data="guide_hub"),
            ],
            [
                InlineKeyboardButton(text="📱 QR فولدر NEXUS", callback_data="nexus_folder_qr"),
                InlineKeyboardButton(text="🛟 پشتیبانی", callback_data="support"),
            ],
            [InlineKeyboardButton(text="🌐 تغییر زبان", callback_data="change_language")],
        ]
        if is_admin:
            rows[-1].append(InlineKeyboardButton(text="🛠 پنل مدیریت", callback_data="admin"))
    else:
        rows = [
            [InlineKeyboardButton(text="🚀 Enter NEXUS", url=ecosystem_settings.folder_url)],
            [
                InlineKeyboardButton(text="📊 Manage Signals", callback_data="client_signals"),
                InlineKeyboardButton(text="💎 Buy Subscription", callback_data="vip"),
            ],
            [
                InlineKeyboardButton(text="👤 My Account", callback_data="account"),
                InlineKeyboardButton(text="🎓 Guide", callback_data="guide_hub"),
            ],
            [
                InlineKeyboardButton(text="📱 NEXUS Folder QR", callback_data="nexus_folder_qr"),
                InlineKeyboardButton(text="🛟 Support", callback_data="support"),
            ],
            [InlineKeyboardButton(text="🌐 Change Language", callback_data="change_language")],
        ]
        if is_admin:
            rows[-1].append(InlineKeyboardButton(text="🛠 Admin Panel", callback_data="admin"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def install_nexus_hub(core) -> None:
    """Install the redesigned customer UI without modifying the hardened core module.

    `app.main` is intentionally large and battle-tested. The access-center layer
    is attached at runtime so trading, subscription, reporting and AutoTrade
    handlers remain untouched.
    """
    if getattr(core, "_NEXUS_HUB_INSTALLED", False):
        return

    core.main_menu = build_nexus_main_menu

    async def show_access_center(bot, user_id: int, chat_id: int) -> None:
        lang = core.get_lang(user_id)
        text = core.tr(
            lang,
            "<b>⚡ NEXUS | مرکز دسترسی</b>\n\n"
            "تمام کانال‌ها و سرویس‌های NEXUS از یک ورودی واحد در دسترس هستند.\n\n"
            "🚀 <b>ورود به NEXUS</b> فولدر رسمی تلگرام را باز می‌کند؛ کانال عمومی، Academy، Free و VIP در همان فولدر قرار می‌گیرند.\n\n"
            "برای مدیریت اشتراک، سیگنال‌ها، حساب یا راهنما از گزینه‌های پایین استفاده کنید.",
            "<b>⚡ NEXUS | Access Center</b>\n\n"
            "All NEXUS channels and services are available from one gateway.\n\n"
            "🚀 <b>Enter NEXUS</b> opens the official Telegram folder containing Public, Academy, Free and VIP channels.\n\n"
            "Use the options below to manage subscriptions, signals, account and guides.",
        )
        await core.screen(
            bot,
            user_id,
            chat_id,
            text,
            build_nexus_main_menu(lang, core.is_admin(user_id)),
        )

    core.show_main = show_access_center

    async def nexus_folder_qr(cb, bot) -> None:
        if not await core.gated(cb, bot):
            return
        lang = core.get_lang(cb.from_user.id)
        await cb.answer()
        try:
            qr_bytes = build_nexus_folder_qr(ecosystem_settings.folder_url)
        except Exception:
            core.log.exception("could not build NEXUS folder QR")
            await bot.send_message(
                cb.from_user.id,
                core.tr(
                    lang,
                    "⚠️ ساخت QR موقتاً ناموفق بود. از دکمه «ورود به NEXUS» استفاده کنید.",
                    "⚠️ QR generation is temporarily unavailable. Use the ‘Enter NEXUS’ button.",
                ),
            )
            return

        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text=core.tr(lang, "🚀 باز کردن فولدر NEXUS", "🚀 Open NEXUS Folder"),
                url=ecosystem_settings.folder_url,
            )],
            [InlineKeyboardButton(
                text=core.tr(lang, "🏠 بازگشت به مرکز دسترسی", "🏠 Back to Access Center"),
                callback_data="main",
            )],
        ])
        await bot.send_photo(
            cb.from_user.id,
            photo=BufferedInputFile(qr_bytes, filename="NEXUS_Official_Folder_QR.png"),
            caption=core.tr(
                lang,
                "<b>📱 فولدر رسمی NEXUS</b>\n\n"
                "برای ورود مستقیم روی دکمه زیر بزنید؛ یا QR را با دستگاه دیگر اسکن کنید.\n\n"
                f"<code>{escape(ecosystem_settings.folder_url)}</code>",
                "<b>📱 Official NEXUS Folder</b>\n\n"
                "Tap the button below to open it directly, or scan the QR from another device.\n\n"
                f"<code>{escape(ecosystem_settings.folder_url)}</code>",
            ),
            reply_markup=markup,
            parse_mode=ParseMode.HTML,
            protect_content=False,
        )

    core.router.callback_query.register(nexus_folder_qr, F.data == "nexus_folder_qr")
    core._NEXUS_HUB_INSTALLED = True
