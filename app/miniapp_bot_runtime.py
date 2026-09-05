from __future__ import annotations

import os
from typing import Any

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from . import customer_experience as cx

router = Router(name="nexus-miniapp-bot-runtime")
_INSTALLED = False


def _url() -> str:
    return os.getenv("MINIAPP_URL", "").strip()


@router.message(Command("app"))
async def open_miniapp(message: Message) -> None:
    url = _url()
    lang = "fa"
    try:
        from . import main as core
        lang = core.get_lang(message.from_user.id)
    except Exception:
        pass

    if not url:
        text = "آدرس مینی‌اپ هنوز تنظیم نشده است." if lang == "fa" else "The Mini App URL is not configured yet."
        await message.answer(text)
        return

    label = "⚡ ورود به مینی‌اپ NEXUS" if lang == "fa" else "⚡ Open NEXUS Mini App"
    text = "پنل یکپارچه NEXUS را باز کنید:" if lang == "fa" else "Open the integrated NEXUS dashboard:"
    await message.answer(
        text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=label, web_app=WebAppInfo(url=url))]]
        ),
    )


def install_miniapp_bot_runtime(core: Any) -> None:
    """Add Mini App entry without changing the approved customer menu layout.

    The existing «Enter NEXUS» public-channel button remains first. Mini App is
    inserted immediately after it. Signal issuance is intentionally absent from
    the Mini App and enforced by tests/API contract.
    """
    global _INSTALLED
    if _INSTALLED:
        return

    url = _url()
    if url:
        original = cx.customer_main_menu

        def _menu(lang: str, *, is_admin: bool, has_vip: bool):
            markup = original(lang, is_admin=is_admin, has_vip=has_vip)
            label = "⚡ مینی‌اپ NEXUS" if lang == "fa" else "⚡ NEXUS Mini App"
            row = [InlineKeyboardButton(text=label, web_app=WebAppInfo(url=url))]
            # Keep the approved public NEXUS entry as the first row.
            insert_at = 1 if markup.inline_keyboard else 0
            markup.inline_keyboard.insert(insert_at, row)
            return markup

        cx.customer_main_menu = _menu

    core.router.include_router(router)
    _INSTALLED = True
