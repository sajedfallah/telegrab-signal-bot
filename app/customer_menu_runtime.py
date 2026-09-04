from __future__ import annotations

"""Final customer-home layout for the NEXUS Telegram bot.

Product decisions implemented here:
- «ورود به نکسوس / Enter NEXUS» is the first home-menu entry.
- The generic Signals menu is removed from the customer home screen.
- Only the entitlement-gated VIP Signal Channel remains as the signal entry.
- AutoTrade status is visible directly below VIP access.
- FAQ is no longer a top-level item; it lives inside Support.

The existing customer_experience module remains authoritative for VIP access,
purchases, FAQ content and AutoTrade delivery. This runtime only refines
navigation and support information architecture.
"""

from typing import Any

from aiogram import Bot, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from . import customer_experience as cx
from .config import settings
from .services import license_service

router = Router(name="nexus-customer-menu-runtime")


def customer_main_menu(lang: str, *, is_admin: bool, has_vip: bool) -> InlineKeyboardMarkup:
    vip_icon = "🔓" if has_vip else "🔒"

    if lang == "fa":
        rows = [
            [InlineKeyboardButton(text="🚪 ورود به نکسوس", url=cx.NEXUS_FOLDER_URL)],
            [InlineKeyboardButton(text=f"{vip_icon} کانال سیگنال VIP", callback_data="vip_channel_access")],
            [InlineKeyboardButton(text="⚙️ وضعیت AutoTrade", callback_data="customer_autotrade_status")],
            [
                InlineKeyboardButton(text="💎 خرید اشتراک", callback_data="vip"),
                InlineKeyboardButton(text="👤 حساب من", callback_data="account"),
            ],
            [
                InlineKeyboardButton(text="🎓 راهنما", callback_data="guide_hub"),
                InlineKeyboardButton(text="🛟 پشتیبانی", callback_data="customer_support"),
            ],
            [InlineKeyboardButton(text="🌐 تغییر زبان", callback_data="change_language")],
        ]
        if is_admin:
            rows.append([InlineKeyboardButton(text="🛠 پنل مدیریت", callback_data="admin")])
    else:
        rows = [
            [InlineKeyboardButton(text="🚪 Enter NEXUS", url=cx.NEXUS_FOLDER_URL)],
            [InlineKeyboardButton(text=f"{vip_icon} VIP Signal Channel", callback_data="vip_channel_access")],
            [InlineKeyboardButton(text="⚙️ AutoTrade Status", callback_data="customer_autotrade_status")],
            [
                InlineKeyboardButton(text="💎 Buy Subscription", callback_data="vip"),
                InlineKeyboardButton(text="👤 My Account", callback_data="account"),
            ],
            [
                InlineKeyboardButton(text="🎓 Guide", callback_data="guide_hub"),
                InlineKeyboardButton(text="🛟 Support", callback_data="customer_support"),
            ],
            [InlineKeyboardButton(text="🌐 Change Language", callback_data="change_language")],
        ]
        if is_admin:
            rows.append([InlineKeyboardButton(text="🛠 Admin Panel", callback_data="admin")])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def support_menu(lang: str) -> InlineKeyboardMarkup:
    if lang == "fa":
        rows = [
            [InlineKeyboardButton(text="🛟 ارتباط با پشتیبانی", url=settings.support_url)],
            [InlineKeyboardButton(text="❓ سوالات متداول", callback_data="faq")],
            [
                InlineKeyboardButton(text="⬅️ بازگشت", callback_data="main"),
                InlineKeyboardButton(text="🏠 منوی اصلی", callback_data="main"),
            ],
        ]
    else:
        rows = [
            [InlineKeyboardButton(text="🛟 Contact Support", url=settings.support_url)],
            [InlineKeyboardButton(text="❓ FAQ", callback_data="faq")],
            [
                InlineKeyboardButton(text="⬅️ Back", callback_data="main"),
                InlineKeyboardButton(text="🏠 Main Menu", callback_data="main"),
            ],
        ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def faq_menu(lang: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    index = 0 if lang == "fa" else 1
    for key, item in cx.FAQS.items():
        rows.append(
            [InlineKeyboardButton(text=f"❔ {item['q'][index]}", callback_data=f"faq:{key}")]
        )
    if lang == "fa":
        rows.append(
            [
                InlineKeyboardButton(text="⬅️ پشتیبانی", callback_data="customer_support"),
                InlineKeyboardButton(text="🏠 منوی اصلی", callback_data="main"),
            ]
        )
    else:
        rows.append(
            [
                InlineKeyboardButton(text="⬅️ Support", callback_data="customer_support"),
                InlineKeyboardButton(text="🏠 Main Menu", callback_data="main"),
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(lambda cb: cb.data == "customer_autotrade_status")
async def customer_autotrade_status(cb: CallbackQuery, bot: Bot) -> None:
    from . import main as core

    if not await core.gated(cb, bot):
        return

    lang = core.get_lang(cb.from_user.id)
    access = license_service.snapshot(cb.from_user.id)
    active = bool(access.autotrade)
    await cb.answer()

    if lang == "fa":
        status = "🟢 فعال" if active else "🔴 غیرفعال"
        text = (
            "<b>⚙️ وضعیت AutoTrade</b>\n\n"
            f"وضعیت سرویس: <b>{status}</b>\n\n"
            + (
                "برای مشاهده حساب متصل، معاملات و تنظیمات AutoTrade روی دکمه مدیریت بزنید."
                if active
                else "برای فعال‌سازی AutoTrade از منوی اصلی «خرید اشتراک» استفاده کنید."
            )
        )
        rows = []
        if active:
            rows.append([InlineKeyboardButton(text="⚙️ مدیریت AutoTrade", callback_data="client_autotrade_access")])
        rows.append([InlineKeyboardButton(text="🏠 منوی اصلی", callback_data="main")])
    else:
        status = "🟢 Active" if active else "🔴 Inactive"
        text = (
            "<b>⚙️ AutoTrade Status</b>\n\n"
            f"Service status: <b>{status}</b>\n\n"
            + (
                "Open AutoTrade management to view the connected account, trades and settings."
                if active
                else "Use “Buy Subscription” on the main menu to activate AutoTrade."
            )
        )
        rows = []
        if active:
            rows.append([InlineKeyboardButton(text="⚙️ Manage AutoTrade", callback_data="client_autotrade_access")])
        rows.append([InlineKeyboardButton(text="🏠 Main Menu", callback_data="main")])

    await core.screen(
        bot,
        cb.from_user.id,
        cb.message.chat.id,
        text,
        InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(lambda cb: cb.data == "customer_support")
async def customer_support(cb: CallbackQuery, bot: Bot) -> None:
    from . import main as core

    if not await core.gated(cb, bot):
        return

    lang = core.get_lang(cb.from_user.id)
    await cb.answer()
    await core.screen(
        bot,
        cb.from_user.id,
        cb.message.chat.id,
        core.tr(
            lang,
            "<b>🛟 پشتیبانی NEXUS</b>\n\nبرای ارتباط مستقیم با پشتیبانی یا مشاهده سوالات متداول، یکی از گزینه‌های زیر را انتخاب کنید.",
            "<b>🛟 NEXUS Support</b>\n\nChoose direct support or browse the FAQ below.",
        ),
        support_menu(lang),
    )


def install_customer_menu_runtime(core: Any) -> None:
    if getattr(core.router, "__nexus_customer_menu_runtime_installed__", False):
        return

    # customer_experience's dynamic home renderers resolve this global at call
    # time, so replacing it here updates every subsequent home refresh.
    cx.customer_main_menu = customer_main_menu
    cx.faq_menu = faq_menu

    core.router.include_router(router)
    core.router.__nexus_customer_menu_runtime_installed__ = True
