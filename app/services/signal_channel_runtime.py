from __future__ import annotations

"""Correct customer signal-channel navigation.

The general NEXUS public channel remains the mandatory join gate at bot entry.
Inside the Signals dashboard, the Public Signals action must point to the
separate free/public-signal channel (FREE_CHANNEL_URL), never to
PUBLIC_CHANNEL_URL.
"""

import logging
from typing import Any

from aiogram import F
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


log = logging.getLogger(__name__)
_INSTALLED = False


def _callback_button(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def _client_signal_menu(main: Any, lang: str, has_vip: bool, has_autotrade: bool = False) -> InlineKeyboardMarkup:
    free_url = str(main.settings.free_channel_url).strip()
    if not free_url:
        raise RuntimeError("FREE_CHANNEL_URL is not configured")

    if lang == "fa":
        public_label = "🎯 سیگنال عمومی"
        vip_label = ("🔓" if has_vip else "🔒") + " سیگنال VIP"
        auto_label = ("🔓" if has_autotrade else "🔒") + " سیگنال + AutoTrade"
        back_label = "⬅️ بازگشت"
        home_label = "🏠 منوی اصلی"
    else:
        public_label = "🎯 Public Signals"
        vip_label = ("🔓" if has_vip else "🔒") + " VIP Signals"
        auto_label = ("🔓" if has_autotrade else "🔒") + " Signals + AutoTrade"
        back_label = "⬅️ Back"
        home_label = "🏠 Main Menu"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=public_label, url=free_url)],
            [
                _callback_button(vip_label, "client_vip_access"),
                _callback_button(auto_label, "client_autotrade_access"),
            ],
            [
                _callback_button(back_label, "main"),
                _callback_button(home_label, "main"),
            ],
        ]
    )


def _remove_legacy_public_handler(main: Any) -> None:
    main.router.callback_query.handlers[:] = [
        handler
        for handler in main.router.callback_query.handlers
        if getattr(handler.callback, "__name__", "") != "public_channel"
    ]


def _register_legacy_public_callback(main: Any) -> None:
    """Keep old inline keyboards safe after deploy; route them to free signals."""

    async def legacy_public_signal(cb, bot):
        if not await main.gated(cb, bot):
            return
        lang = main.get_lang(cb.from_user.id)
        await cb.answer()
        free_url = str(main.settings.free_channel_url).strip()
        if lang == "fa":
            text = "<b>🎯 کانال سیگنال عمومی NEXUS</b>\n\nبرای مشاهده سیگنال‌های عمومی وارد کانال سیگنال عمومی شوید."
            open_label = "🎯 ورود به کانال سیگنال عمومی"
            back_label = "⬅️ بازگشت"
            home_label = "🏠 منوی اصلی"
        else:
            text = "<b>🎯 NEXUS Public Signals</b>\n\nOpen the public-signal channel to view free signals."
            open_label = "🎯 Open Public Signals"
            back_label = "⬅️ Back"
            home_label = "🏠 Main Menu"
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=open_label, url=free_url)],
                [
                    _callback_button(back_label, "client_signals"),
                    _callback_button(home_label, "main"),
                ],
            ]
        )
        await main.screen(bot, cb.from_user.id, cb.message.chat.id, text, markup)

    main.router.callback_query.register(legacy_public_signal, F.data == "public")


def install(main: Any) -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    # app.main imported client_signal_menu into its module namespace, therefore
    # replacing this module global updates the menu used by the existing handler.
    main.client_signal_menu = lambda lang, has_vip, has_autotrade=False: _client_signal_menu(
        main, lang, has_vip, has_autotrade
    )
    _remove_legacy_public_handler(main)
    _register_legacy_public_callback(main)

    _INSTALLED = True
    log.info(
        "[NEXUS][SIGNAL_CHANNEL_ROUTING][INSTALLED] public-signals=FREE_CHANNEL_URL general-public=join-gate-only"
    )
