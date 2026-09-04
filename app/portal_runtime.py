from __future__ import annotations

from html import escape

from aiogram import F
from aiogram.enums import ParseMode
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup

from .ecosystem import ecosystem_settings
from .portal import build_nexus_folder_qr


def build_nexus_main_menu(
    lang: str,
    is_admin: bool = False,
    has_autotrade: bool = False,
) -> InlineKeyboardMarkup:
    """Central customer gateway with entitlement-aware AutoTrade controls.

    Public/Academy/Free/VIP channel discovery belongs to the official Telegram
    folder. The in-bot trading control is therefore shown only to customers
    whose AutoTrade entitlement is active.
    """
    if lang == "fa":
        rows = [
            [InlineKeyboardButton(text="🚀 ورود به NEXUS", url=ecosystem_settings.folder_url)],
        ]
        if has_autotrade:
            rows.append([
                InlineKeyboardButton(text="🤖 مدیریت AutoTrade", callback_data="client_autotrade_access"),
                InlineKeyboardButton(text="💎 خرید / تمدید اشتراک", callback_data="vip"),
            ])
        else:
            rows.append([
                InlineKeyboardButton(text="💎 خرید اشتراک", callback_data="vip"),
            ])
        rows.extend([
            [
                InlineKeyboardButton(text="👤 حساب من", callback_data="account"),
                InlineKeyboardButton(text="🎓 راهنما", callback_data="guide_hub"),
            ],
            [
                InlineKeyboardButton(text="📱 QR فولدر NEXUS", callback_data="nexus_folder_qr"),
                InlineKeyboardButton(text="🛟 پشتیبانی", callback_data="support"),
            ],
            [InlineKeyboardButton(text="🌐 تغییر زبان", callback_data="change_language")],
        ])
        if is_admin:
            rows[-1].append(InlineKeyboardButton(text="🛠 پنل مدیریت", callback_data="admin"))
    else:
        rows = [
            [InlineKeyboardButton(text="🚀 Enter NEXUS", url=ecosystem_settings.folder_url)],
        ]
        if has_autotrade:
            rows.append([
                InlineKeyboardButton(text="🤖 Manage AutoTrade", callback_data="client_autotrade_access"),
                InlineKeyboardButton(text="💎 Buy / Renew", callback_data="vip"),
            ])
        else:
            rows.append([
                InlineKeyboardButton(text="💎 Buy Subscription", callback_data="vip"),
            ])
        rows.extend([
            [
                InlineKeyboardButton(text="👤 My Account", callback_data="account"),
                InlineKeyboardButton(text="🎓 Guide", callback_data="guide_hub"),
            ],
            [
                InlineKeyboardButton(text="📱 NEXUS Folder QR", callback_data="nexus_folder_qr"),
                InlineKeyboardButton(text="🛟 Support", callback_data="support"),
            ],
            [InlineKeyboardButton(text="🌐 Change Language", callback_data="change_language")],
        ])
        if is_admin:
            rows[-1].append(InlineKeyboardButton(text="🛠 Admin Panel", callback_data="admin"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


class _LegacySignalsRedirectMiddleware:
    """Retire the old Public/VIP signal chooser without breaking stale buttons.

    Old Telegram messages may still contain callback_data=client_signals. Those
    callbacks are intercepted before the hardened legacy handler: AutoTrade
    customers go directly to their control center, everyone else returns to the
    central NEXUS access center.
    """

    def __init__(self, core):
        self.core = core

    async def __call__(self, handler, event, data):
        if getattr(event, "data", None) != "client_signals":
            return await handler(event, data)

        bot = data.get("bot")
        if bot is None:
            return await handler(event, data)

        if not await self.core.gated(event, bot):
            return None

        user_id = int(event.from_user.id)
        lang = self.core.get_lang(user_id)
        if not self.core.license_service.has_autotrade(user_id):
            try:
                await event.answer(
                    self.core.tr(
                        lang,
                        "این بخش فقط برای کاربران دارای AutoTrade فعال است.",
                        "This section is available only to users with active AutoTrade.",
                    ),
                    show_alert=True,
                )
            except Exception:
                pass
            await self.core.show_main(bot, user_id, event.message.chat.id)
            return None

        try:
            await event.answer()
        except Exception:
            pass
        await self.core._show_autotrade_home(bot, user_id, event.message.chat.id)
        return None


def install_nexus_hub(core) -> None:
    """Install the redesigned customer UI without modifying hardened trading logic."""
    if getattr(core, "_NEXUS_HUB_INSTALLED", False):
        return

    # Keep compatibility with hardened call sites that still invoke main_menu
    # with only (lang, is_admin). Entitlement-aware screens call the builder
    # directly with has_autotrade.
    core.main_menu = build_nexus_main_menu

    async def show_access_center(bot, user_id: int, chat_id: int) -> None:
        lang = core.get_lang(user_id)
        access = core.license_service.snapshot(user_id)
        has_autotrade = bool(access.autotrade)
        text = core.tr(
            lang,
            "<b>⚡ NEXUS | مرکز دسترسی</b>\n\n"
            "تمام کانال‌های NEXUS از فولدر رسمی تلگرام در دسترس هستند.\n\n"
            "🚀 <b>ورود به NEXUS</b> فولدر مرکزی شامل Public، Academy، Free و VIP را باز می‌کند.\n\n"
            + (
                "🤖 AutoTrade شما فعال است؛ کنترل معاملات خودکار از همین پنل در دسترس است."
                if has_autotrade
                else "برای خرید، حساب کاربری، راهنما یا پشتیبانی از گزینه‌های پایین استفاده کنید."
            ),
            "<b>⚡ NEXUS | Access Center</b>\n\n"
            "All NEXUS channels are available through the official Telegram folder.\n\n"
            "🚀 <b>Enter NEXUS</b> opens the central folder containing Public, Academy, Free and VIP channels.\n\n"
            + (
                "🤖 Your AutoTrade is active; trading controls are available in this panel."
                if has_autotrade
                else "Use the options below for purchases, account, guides or support."
            ),
        )
        await core.screen(
            bot,
            user_id,
            chat_id,
            text,
            build_nexus_main_menu(lang, core.is_admin(user_id), has_autotrade),
        )

    core.show_main = show_access_center

    # Broadcasts and system notices push a fresh home panel. Preserve the same
    # entitlement-aware layout there as on /start and normal navigation.
    async def push_access_center_to_bottom(bot, user_id: int) -> None:
        user = core.db.get_user(user_id)
        if not user:
            return
        old_id = user["last_menu_message_id"]
        if old_id:
            try:
                await bot.delete_message(user_id, int(old_id))
            except Exception:
                pass
        if core.is_admin(user_id):
            lang = core.get_lang(user_id)
            msg = await bot.send_message(
                user_id,
                core.tr(lang, "<b>🛠 پنل ادمین NEXUS</b>", "<b>🛠 NEXUS Admin Panel</b>"),
                reply_markup=core.admin_menu(lang),
                parse_mode=ParseMode.HTML,
            )
            core.db.set_last_menu_message(user_id, msg.message_id)
            return
        await show_access_center(bot, user_id, user_id)

    core.push_home_to_bottom = push_access_center_to_bottom

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

    # Outer middleware executes before the legacy callback handler, so stale
    # client_signals buttons can no longer expose Public/VIP chooser screens.
    core.router.callback_query.outer_middleware(_LegacySignalsRedirectMiddleware(core))
    core.router.callback_query.register(nexus_folder_qr, F.data == "nexus_folder_qr")
    core._NEXUS_HUB_INSTALLED = True
