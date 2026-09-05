from __future__ import annotations

import asyncio
import os
import socket
import json
import logging
from logging.handlers import RotatingFileHandler
import math
import re
import secrets
import shutil
from io import BytesIO
from pathlib import Path
from datetime import datetime, timezone, timedelta, date
from html import escape
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.session.aiohttp import AiohttpSession
from aiohttp.resolver import AsyncResolver
from aiogram.enums import ChatMemberStatus, ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, ChatJoinRequest, InlineKeyboardButton, InlineKeyboardMarkup, Message, BufferedInputFile, ReplyParameters, WebAppInfo

from .config import settings
from . import db
from .signals.card_generator import build_chart_frame, build_report_card
from .signals.calculator import risk_reward, result_metric
from .states import Flow
from .storage.sqlite_storage import SQLiteStorage
from .services import license_service
from .services import pricing_service
from .autotrade.trailing_profiles import profile_guide
from .autotrade.exchange_service import SUPPORTED_EXCHANGES, test_connection as test_exchange_connection, encrypt_credentials, decrypt_credentials, ExchangeConnectionError
from .autotrade.symbol_registry import normalize_symbol
from .routers.analytics import router as analytics_router
from .routers.subscriptions import router as subscriptions_router
from .ui import (
    account_menu,
    my_payments_menu,
    admin_menu,
    admin_payment,
    admin_user_actions,
    discounts_menu,
    campaign_menu,
    campaign_plan_menu,
    campaign_audience_menu,
    broadcast_target_menu,
    broadcast_confirm_menu,
    join_gate,
    kb,
    language_menu,
    main_menu,
    guide_hub_menu,
    guide_back_menu,
    client_signal_menu,
    nav,
    payment_actions,
    payment_method,
    plan_options,
    plans,
    subscription_service_menu,
    plans_for_service,
    referral_menu,
    reward_settings_menu,
    autotrade_waitlist_menu,
    admin_crm_menu,
    admin_users_group,
    admin_finance_group,
    admin_rewards_group,
    admin_content_group,
    admin_marketing_group,
    admin_reports_group,
    admin_system_group,
    signal_center_menu,
    signal_market_menu,
    signal_symbol_menu,
    signal_direction_menu,
    signal_order_type_menu,
    signal_timeframe_menu,
    signal_trailing_preset_menu,
    TRAILING_PRESETS,
    signal_volume_mode_menu,
    trailing_guide_menu,
    trailing_guide_detail_menu,
    autotrade_user_menu,
    exchange_select_menu,
    exchange_connected_menu,
    signal_destination_menu,
    signal_confirm_menu,
    signal_manage_menu,
    admin_plan_list_menu,
    admin_plan_edit_menu,
)

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
_LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
logging.basicConfig(
    level=logging.INFO,
    format=_LOG_FORMAT,
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler(LOG_DIR / "nexus.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8"),
    ],
)
log = logging.getLogger("nexus-core-v0.6.5")  # NEXUS v0.6.5
router = Router()

# One serialized reply chain per signal/channel. This prevents concurrent
# SL/TP/BE events from branching the Telegram thread.
_REPLY_CHAIN_LOCKS: dict[tuple[int, str], asyncio.Lock] = {}
_REPLY_CHAIN_LOCKS_GUARD = asyncio.Lock()

async def _reply_chain_lock(signal_id: int, channel: str) -> asyncio.Lock:
    key = (int(signal_id), str(channel).upper())
    async with _REPLY_CHAIN_LOCKS_GUARD:
        lock = _REPLY_CHAIN_LOCKS.get(key)
        if lock is None:
            lock = asyncio.Lock()
            _REPLY_CHAIN_LOCKS[key] = lock
        return lock
BACKGROUND_TASKS: set[asyncio.Task] = set()
SIGNAL_PUBLISH_LOCKS: dict[int, asyncio.Lock] = {}
TZ = ZoneInfo(settings.timezone)
BOT_USERNAME = ""



def is_admin(user_id: int) -> bool:
    return user_id in settings.admin_ids


def get_lang(user_id: int) -> str:
    row = db.get_user(user_id)
    return row["language"] if row and row["language"] in {"fa", "en"} else "fa"


def tr(lang: str, fa: str, en: str) -> str:
    return fa if lang == "fa" else en


def fmt_dt(iso: str | None) -> str:
    if not iso:
        return "—"
    dt = datetime.fromisoformat(iso).astimezone(TZ)
    return dt.strftime("%Y/%m/%d - %H:%M")


def remaining_days(expires_at: str) -> int:
    delta = datetime.fromisoformat(expires_at) - datetime.now(timezone.utc)
    return max(0, int((delta.total_seconds() + 86399) // 86400))


def parse_irr(value: str) -> int | None:
    digits = re.sub(r"[^0-9]", "", value or "")
    return int(digits) if digits else None


def fmt_irr(value: int) -> str:
    return f"{value:,}".replace(",", ".") + " تومان"


def discounted_amount(base: int, pct: float) -> int:
    return max(0, int(round(base * (100.0 - pct) / 100.0)))


def _plans(*, active_only: bool = True) -> dict[str, dict[str, object]]:
    catalog = db.plan_map(active_only=active_only)
    return catalog or settings.plans


def _usdt_plan_ready(plan: dict[str, object]) -> bool:
    if not settings.usdt_wallet:
        return False
    if not settings.usdt_network or settings.usdt_network.upper().startswith("SET_"):
        return False
    value = str(plan.get("usdt", "")).strip()
    return bool(value and not value.upper().startswith("SET_"))


async def check_public_member(bot: Bot, user_id: int) -> bool | None:
    """Return True/False for a real membership result and None for Telegram/API failure."""
    try:
        member = await bot.get_chat_member(settings.public_channel_id, user_id)
        return member.status not in {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED}
    except Exception as exc:
        log.warning("public membership API check failed for %s: %s", user_id, exc)
        return None


async def maybe_reward_referral(bot: Bot, referred_id: int) -> None:
    result = db.reward_referral_if_ready(referred_id)
    if not result:
        return
    referrer_id, points = result
    lang = get_lang(referrer_id)
    try:
        await bot.send_message(
            referrer_id,
            tr(
                lang,
                f"🎉 <b>دعوت موفق!</b>\n\nیک کاربر دعوت‌شده عضویت خود را تأیید کرد و <b>{points} ⭐ NEXUS Points</b> به حساب شما اضافه شد.",
                f"🎉 <b>Successful referral!</b>\n\nA referred user confirmed membership and <b>{points} ⭐ NEXUS Points</b> were added to your account.",
            ),
            parse_mode=ParseMode.HTML,
        )
    except Exception as exc:
        log.warning("referral notification failed: %s", exc)


async def ensure_user(message_or_cb, bot: Bot) -> bool | None:
    user = message_or_cb.from_user
    db.upsert_user(user.id, user.username, user.first_name)
    ok = await check_public_member(bot, user.id)
    if ok is None:
        # Do not turn a Telegram outage into a false "not a member" result.
        # Previously verified members may continue; unknown users get a temporary error.
        existing = db.get_user(user.id)
        return True if existing and bool(existing["joined_public"]) else None
    db.mark_public_joined(user.id, ok)
    if ok:
        await maybe_reward_referral(bot, user.id)
    return ok


async def clean_user_message(message: Message) -> bool:
    try:
        await message.delete()
        return True
    except Exception as exc:
        log.warning("Could not delete message %s in chat %s: %s", message.message_id, message.chat.id, exc)
        return False


async def screen(bot: Bot, user_id: int, chat_id: int, text: str, markup=None) -> None:
    """Render the current dashboard as the newest message in the chat.

    NEXUS intentionally keeps a single navigation/dashboard message. The old
    dashboard is deleted and a fresh one is sent, so menus never remain above
    newly delivered licenses, installers, videos, receipts, or status messages.
    """
    if isinstance(text, (tuple, list)):
        log.warning("screen() received %s instead of str; normalizing", type(text).__name__)
        text = "".join(str(x) for x in text)
    elif not isinstance(text, str):
        text = str(text)

    user = db.get_user(user_id)
    old_id = user["last_menu_message_id"] if user else None
    if old_id:
        try:
            await bot.delete_message(chat_id, int(old_id))
        except Exception:
            pass

    msg = await bot.send_message(
        chat_id,
        text,
        reply_markup=markup,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )
    db.set_last_menu_message(user_id, msg.message_id)


async def show_language(bot: Bot, user_id: int, chat_id: int) -> None:
    await screen(bot, user_id, chat_id, "<b>🌐 NEXUS</b>\n\nزبان خود را انتخاب کنید.\nChoose your language.", language_menu())


async def show_gate(bot: Bot, user_id: int, chat_id: int) -> None:
    lang = get_lang(user_id)
    text = tr(
        lang,
        "<b>به NEXUS خوش آمدید.</b>\n\nبرای استفاده از ربات، ابتدا عضو کانال عمومی NEXUS شوید و سپس «بررسی عضویت» را بزنید.",
        "<b>Welcome to NEXUS.</b>\n\nJoin the NEXUS public channel first, then tap “Check Membership”.",
    )
    await screen(bot, user_id, chat_id, text, join_gate(lang))


async def show_main(bot: Bot, user_id: int, chat_id: int) -> None:
    lang = get_lang(user_id)
    await screen(
        bot,
        user_id,
        chat_id,
        tr(lang, "<b>⚡ NEXUS</b>\n\nاز این بخش می‌توانید سیگنال‌ها، معاملات خودکار و حساب کاربری خود را مدیریت کنید.\n\nسرویس موردنظر را انتخاب کنید:", "<b>⚡ NEXUS</b>\n\nManage signals, Auto Trade and your account from here.\n\nSelect a service:"),
        main_menu(lang, is_admin(user_id)),
    )


async def show_admin(bot: Bot, user_id: int, chat_id: int) -> None:
    lang = get_lang(user_id)
    await screen(
        bot, user_id, chat_id,
        tr(lang, "<b>🛠 پنل ادمین NEXUS</b>\n\nبخش موردنظر را انتخاب کنید.", "<b>🛠 NEXUS Admin Panel</b>\n\nChoose a section."),
        admin_menu(lang),
    )


async def push_home_to_bottom(bot: Bot, user_id: int) -> None:
    """Delete the previous dashboard and send a fresh one after a broadcast."""
    user = db.get_user(user_id)
    if not user:
        return
    old_id = user["last_menu_message_id"]
    if old_id:
        try:
            await bot.delete_message(user_id, int(old_id))
        except Exception:
            pass
    lang = get_lang(user_id)
    if is_admin(user_id):
        text = tr(lang, "<b>🛠 پنل ادمین NEXUS</b>", "<b>🛠 NEXUS Admin Panel</b>")
        markup = admin_menu(lang)
    else:
        text = tr(lang, "<b>⚡ NEXUS</b>\n\nمنوی اصلی", "<b>⚡ NEXUS</b>\n\nMain Menu")
        markup = main_menu(lang, False)
    msg = await bot.send_message(user_id, text, reply_markup=markup, parse_mode=ParseMode.HTML)
    db.set_last_menu_message(user_id, msg.message_id)


@router.message(CommandStart())
async def start(message: Message, bot: Bot, state: FSMContext):
    await state.clear()
    db.upsert_user(message.from_user.id, message.from_user.username, message.from_user.first_name)

    # Deep-link referral: /start ref_NX123...
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) == 2 and parts[1].startswith("ref_"):
        code = parts[1][4:].strip()
        referrer = db.get_user_by_referral(code)
        if referrer and int(referrer["telegram_id"]) != message.from_user.id:
            db.set_referred_by(message.from_user.id, int(referrer["telegram_id"]))

    await clean_user_message(message)
    user = db.get_user(message.from_user.id)
    if is_admin(message.from_user.id):
        if not user or not user["language"]:
            db.set_language(message.from_user.id, "fa")
        lang = get_lang(message.from_user.id)
        await screen(
            bot, message.from_user.id, message.chat.id,
            tr(lang,
               "<b>به پنل مدیریت NEXUS خوش آمدید.</b>\n\nربات آماده است. بخش موردنظر را از منوی زیر انتخاب کنید.",
               "<b>Welcome to the NEXUS Admin Panel.</b>\n\nThe bot is ready. Choose a section below."),
            admin_menu(lang),
        )
        return
    if not user or not user["language"]:
        await show_language(bot, message.from_user.id, message.chat.id)
        return
    ok = await ensure_user(message, bot)
    if ok is None:
        await screen(bot, message.from_user.id, message.chat.id, tr(get_lang(message.from_user.id), "⚠️ بررسی عضویت تلگرام موقتاً در دسترس نیست. چند لحظه دیگر دوباره تلاش کنید.", "⚠️ Telegram membership verification is temporarily unavailable. Please try again shortly."), join_gate(get_lang(message.from_user.id)))
        return
    await (show_main(bot, message.from_user.id, message.chat.id) if ok else show_gate(bot, message.from_user.id, message.chat.id))


@router.message(Command("app"))
async def open_miniapp(message: Message):
    """Open the authenticated Telegram Mini App from a dedicated command."""
    lang = get_lang(message.from_user.id)
    if not settings.miniapp_url:
        await message.answer(tr(lang, "آدرس مینی‌اپ هنوز تنظیم نشده است.", "The Mini App URL is not configured yet."))
        return
    label = tr(lang, "⚡ ورود به مینی‌اپ NEXUS", "⚡ Open NEXUS Mini App")
    await message.answer(
        tr(lang, "پنل یکپارچه NEXUS را باز کنید:", "Open the integrated NEXUS dashboard:"),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=label, web_app=WebAppInfo(url=settings.miniapp_url))
        ]]),
    )


@router.callback_query(F.data.startswith("lang:"))
async def choose_language(cb: CallbackQuery, bot: Bot, state: FSMContext):
    await state.clear()
    lang = cb.data.split(":", 1)[1]
    if lang not in {"fa", "en"}:
        await cb.answer()
        return
    db.upsert_user(cb.from_user.id, cb.from_user.username, cb.from_user.first_name)
    db.set_language(cb.from_user.id, lang)
    await cb.answer("زبان فارسی انتخاب شد ✅" if lang == "fa" else "English selected ✅")
    if is_admin(cb.from_user.id):
        await show_admin(bot, cb.from_user.id, cb.message.chat.id)
        return
    ok = await ensure_user(cb, bot)
    if ok is None:
        await screen(bot, cb.from_user.id, cb.message.chat.id, tr(lang, "⚠️ بررسی عضویت تلگرام موقتاً در دسترس نیست. دوباره تلاش کنید.", "⚠️ Telegram membership verification is temporarily unavailable. Try again."), join_gate(lang))
        return
    await (show_main(bot, cb.from_user.id, cb.message.chat.id) if ok else show_gate(bot, cb.from_user.id, cb.message.chat.id))


@router.callback_query(F.data == "change_language")
async def change_language(cb: CallbackQuery, bot: Bot, state: FSMContext):
    await state.clear()
    await cb.answer()
    await show_language(bot, cb.from_user.id, cb.message.chat.id)


@router.callback_query(F.data == "check_public")
async def check_public(cb: CallbackQuery, bot: Bot):
    lang = get_lang(cb.from_user.id)
    ok = await ensure_user(cb, bot)
    if ok is None:
        await cb.answer(tr(lang, "بررسی عضویت موقتاً در دسترس نیست؛ دوباره تلاش کنید.", "Membership verification is temporarily unavailable; try again."), show_alert=True)
        return
    await cb.answer(
        tr(lang, "عضویت تأیید شد ✅", "Membership confirmed ✅") if ok else tr(lang, "هنوز عضویت شما تأیید نشده است.", "Your membership is not confirmed yet."),
        show_alert=not ok,
    )
    await (show_main(bot, cb.from_user.id, cb.message.chat.id) if ok else show_gate(bot, cb.from_user.id, cb.message.chat.id))


async def gated(cb: CallbackQuery, bot: Bot) -> bool:
    ok = await ensure_user(cb, bot)
    lang = get_lang(cb.from_user.id)
    if ok is None:
        await cb.answer(tr(lang, "بررسی عضویت تلگرام موقتاً در دسترس نیست؛ کمی بعد دوباره تلاش کنید.", "Telegram membership verification is temporarily unavailable; try again shortly."), show_alert=True)
        return False
    if not ok:
        await cb.answer(tr(lang, "برای ادامه ابتدا عضو کانال عمومی شوید.", "Join the public channel first."), show_alert=True)
        await show_gate(bot, cb.from_user.id, cb.message.chat.id)
        return False
    return True


@router.callback_query(F.data == "main")
async def menu(cb: CallbackQuery, bot: Bot, state: FSMContext):
    await state.clear()
    if not await gated(cb, bot):
        return
    await cb.answer()
    await show_main(bot, cb.from_user.id, cb.message.chat.id)




def _guide_video_spec(kind: str):
    base = Path(__file__).resolve().parent.parent / "assets" / "guides"
    mt5_new = base / "NEXUS_AutoTrade_MT5_Guide.mp4"
    mt5_legacy = Path(__file__).resolve().parent.parent / "assets" / "autotrade" / "NEXUS_AutoTrade_Guide.mp4"
    mt5_path = mt5_new if mt5_new.is_file() or not mt5_legacy.is_file() else mt5_legacy
    specs = {
        "intro": (base / "NEXUS_Intro.mp4", settings.guide_intro_video_url, "معرفی NEXUS", "About NEXUS"),
        "purchase": (base / "NEXUS_Purchase_Guide.mp4", settings.guide_purchase_video_url, "راهنمای خرید و اشتراک", "Purchase & Subscription Guide"),
        "mt5": (mt5_path, settings.guide_mt5_video_url, "آموزش نصب و فعال‌سازی معاملات خودکار MT5", "MT5 Auto Trade Installation & Activation"),
        "crypto": (base / "NEXUS_AutoTrade_Crypto_Guide.mp4", settings.guide_crypto_video_url, "راهنمای معاملات خودکار صرافی", "Exchange Auto Trade Guide"),
    }
    return specs[kind]


async def _send_guide_video(bot: Bot, user_id: int, kind: str) -> bool:
    lang = get_lang(user_id)
    local_path, url, fa_title, en_title = _guide_video_spec(kind)
    title = tr(lang, fa_title, en_title)
    if local_path.is_file():
        await bot.send_video(
            user_id,
            BufferedInputFile(local_path.read_bytes(), filename=local_path.name),
            caption=f"🎥 <b>{escape(title)}</b>",
            parse_mode=ParseMode.HTML,
            protect_content=True,
            supports_streaming=True,
        )
        return True
    if url:
        markup = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=tr(lang, "▶️ مشاهده کلیپ", "▶️ Watch Video"), url=url)
        ]])
        await bot.send_message(
            user_id,
            tr(lang, f"🎥 <b>{escape(title)}</b>\n\nبرای مشاهده کلیپ روی دکمه زیر بزنید.", f"🎥 <b>{escape(title)}</b>\n\nTap below to watch the video."),
            reply_markup=markup,
            parse_mode=ParseMode.HTML,
        )
        return True
    return False


@router.callback_query(F.data == "guide_hub")
async def guide_hub(cb: CallbackQuery, bot: Bot):
    if not await gated(cb, bot): return
    lang = get_lang(cb.from_user.id); await cb.answer()
    text = tr(
        lang,
        "<b>🎓 معرفی و راهنمای NEXUS</b>\n\nدر این بخش کلیپ‌های معرفی و آموزش‌های مرحله‌به‌مرحله قرار می‌گیرند.\n\n• معرفی NEXUS و خدمات\n• خرید و فعال‌سازی اشتراک\n• نصب و فعال‌سازی معاملات خودکار روی MT5\n• اتصال معاملات خودکار صرافی\n• راهنمای متنی کامل\n\nیکی از گزینه‌های زیر را انتخاب کنید.",
        "<b>🎓 NEXUS Introduction & Guides</b>\n\nThis section contains introduction videos and step-by-step tutorials.\n\n• NEXUS services overview\n• Purchase and subscription activation\n• MT5 Auto Trade installation and activation\n• Exchange Auto Trade connection\n• Full text guide\n\nChoose a section below.",
    )
    await screen(bot, cb.from_user.id, cb.message.chat.id, text, guide_hub_menu(lang))


@router.callback_query(F.data.in_({"guide_intro", "guide_purchase", "guide_mt5", "guide_crypto"}))
async def guide_video(cb: CallbackQuery, bot: Bot):
    if not await gated(cb, bot): return
    lang = get_lang(cb.from_user.id); await cb.answer()
    kind = cb.data.split("_", 1)[1]
    ok = await _send_guide_video(bot, cb.from_user.id, kind)
    if not ok:
        path, _, fa_title, en_title = _guide_video_spec(kind)
        await bot.send_message(
            cb.from_user.id,
            tr(lang,
               f"🎥 <b>{escape(fa_title)}</b>\n\nکلیپ هنوز روی سرور قرار نگرفته است.\nنام فایل مورد انتظار: <code>{escape(path.name)}</code>",
               f"🎥 <b>{escape(en_title)}</b>\n\nThe video has not been uploaded to the server yet.\nExpected filename: <code>{escape(path.name)}</code>"),
            parse_mode=ParseMode.HTML,
        )
    # Keep the guide dashboard as the last menu after media/messages.
    user = db.get_user(cb.from_user.id)
    old_id = user["last_menu_message_id"] if user else None
    if old_id:
        try: await bot.delete_message(cb.from_user.id, int(old_id))
        except Exception: pass
    msg = await bot.send_message(
        cb.from_user.id,
        tr(lang, "<b>🎓 معرفی و راهنما</b>\n\nراهنمای دیگری را انتخاب کنید.", "<b>🎓 Introduction & Guides</b>\n\nChoose another guide."),
        reply_markup=guide_hub_menu(lang),
        parse_mode=ParseMode.HTML,
    )
    db.set_last_menu_message(cb.from_user.id, msg.message_id)


@router.callback_query(F.data == "guide_text")
async def guide_text(cb: CallbackQuery, bot: Bot):
    if not await gated(cb, bot): return
    lang = get_lang(cb.from_user.id); await cb.answer()
    text = tr(
        lang,
        "<b>📘 راهنمای سریع NEXUS</b>\n\n<b>سیگنال‌ها:</b> از منوی کانال تحلیل و سیگنال، دسترسی عمومی، وی‌آی‌پی یا وی‌آی‌پی + معاملات خودکار را انتخاب کنید.\n\n<b>خرید:</b> پلن را انتخاب، پرداخت را انجام و رسید را ارسال کنید. پس از تأیید ادمین، دسترسی مربوطه فعال می‌شود.\n\n<b>معاملات خودکار MT5:</b> پس از خرید، مجوز و فایل EX5 را دریافت می‌کنید. فایل را در MQL5/Experts قرار دهید، Algo Trading را روشن کنید، EA را روی Chart بیندازید، مجوز را وارد و اتصال و فعال‌سازی را بزنید.\n\n<b>معاملات خودکار صرافی:</b> پس از فعال شدن این سرویس، API مخصوص Trading را بدون مجوز Withdrawal متصل می‌کنید.\n\n<b>امنیت:</b> مجوز و فایل اختصاصی خود را در اختیار دیگران قرار ندهید. معاملات خودکار اجرای خودکار سیگنال است و تضمین سودآوری نیست.",
        "<b>📘 NEXUS Quick Guide</b>\n\n<b>Signals:</b> Open Analysis & Signals and choose Public, VIP, or VIP + Auto Trade.\n\n<b>Purchase:</b> Choose a plan, pay, and upload the receipt. Access is activated after admin approval.\n\n<b>MT5 Auto Trade:</b> After purchase you receive a License and EX5. Put the file in MQL5/Experts, enable Algo Trading, attach the EA, enter the License, and press CONNECT & ACTIVATE.\n\n<b>Exchange Auto Trade:</b> When enabled, connect a trade-only API with Withdrawal disabled.\n\n<b>Security:</b> Do not share your License or installer. Auto Trade automates signal execution and does not guarantee profit.",
    )
    await screen(bot, cb.from_user.id, cb.message.chat.id, text, guide_back_menu(lang))


@router.callback_query(F.data == "client_signals")
async def client_signals(cb: CallbackQuery, bot: Bot):
    if not await gated(cb, bot): return
    lang = get_lang(cb.from_user.id)
    access = license_service.snapshot(cb.from_user.id)
    await cb.answer()
    await screen(
        bot, cb.from_user.id, cb.message.chat.id,
        tr(lang,
           "<b>📊 NEXUS SIGNALS</b>\n\n🎯 سیگنال عمومی: دسترسی رایگان\n💎 وی‌آی‌پی: سیگنال کامل و مدیریت لحظه‌ای\n🤖 وی‌آی‌پی + معاملات خودکار: اجرای خودکار سیگنال روی حساب معاملاتی\n\nنوع دسترسی را انتخاب کنید.",
           "<b>📊 NEXUS SIGNALS</b>\n\n🎯 Public Signals: free access\n💎 VIP: full signals and live management\n🤖 VIP + Auto Trade: automatic execution on your trading account\n\nChoose your access."),
        client_signal_menu(lang, access.vip, access.autotrade),
    )


@router.callback_query(F.data == "client_vip_access")
async def client_vip_access(cb: CallbackQuery, bot: Bot):
    if not await gated(cb, bot): return
    lang = get_lang(cb.from_user.id)
    access = license_service.snapshot(cb.from_user.id)
    lic = db.active_license(cb.from_user.id)
    await cb.answer()
    if not (lic and access.vip):
        markup = kb([[
            ("💎 خرید اشتراک" if lang == "fa" else "💎 Buy Subscription", "vip")
        ]] + nav(lang, "client_signals"))
        await screen(bot, cb.from_user.id, cb.message.chat.id,
                     tr(lang,
                        "<b>دسترسی وی‌آی‌پی فعال نیست.</b>\n\nبرای ورود به کانال وی‌آی‌پی ابتدا اشتراک تهیه کنید.",
                        "<b>VIP access is not active.</b>\n\nBuy a subscription to access the VIP channel."), markup)
        return
    try:
        link = await make_secure_invite(bot, cb.from_user.id, int(lic["id"]))
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=tr(lang, "🔐 ورود به کانال وی‌آی‌پی", "🔐 Open VIP Channel"), url=link)],
            [InlineKeyboardButton(text=tr(lang, "⬅️ بازگشت", "⬅️ Back"), callback_data="client_signals")],
        ])
        await screen(bot, cb.from_user.id, cb.message.chat.id,
                     tr(lang,
                        f"<b>دسترسی VIP فعال است.</b>\n\nاعتبار تا: <b>{fmt_dt(lic['vip_expires_at'] if 'vip_expires_at' in lic.keys() and lic['vip_expires_at'] else lic['expires_at'])}</b>",
                        f"<b>VIP access is active.</b>\n\nValid until: <b>{fmt_dt(lic['vip_expires_at'] if 'vip_expires_at' in lic.keys() and lic['vip_expires_at'] else lic['expires_at'])}</b>"), markup)
    except Exception as exc:
        log.exception("VIP access link failed")
        await screen(bot, cb.from_user.id, cb.message.chat.id,
                     tr(lang, "ساخت لینک وی‌آی‌پی با خطا مواجه شد. کمی بعد دوباره تلاش کنید.", "Could not create a VIP link. Try again shortly."),
                     kb(nav(lang, "client_signals")))


@router.callback_query(F.data == "client_autotrade_access")
async def client_autotrade_access(cb: CallbackQuery, bot: Bot):
    if not await gated(cb, bot): return
    lang = get_lang(cb.from_user.id)
    access = license_service.snapshot(cb.from_user.id)
    lic = db.active_license(cb.from_user.id)
    await cb.answer()
    if not (lic and access.autotrade):
        markup = kb([[
            ("💎 خرید / ارتقای اشتراک" if lang == "fa" else "💎 Buy / Upgrade", "vip")
        ]] + nav(lang, "client_signals"))
        await screen(bot, cb.from_user.id, cb.message.chat.id,
                     tr(lang,
                        "<b>🤖 NEXUS AUTO TRADE</b>\n\nمعاملات خودکار سیگنال‌های NEXUS را به‌صورت خودکار روی حساب معاملاتی اجرا و تا پایان مدیریت می‌کند.\n\nاگر وی‌آی‌پی دارید، می‌توانید فقط افزونه معاملات خودکار را تهیه کنید. اگر اشتراک ندارید، پلن وی‌آی‌پی + معاملات خودکار را انتخاب کنید.\n\nوضعیت فعلی: <b>غیرفعال</b>\nقدم بعدی: خرید یا ارتقای اشتراک.",
                        "<b>🤖 NEXUS AUTO TRADE</b>\n\nAuto Trade executes NEXUS signals automatically and manages the trade through completion.\n\nIf you already have VIP, you can add Auto Trade only. Otherwise choose a VIP + Auto Trade plan.\n\nCurrent status: <b>Inactive</b>\nNext step: purchase or upgrade."), markup)
        return
    mt5 = db.mt5_account(cb.from_user.id)
    exch = db.exchange_account(cb.from_user.id)
    key = str(lic["license_key"] or "").strip()
    text = tr(
        lang,
        (
            "🤖 <b>NEXUS معاملات خودکار</b>\n\n"
            "این بخش مرکز مدیریت معاملات خودکار شماست.\n\n"
            "🟢 وضعیت سرویس: <b>فعال</b>\n"
            f"🔑 License: <code>{escape(key)}</code>\n"
            f"📅 اعتبار تا: <b>{fmt_dt(lic['autotrade_expires_at'] if 'autotrade_expires_at' in lic.keys() and lic['autotrade_expires_at'] else lic['expires_at'])}</b>\n"
            f"🖥 MT5: <b>{'متصل' if mt5 else 'متصل نیست'}</b>\n"
            f"₿ صرافی: <b>{escape(str(exch['exchange'])) + ' / ' + escape(str(exch['status'])) if exch else 'متصل نیست'}</b>\n\n"
            "از منوی زیر وضعیت و معاملات را مدیریت کنید. برای راهنما از منوی اصلی وارد بخش «راهنما» شوید."
        ),
        (
            "🤖 <b>NEXUS معاملات خودکار</b>\n\n"
            "This is your Auto Trade control center.\n\n"
            "🟢 Service: <b>ACTIVE</b>\n"
            f"🔑 License: <code>{escape(key)}</code>\n"
            f"📅 Valid until: <b>{fmt_dt(lic['autotrade_expires_at'] if 'autotrade_expires_at' in lic.keys() and lic['autotrade_expires_at'] else lic['expires_at'])}</b>\n"
            f"🖥 MT5: <b>{'متصل' if mt5 else 'متصل نیست'}</b>\n"
            f"₿ صرافی: <b>{escape(str(exch['exchange'])) + ' / ' + escape(str(exch['status'])) if exch else 'متصل نیست'}</b>\n\n"
            "Use the menu below for status and trades. For guides, return to the main menu and open Guide."
        ),
    )
    await screen(bot, cb.from_user.id, cb.message.chat.id, text,
                 autotrade_user_menu(lang, mt5_connected=bool(mt5), exchange_connected=bool(exch)))


async def _show_autotrade_home(bot: Bot, user_id: int, chat_id: int) -> None:
    lang=get_lang(user_id); lic=db.active_license(user_id); access=license_service.snapshot(user_id)
    if not (lic and access.autotrade):
        await screen(bot,user_id,chat_id,tr(lang,"معاملات خودکار برای این حساب فعال نیست.","Auto Trade is not active for this account."),kb(nav(lang,"client_signals")))
        return
    mt5=db.mt5_account(user_id); exch=db.exchange_account(user_id)
    text=tr(lang,
            f"🤖 <b>NEXUS معاملات خودکار</b>\n\n🟢 فعال\n🔑 License: <code>{escape(str(lic['license_key']))}</code>\n🖥 MT5: <b>{'متصل' if mt5 else 'متصل نیست'}</b>\n₿ صرافی: <b>{escape(str(exch['exchange'])) if exch else 'متصل نیست'}</b>\n\nبخش موردنظر را انتخاب کنید.",
            f"🤖 <b>NEXUS AUTO TRADE</b>\n\n🟢 ACTIVE\n🔑 <code>{escape(str(lic['license_key']))}</code>\n🖥 MT5: <b>{'CONNECTED' if mt5 else 'NOT CONNECTED'}</b>\n₿ Exchange: <b>{escape(str(exch['exchange'])) if exch else 'NOT CONNECTED'}</b>\n\nChoose a section.")
    await screen(bot,user_id,chat_id,text,autotrade_user_menu(lang,mt5_connected=bool(mt5),exchange_connected=bool(exch)))


@router.callback_query(F.data == "autotrade_status")
async def autotrade_status(cb: CallbackQuery, bot: Bot):
    if not await gated(cb,bot): return
    lang=get_lang(cb.from_user.id); lic=db.active_license(cb.from_user.id); mt5=db.mt5_account(cb.from_user.id); exch=db.exchange_account(cb.from_user.id)
    await cb.answer()
    if not lic or not license_service.has_autotrade(cb.from_user.id):
        await _show_autotrade_home(bot,cb.from_user.id,cb.message.chat.id); return
    mt5_line=(f"{escape(str(mt5['account_number']))} / {escape(str(mt5['broker'] or '—'))}" if mt5 else "NOT CONNECTED")
    ex_line=(f"{escape(str(exch['exchange']))} / {escape(str(exch['status']))}" if exch else "NOT CONNECTED")
    text=tr(lang,
            f"<b>📊 وضعیت معاملات خودکار</b>\n\nاین صفحه وضعیت اتصال و مجوز شما را نشان می‌دهد.\n\n🔑 License: <code>{escape(str(lic['license_key']))}</code>\n🟢 وضعیت: <b>فعال</b>\n📅 انقضا: <b>{fmt_dt(lic['expires_at'])}</b>\n🖥 MT5: <b>{mt5_line}</b>\n₿ صرافی: <b>{ex_line}</b>\n\nقدم بعدی: اگر MT5 متصل نیست، اکسپرت را نصب و مجوز را فعال کنید.",
            f"<b>📊 Auto Trade Status</b>\n\nThis page shows your license and connections.\n\n🔑 License: <code>{escape(str(lic['license_key']))}</code>\n🟢 Status: <b>ACTIVE</b>\n📅 Expire: <b>{fmt_dt(lic['expires_at'])}</b>\n🖥 MT5: <b>{mt5_line}</b>\n₿ Exchange: <b>{ex_line}</b>\n\nNext step: if MT5 is not connected, install the EA and activate your License.")
    await screen(bot,cb.from_user.id,cb.message.chat.id,text,autotrade_user_menu(lang,mt5_connected=bool(mt5),exchange_connected=bool(exch)))


def _autotrade_rows_text(rows, lang: str, *, title_fa: str, title_en: str) -> str:
    title=title_fa if lang=="fa" else title_en
    if not rows:
        return title + ("\n\nموردی برای نمایش وجود ندارد." if lang=="fa" else "\n\nNothing to show.")
    out=[title]
    for r in rows[:15]:
        status=str(r['status']).upper(); result='—'
        if r['result_value'] is not None:
            unit=str(r['result_unit'] or '')
            result=f"{float(r['result_value']):+g} {unit}".strip()
        if lang == "fa":
            out.append(f"\n• <b>{escape(str(r['code']))}</b> | {escape(str(r['symbol']))} {escape(str(r['direction']))}\n  وضعیت: <b>{escape(status)}</b> | حدضرر متحرک: <code>{escape(str(r['trailing_code'] or '—'))}</code> | نتیجه: <b>{escape(result)}</b>")
        else:
            out.append(f"\n• <b>{escape(str(r['code']))}</b> | {escape(str(r['symbol']))} {escape(str(r['direction']))}\n  Status: <b>{escape(status)}</b> | Trail: <code>{escape(str(r['trailing_code'] or '—'))}</code> | Result: <b>{escape(result)}</b>")
    return "\n".join(out)


@router.callback_query(F.data == "autotrade_open")
async def autotrade_open(cb: CallbackQuery, bot: Bot):
    if not await gated(cb,bot): return
    lang=get_lang(cb.from_user.id); await cb.answer()
    rows=db.autotrade_user_signal_receipts(cb.from_user.id,limit=20,open_only=True)
    text=_autotrade_rows_text(rows,lang,title_fa="<b>🖥 معاملات باز معاملات خودکار</b>\n\nمعاملاتی که EA برای حساب شما دریافت/اجرا کرده و هنوز سیگنال بسته نشده است:",title_en="<b>🖥 Open Auto Trade Positions</b>\n\nSignals received/executed for your account that are not closed:")
    await screen(bot,cb.from_user.id,cb.message.chat.id,text,autotrade_user_menu(lang))


@router.callback_query(F.data == "autotrade_history")
async def autotrade_history(cb: CallbackQuery, bot: Bot):
    if not await gated(cb,bot): return
    lang=get_lang(cb.from_user.id); await cb.answer()
    rows=db.autotrade_user_signal_receipts(cb.from_user.id,limit=20,open_only=False)
    text=_autotrade_rows_text(rows,lang,title_fa="<b>📜 تاریخچه معاملات خودکار</b>\n\nآخرین سیگنال‌های دریافت‌شده توسط معاملات خودکار:",title_en="<b>📜 Auto Trade History</b>\n\nLatest signals received by Auto Trade:")
    await screen(bot,cb.from_user.id,cb.message.chat.id,text,autotrade_user_menu(lang))


@router.callback_query(F.data == "autotrade_today")
async def autotrade_today(cb: CallbackQuery, bot: Bot):
    if not await gated(cb,bot): return
    lang=get_lang(cb.from_user.id); await cb.answer(); now=datetime.now(TZ); start,_=_day_bounds(now.date()); start_iso,end_iso=_period_utc(start,now)
    st=db.autotrade_user_daily_stats(cb.from_user.id,start_iso,end_iso)
    text=tr(lang,
            f"<b>📅 گزارش امروز معاملات خودکار</b>\n\nسیگنال دریافت‌شده: <b>{st['total']}</b>\nاجراشده: <b>{st['executed']}</b>\nبسته‌شده: <b>{st['closed']}</b>\n✅ برد: <b>{st['wins']}</b>\n❌ باخت: <b>{st['losses']}</b>\n⚪ سر‌به‌سر: <b>{st['be']}</b>\n\nاین گزارش فقط فعالیت معاملات خودکار حساب شما را نمایش می‌دهد.",
            f"<b>📅 Today's Auto Trade Report</b>\n\nSignals received: <b>{st['total']}</b>\nExecuted: <b>{st['executed']}</b>\nClosed: <b>{st['closed']}</b>\n✅ WIN: <b>{st['wins']}</b>\n❌ LOSS: <b>{st['losses']}</b>\n⚪ BREAK EVEN: <b>{st['be']}</b>\n\nThis report only covers your Auto Trade activity.")
    await screen(bot,cb.from_user.id,cb.message.chat.id,text,autotrade_user_menu(lang))


@router.callback_query(F.data == "autotrade_license")
async def autotrade_license(cb: CallbackQuery, bot: Bot):
    if not await gated(cb,bot): return
    uid=cb.from_user.id; lang=get_lang(uid); lic=db.active_license(uid); await cb.answer()
    if not lic or not license_service.has_autotrade(uid):
        await _show_autotrade_home(bot,uid,cb.message.chat.id); return
    key=str(lic["license_key"] or "").strip()
    account=db.mt5_account(uid)
    if not key:
        text=tr(lang,
            "<b>🔑 مجوز NEXUS</b>\n\n⏳ لایسنس AutoTrade هنوز صادر نشده است. ابتدا شماره حساب MT5 خود را ثبت کنید تا لایسنس اختصاصی به آن متصل و صادر شود.",
            "<b>🔑 NEXUS License</b>\n\n⏳ Your AutoTrade license has not been issued yet. Register your MT5 account first so the dedicated license can be bound and issued.")
    else:
        text=tr(lang,
            f"<b>🔑 مجوز NEXUS</b>\n\n<code>{escape(key)}</code>\n\n🖥 MT5: <code>{escape(str(account['account_number']))}</code>\n📅 اعتبار معاملات خودکار تا: <b>{fmt_dt(lic['autotrade_expires_at'] if 'autotrade_expires_at' in lic.keys() and lic['autotrade_expires_at'] else lic['expires_at'])}</b>\n\nاین مجوز شخصی است و به حساب ثبت‌شده متصل است.",
            f"<b>🔑 NEXUS License</b>\n\n<code>{escape(key)}</code>\n\n🖥 MT5: <code>{escape(str(account['account_number']))}</code>\n📅 Auto Trade valid until: <b>{fmt_dt(lic['autotrade_expires_at'] if 'autotrade_expires_at' in lic.keys() and lic['autotrade_expires_at'] else lic['expires_at'])}</b>\n\nThis License is personal and bound to the registered account.")
    await screen(bot,uid,cb.message.chat.id,text,autotrade_user_menu(lang))


async def _send_mt5_installer_and_help(bot: Bot, user_id: int) -> None:
    lang=get_lang(user_id)
    ea_path = Path(__file__).resolve().parents[1] / "assets" / "autotrade" / "NEXUS_AutoTrade.ex5"
    if not ea_path.exists():
        raise FileNotFoundError(f"Auto Trade installer is missing: {ea_path}")
    await bot.send_document(user_id, BufferedInputFile(ea_path.read_bytes(), filename="NEXUS_AutoTrade.ex5"), caption=tr(lang,"📦 فایل نصب NEXUS معاملات خودکار برای متاتریدر ۵","📦 NEXUS Auto Trade installer for MetaTrader 5"), protect_content=True)
    await bot.send_message(user_id,tr(lang,
        "📘 <b>نصب و فعال‌سازی MT5</b>\n\n1️⃣ MT5 → File → Open Data Folder\n2️⃣ MQL5 → Experts\n3️⃣ فایل EX5 را کپی کنید و MT5 را راه‌اندازی مجدد کنید.\n4️⃣ معاملات الگوریتمی را فعال کنید.\n5️⃣ NEXUS_AutoTrade را روی نمودار قرار دهید.\n6️⃣ مجوز را در پنل روی نمودار وارد و اتصال و فعال‌سازی را بزنید.\n7️⃣ با نمایش «متصل / در انتظار سیگنال»، نصب کامل است.",
        "📘 <b>MT5 Installation & Activation</b>\n\n1️⃣ MT5 → File → Open Data Folder\n2️⃣ MQL5 → Experts\n3️⃣ Copy the EX5 file and restart MT5.\n4️⃣ Enable Algo Trading.\n5️⃣ Attach NEXUS_AutoTrade to a chart.\n6️⃣ Enter your License in the on-chart panel and press CONNECT & ACTIVATE.\n7️⃣ CONNECTED / WAITING FOR SIGNAL means setup is complete."),parse_mode=ParseMode.HTML)


@router.callback_query(F.data == "autotrade_download_mt5")
async def autotrade_download_mt5(cb: CallbackQuery, bot: Bot):
    if not await gated(cb,bot): return
    lang=get_lang(cb.from_user.id); await cb.answer()
    try:
        await _send_mt5_installer_and_help(bot,cb.from_user.id)
    except Exception as exc:
        log.exception("manual MT5 installer delivery failed")
        await bot.send_message(cb.from_user.id,tr(lang,"❌ فایل نصب فعلاً در دسترس نیست. با پشتیبانی تماس بگیرید.","❌ The installer is temporarily unavailable. Contact support."))
    await push_home_to_bottom(bot,cb.from_user.id)


@router.callback_query(F.data == "autotrade_install_help")
async def autotrade_install_help(cb: CallbackQuery, bot: Bot):
    if not await gated(cb,bot): return
    lang=get_lang(cb.from_user.id); await cb.answer()
    text=tr(lang,
        "<b>📘 راهنمای نصب NEXUS معاملات خودکار</b>\n\nاین بخش چیست؟ آموزش نصب و فعال‌سازی اکسپرت روی MT5.\n\n1️⃣ فایل EX5 را دریافت کنید.\n2️⃣ MT5 → File → Open Data Folder → MQL5 → Experts.\n3️⃣ فایل را کپی و MT5 را راه‌اندازی مجدد کنید.\n4️⃣ معاملات الگوریتمی را فعال کنید.\n5️⃣ اکسپرت را روی نمودار قرار دهید.\n6️⃣ مجوز را وارد و اتصال و فعال‌سازی را بزنید.\n\nقدم بعدی: پس از نمایش «در انتظار سیگنال»، سیستم آماده است.",
        "<b>📘 NEXUS Auto Trade Installation</b>\n\nWhat is this? Step-by-step MT5 installation and activation.\n\n1️⃣ Get the EX5 file.\n2️⃣ MT5 → File → Open Data Folder → MQL5 → Experts.\n3️⃣ Copy the file and restart MT5.\n4️⃣ Enable Algo Trading.\n5️⃣ Attach the EA to a chart.\n6️⃣ Enter License and press CONNECT & ACTIVATE.\n\nNext step: WAITING FOR SIGNAL means the system is ready.")
    await screen(bot,cb.from_user.id,cb.message.chat.id,text,autotrade_user_menu(lang))


@router.callback_query(F.data == "autotrade_video_guide")
async def autotrade_video_guide(cb: CallbackQuery, bot: Bot):
    if not await gated(cb,bot): return
    lang=get_lang(cb.from_user.id); await cb.answer()
    local_video=Path(__file__).resolve().parent.parent / "assets" / "guides" / "NEXUS_AutoTrade_MT5_Guide.mp4"
    if local_video.is_file():
        await bot.send_video(
            cb.from_user.id,
            BufferedInputFile(local_video.read_bytes(),filename="NEXUS_AutoTrade_MT5_Guide.mp4"),
            caption=tr(lang,"🎥 راهنمای تصویری نصب و فعال‌سازی NEXUS معاملات خودکار","🎥 NEXUS Auto Trade installation and activation video"),
            protect_content=True,
        )
        await bot.send_message(
            cb.from_user.id,
            tr(lang,
               "<b>🎓 راهنمای NEXUS</b>\n\nبرای ادامه یکی از گزینه‌ها را انتخاب کنید.",
               "<b>🎓 NEXUS Guide</b>\n\nChoose another guide or return to Auto Trade."),
            parse_mode=ParseMode.HTML,
            reply_markup=autotrade_user_menu(lang, mt5_connected=bool(db.mt5_account(cb.from_user.id)), exchange_connected=bool(db.exchange_account(cb.from_user.id))),
        )
        return
    if settings.guide_mt5_video_url:
        markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=tr(lang,"▶️ مشاهده کلیپ راهنما","▶️ Watch Video Guide"),url=settings.guide_mt5_video_url)],
            [InlineKeyboardButton(text=tr(lang,"⬅️ بازگشت","⬅️ Back"),callback_data="client_autotrade_access")],
        ])
        text=tr(lang,
                "<b>🎥 راهنمای تصویری</b>\n\nدر این کلیپ مراحل خرید، نصب اکسپرت، وارد کردن مجوز و فعال‌سازی روی MT5 را قدم‌به‌قدم مشاهده می‌کنید.",
                "<b>🎥 Video Guide</b>\n\nThis video walks through purchase, EA installation, License entry and MT5 activation.")
    else:
        markup=autotrade_user_menu(lang, mt5_connected=bool(db.mt5_account(cb.from_user.id)), exchange_connected=bool(db.exchange_account(cb.from_user.id)))
        text=tr(lang,
                "<b>🎥 راهنمای تصویری</b>\n\nفایل <code>NEXUS_AutoTrade_MT5_Guide.mp4</code> را دقیقاً در <code>assets/guides</code> قرار دهید؛ یا GUIDE_MT5_VIDEO_URL را در .env تنظیم کنید.",
                "<b>🎥 Video Guide</b>\n\nPlace <code>NEXUS_AutoTrade_MT5_Guide.mp4</code> exactly in <code>assets/guides</code>, or set GUIDE_MT5_VIDEO_URL in .env.")
    await screen(bot,cb.from_user.id,cb.message.chat.id,text,markup)


@router.callback_query(F.data == "autotrade_help")
async def autotrade_help(cb: CallbackQuery, bot: Bot):
    if not await gated(cb,bot): return
    lang=get_lang(cb.from_user.id); await cb.answer()
    text=tr(lang,
        "<b>🆘 معاملات خودکار چیست؟</b>\n\nمعاملات خودکار سیگنال‌های NEXUS را از Backend دریافت می‌کند، ورود را بررسی می‌کند و در صورت معتبر بودن معامله را اجرا می‌کند. SL، TP، سر‌به‌سر، بستن بخشی، حدضرر متحرک و خروج زودهنگام ادمین نیز بر اساس همان سیگنال ID اجرا می‌شوند.\n\n🔒 حدضرر متحرک و روش حجم برای هر سیگنال توسط ادمین NEXUS تعیین می‌شود و برای حفظ یکپارچگی استراتژی در حالت قفل‌شده NEXUS اجرا خواهد شد.",
        "<b>🆘 What is Auto Trade?</b>\n\nAuto Trade receives NEXUS signals from the Backend, validates entry conditions and executes valid trades. SL, TP, Break Even, Partial Close, Trailing and admin early-exit commands are applied to the same Signal ID.\n\n🔒 Trailing and sizing mode are selected by the NEXUS admin and run in NEXUS LOCKED mode for strategy consistency.")
    await screen(bot,cb.from_user.id,cb.message.chat.id,text,autotrade_user_menu(lang))


@router.callback_query(F.data == "autotrade_exchange")
async def autotrade_exchange(cb: CallbackQuery, bot: Bot, state: FSMContext):
    if not await gated(cb,bot): return
    lang=get_lang(cb.from_user.id); await cb.answer(); exch=db.exchange_account(cb.from_user.id)
    if exch and str(exch["status"]).lower()=="connected":
        name=SUPPORTED_EXCHANGES.get(str(exch["exchange"]).lower(), str(exch["exchange"]))
        text=tr(lang,
            f"<b>₿ اتصال صرافی Auto Trade</b>\n\nوضعیت: 🟢 <b>CONNECTED</b>\nصرافی: <b>{escape(name)}</b>\nحساب: <code>{escape(str(exch['account_label'] or 'authenticated'))}</code>\n\nکلیدهای API به‌صورت رمزنگاری‌شده روی Backend ذخیره می‌شوند. NEXUS فقط از مسیرهای معاملاتی Connector استفاده می‌کند و هیچ عملیات برداشت انجام نمی‌دهد.\n\nبرای تست مجدد یا قطع اتصال از دکمه‌های زیر استفاده کنید.",
            f"<b>₿ Exchange Auto Trade</b>\n\nStatus: 🟢 <b>CONNECTED</b>\nExchange: <b>{escape(name)}</b>\nAccount: <code>{escape(str(exch['account_label'] or 'authenticated'))}</code>\n\nAPI credentials are encrypted on the Backend. NEXUS uses trading connector methods only and never performs withdrawals.\n\nUse the buttons below to retest or disconnect.")
        await screen(bot,cb.from_user.id,cb.message.chat.id,text,exchange_connected_menu(lang)); return

    text=tr(lang,
        "<b>₿ اتصال صرافی معاملات خودکار</b>\n\nاین بخش چیست؟ اتصال امن حساب صرافی به مجوز معاملات خودکار شما.\n\n1️⃣ در صرافی یک کلید API مخصوص معاملات بسازید.\n2️⃣ مجوز برداشت را فعال نکنید.\n3️⃣ صرافی را از لیست زیر انتخاب کنید.\n4️⃣ کلید API و کلید محرمانه را در مراحل بعد ارسال کنید. پیام حاوی کلید بعد از خواندن توسط ربات حذف می‌شود.\n5️⃣ سامانه اتصال را با درخواست احراز هویت تست و سپس اطلاعات را رمزنگاری می‌کند.\n\n⚠️ اتصال صرافی واقعی است؛ اجرای خودکار سفارش‌های رمزارزی هنوز باید جداگانه در موتور اجرای معاملات صرافی فعال شود.",
        "<b>₿ Exchange Auto Trade Connection</b>\n\nWhat is this? Securely bind one exchange account to your Auto Trade License.\n\n1️⃣ Create a Trading API key on the exchange.\n2️⃣ Do not enable Withdrawal.\n3️⃣ Choose the exchange below.\n4️⃣ Send API Key and Secret in the next steps. The bot deletes credential messages after reading them.\n5️⃣ The Backend authenticates the connection and stores credentials encrypted.\n\n⚠️ The exchange connection is live; automatic Crypto order execution remains a separate Exchange Execution Engine feature.")
    await state.clear()
    await screen(bot,cb.from_user.id,cb.message.chat.id,text,exchange_select_menu(lang))


@router.callback_query(F.data.startswith("exchange_select:"))
async def exchange_select(cb: CallbackQuery, bot: Bot, state: FSMContext):
    if not await gated(cb,bot): return
    lang=get_lang(cb.from_user.id); await cb.answer()
    exchange_id=cb.data.split(":",1)[1].strip().lower()
    if exchange_id not in SUPPORTED_EXCHANGES:
        await cb.answer(tr(lang,"صرافی پشتیبانی نمی‌شود.","Exchange is not supported."),show_alert=True); return
    if not settings.exchange_credentials_key:
        text=tr(lang,
            "<b>⚠️ تنظیم امنیت صرافی کامل نیست</b>\n\nروی سرور هنوز <code>EXCHANGE_CREDENTIALS_KEY</code> تنظیم نشده است. قبل از دریافت API کاربران یک Fernet Key در .env قرار دهید.",
            "<b>⚠️ Exchange security is not configured</b>\n\n<code>EXCHANGE_CREDENTIALS_KEY</code> is missing on the server. Configure a Fernet key in .env before collecting user APIs.")
        await screen(bot,cb.from_user.id,cb.message.chat.id,text,exchange_select_menu(lang)); return
    await state.update_data(exchange_id=exchange_id)
    await state.set_state(Flow.exchange_api_key)
    await screen(bot,cb.from_user.id,cb.message.chat.id,
        tr(lang,
           f"<b>₿ {escape(SUPPORTED_EXCHANGES[exchange_id])}</b>\n\nAPI Key را ارسال کنید.\n\n🔐 پیام شما بعد از خواندن حذف می‌شود.",
           f"<b>₿ {escape(SUPPORTED_EXCHANGES[exchange_id])}</b>\n\nSend your API Key.\n\n🔐 Your credential message will be deleted after reading."),
        kb(nav(lang,"autotrade_exchange")))


async def _delete_credential_message(message: Message):
    try:
        await message.delete()
    except Exception:
        pass


@router.message(Flow.exchange_api_key)
async def exchange_api_key_input(message: Message, state: FSMContext, bot: Bot):
    lang=get_lang(message.from_user.id); value=(message.text or "").strip(); await _delete_credential_message(message)
    if len(value)<6:
        await bot.send_message(message.from_user.id,tr(lang,"API Key معتبر نیست؛ دوباره ارسال کنید.","API Key looks invalid; send it again.")); return
    await state.update_data(exchange_api_key=value); await state.set_state(Flow.exchange_api_secret)
    await bot.send_message(message.from_user.id,tr(lang,"🔐 اکنون API Secret را ارسال کنید. این پیام هم بعد از خواندن حذف می‌شود.","🔐 Now send the API Secret. This message will also be deleted after reading."))


@router.message(Flow.exchange_api_secret)
async def exchange_api_secret_input(message: Message, state: FSMContext, bot: Bot):
    lang=get_lang(message.from_user.id); value=(message.text or "").strip(); await _delete_credential_message(message)
    if len(value)<6:
        await bot.send_message(message.from_user.id,tr(lang,"API Secret معتبر نیست؛ دوباره ارسال کنید.","API Secret looks invalid; send it again.")); return
    await state.update_data(exchange_api_secret=value); await state.set_state(Flow.exchange_api_passphrase)
    await bot.send_message(message.from_user.id,tr(lang,"اگر صرافی شما Passphrase/Password API دارد آن را ارسال کنید؛ در غیر این صورت فقط <code>-</code> بفرستید.","If your exchange API uses a Passphrase/Password, send it now; otherwise send <code>-</code>."),parse_mode=ParseMode.HTML)


@router.message(Flow.exchange_api_passphrase)
async def exchange_api_passphrase_input(message: Message, state: FSMContext, bot: Bot):
    lang=get_lang(message.from_user.id); passphrase=(message.text or "").strip(); await _delete_credential_message(message)
    if passphrase=="-": passphrase=""
    data=await state.get_data(); exchange_id=str(data.get("exchange_id") or ""); api_key=str(data.get("exchange_api_key") or ""); api_secret=str(data.get("exchange_api_secret") or "")
    await state.clear()
    wait=await bot.send_message(message.from_user.id,tr(lang,"⏳ در حال تست اتصال امن صرافی...","⏳ Testing secure exchange connection..."))
    try:
        result=await asyncio.to_thread(test_exchange_connection,exchange_id,api_key,api_secret,passphrase,default_type=settings.exchange_default_market_type)
        key_enc,secret_enc,pass_enc=encrypt_credentials(api_key,api_secret,passphrase,encryption_key=settings.exchange_credentials_key)
        db.save_exchange_account(message.from_user.id,exchange_id,key_enc,secret_enc,pass_enc,account_label=result.account_label,status="connected")
        text=tr(lang,
            f"✅ <b>اتصال صرافی برقرار شد</b>\n\nصرافی: <b>{escape(result.exchange_name)}</b>\nوضعیت: <b>CONNECTED</b>\nMarkets: <b>{result.market_count}</b>\n\nکلیدها رمزنگاری و ذخیره شدند. جزئیات اتصال را از بخش وضعیت Auto Trade مشاهده کنید.",
            f"✅ <b>Exchange connected</b>\n\nExchange: <b>{escape(result.exchange_name)}</b>\nStatus: <b>CONNECTED</b>\nMarkets: <b>{result.market_count}</b>\n\nCredentials were encrypted and stored. Open Auto Trade Status for connection details.")
    except Exception as exc:
        text=tr(lang,
            f"❌ <b>اتصال صرافی ناموفق بود</b>\n\nعلت: <code>{escape(str(exc)[:800])}</code>\n\nAPI، IP whitelist و Permissionهای Trading را بررسی و دوباره تلاش کنید.",
            f"❌ <b>Exchange connection failed</b>\n\nReason: <code>{escape(str(exc)[:800])}</code>\n\nCheck API credentials, IP whitelist and Trading permissions, then retry.")
    try: await bot.delete_message(wait.chat.id,wait.message_id)
    except Exception: pass
    await bot.send_message(message.from_user.id,text,parse_mode=ParseMode.HTML,reply_markup=autotrade_user_menu(lang,mt5_connected=bool(db.mt5_account(message.from_user.id)),exchange_connected=bool(db.exchange_account(message.from_user.id))))


@router.callback_query(F.data == "exchange_disconnect")
async def exchange_disconnect(cb: CallbackQuery, bot: Bot):
    if not await gated(cb,bot): return
    lang=get_lang(cb.from_user.id); db.disconnect_exchange_account(cb.from_user.id)
    await cb.answer(tr(lang,"اتصال صرافی حذف شد.","Exchange disconnected."),show_alert=True)
    await screen(bot,cb.from_user.id,cb.message.chat.id,
                 tr(lang,"₿ اتصال صرافی حذف شد. برای اتصال مجدد صرافی را انتخاب کنید.","₿ Exchange disconnected. Choose an exchange to reconnect."),
                 exchange_select_menu(lang))


@router.callback_query(F.data == "exchange_retest")
async def exchange_retest(cb: CallbackQuery, bot: Bot):
    if not await gated(cb,bot): return
    lang=get_lang(cb.from_user.id); exch=db.exchange_account(cb.from_user.id); await cb.answer()
    if not exch:
        await screen(bot,cb.from_user.id,cb.message.chat.id,tr(lang,"اتصال صرافی پیدا نشد.","No exchange connection found."),exchange_select_menu(lang)); return
    try:
        api_key,api_secret,passphrase=decrypt_credentials(exch,encryption_key=settings.exchange_credentials_key)
        result=await asyncio.to_thread(test_exchange_connection,str(exch["exchange"]),api_key,api_secret,passphrase,default_type=settings.exchange_default_market_type)
        text=tr(lang,f"✅ اتصال {escape(result.exchange_name)} سالم است.",f"✅ {escape(result.exchange_name)} connection is healthy.")
    except Exception as exc:
        text=tr(lang,f"❌ تست اتصال ناموفق: <code>{escape(str(exc)[:800])}</code>",f"❌ Retest failed: <code>{escape(str(exc)[:800])}</code>")
    await screen(bot,cb.from_user.id,cb.message.chat.id,text,exchange_connected_menu(lang))


@router.callback_query(F.data == "public")
async def public_channel(cb: CallbackQuery, bot: Bot):
    if not await gated(cb, bot): return
    lang = get_lang(cb.from_user.id); await cb.answer()
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=tr(lang, "📣 ورود به کانال عمومی", "📣 Open Public Channel"), url=settings.public_channel_url)],
        [InlineKeyboardButton(text=tr(lang, "⬅️ بازگشت", "⬅️ Back"), callback_data="main"), InlineKeyboardButton(text=tr(lang, "🏠 منوی اصلی", "🏠 Main Menu"), callback_data="main")],
    ])
    await screen(bot, cb.from_user.id, cb.message.chat.id, tr(lang, "<b>کانال عمومی NEXUS</b>\n\nتحلیل‌ها، آموزش‌ها و اطلاعیه‌های رسمی NEXUS.", "<b>NEXUS Public Channel</b>\n\nOfficial analysis, education and NEXUS announcements."), markup)


@router.callback_query(F.data == "free")
async def free_channel(cb: CallbackQuery, bot: Bot):
    if not await gated(cb, bot): return
    lang = get_lang(cb.from_user.id); await cb.answer()
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=tr(lang, "🎯 ورود به کانال سیگنال رایگان", "🎯 Open Free Signal Channel"), url=settings.free_channel_url)],
        [InlineKeyboardButton(text=tr(lang, "⬅️ بازگشت", "⬅️ Back"), callback_data="main"), InlineKeyboardButton(text=tr(lang, "🏠 منوی اصلی", "🏠 Main Menu"), callback_data="main")],
    ])
    await screen(bot, cb.from_user.id, cb.message.chat.id, tr(lang, "<b>سیگنال رایگان NEXUS</b>\n\nبرای مشاهده کانال روی دکمه زیر بزنید.", "<b>NEXUS Free Signals</b>\n\nTap the button below to open the channel."), markup)


@router.callback_query(F.data == "autotrade")
async def autotrade(cb: CallbackQuery, bot: Bot):
    if not await gated(cb, bot): return
    lang = get_lang(cb.from_user.id)
    if not license_service.has_autotrade(cb.from_user.id):
        await cb.answer(tr(lang, "ابتدا اشتراک دارای معاملات خودکار تهیه کنید.", "Buy a plan with Auto Trade access first."), show_alert=True)
        await screen(bot, cb.from_user.id, cb.message.chat.id,
                     tr(lang, "برای دسترسی به سیگنال + اتوترید ابتدا اشتراک تهیه کنید.", "Buy a subscription to access Signals + Auto Trade."),
                     kb([[(("💎 خرید اشتراک" if lang=="fa" else "💎 Buy Subscription"), "vip")]] + nav(lang, "client_signals")))
        return
    await cb.answer()
    text = tr(
        lang,
        "<b>🤖 NEXUS AUTO TRADE</b>\n\nسیستم معاملات خودکار نکسوس در حال توسعه است و به‌زودی ارائه می‌شود.\n\nاین سرویس معاملات تأییدشده NEXUS را روی حساب معاملاتی کاربر اجرا می‌کند و ورود، خروج، مدیریت پوزیشن و مدیریت ریسک را خودکار می‌سازد.\n\n🚧 <b>در حال آماده‌سازی — به‌زودی</b>",
        "<b>🤖 NEXUS AUTO TRADE</b>\n\nNEXUS Auto Trade is under development and will be released soon.\n\nIt is designed to execute approved NEXUS trades on the user's trading account and automate entries, exits, position handling and risk management.\n\n🚧 <b>Coming Soon</b>",
    )
    joined = db.is_on_autotrade_waitlist(cb.from_user.id)
    await screen(bot, cb.from_user.id, cb.message.chat.id, text, autotrade_waitlist_menu(lang, joined))


@router.callback_query(F.data == "autotrade_waitlist_join")
async def autotrade_waitlist_join(cb: CallbackQuery, bot: Bot):
    if not await gated(cb, bot): return
    lang=get_lang(cb.from_user.id); db.join_autotrade_waitlist(cb.from_user.id); await cb.answer(tr(lang,"به لیست انتظار اضافه شدید ✅","Added to the waitlist ✅"),show_alert=True)
    await autotrade(cb,bot)


@router.callback_query(F.data == "autotrade_waitlist_leave")
async def autotrade_waitlist_leave(cb: CallbackQuery, bot: Bot):
    lang=get_lang(cb.from_user.id); db.leave_autotrade_waitlist(cb.from_user.id); await cb.answer(tr(lang,"از لیست انتظار خارج شدید.","Removed from the waitlist."),show_alert=True)
    await autotrade(cb,bot)


@router.callback_query(F.data == "noop")
async def noop(cb: CallbackQuery):
    await cb.answer()


@router.callback_query(F.data == "referral")
async def referral(cb: CallbackQuery, bot: Bot):
    if not await gated(cb, bot): return
    lang = get_lang(cb.from_user.id); await cb.answer()
    user = db.get_user(cb.from_user.id)
    stats = db.referral_stats(cb.from_user.id)
    reward = int(db.get_setting("referral_points_per_success", "100"))
    rate = int(db.get_setting("points_per_percent", "100"))
    cap = int(db.get_setting("max_points_discount_percent", "30"))
    code = user["referral_code"]
    link = f"https://t.me/{BOT_USERNAME}?start=ref_{code}" if BOT_USERNAME else f"ref_{code}"
    text = tr(
        lang,
        f"<b>⭐ دعوت و امتیاز NEXUS</b>\n\nکد شما: <code>{escape(code)}</code>\nلینک اختصاصی:\n<code>{escape(link)}</code>\n\n👥 دعوت‌شده‌ها: <b>{stats['invited']}</b>\n✅ دعوت موفق: <b>{stats['successful']}</b>\n⭐ موجودی: <b>{stats['points']} امتیاز</b>\n\n🎁 پاداش هر دعوت موفق: <b>{reward} امتیاز</b>\n📐 هر <b>{rate}</b> امتیاز = <b>۱٪ تخفیف</b>\n🛡 سقف تخفیف امتیازی هر خرید: <b>{cap}٪</b>\n\nامتیاز فقط زمانی داده می‌شود که فرد دعوت‌شده از لینک شما وارد ربات شود و عضویت اجباری کانال عمومی را تأیید کند.",
        f"<b>⭐ Referral & NEXUS Points</b>\n\nYour code: <code>{escape(code)}</code>\nReferral link:\n<code>{escape(link)}</code>\n\n👥 Invited: <b>{stats['invited']}</b>\n✅ Successful referrals: <b>{stats['successful']}</b>\n⭐ Balance: <b>{stats['points']} Points</b>\n\n🎁 Reward per successful referral: <b>{reward} points</b>\n📐 Every <b>{rate}</b> points = <b>1% discount</b>\n🛡 Points-discount cap per purchase: <b>{cap}%</b>\n\nPoints are awarded only after the referred person enters through your link and confirms mandatory public-channel membership.",
    )
    await screen(bot, cb.from_user.id, cb.message.chat.id, text, referral_menu(lang, link))


@router.callback_query(F.data == "vip")
async def vip(cb: CallbackQuery, bot: Bot, state: FSMContext):
    if not await gated(cb, bot):
        return
    await state.clear()
    lang = get_lang(cb.from_user.id)
    await cb.answer()
    access = license_service.snapshot(cb.from_user.id)
    plans_map = db.plan_map(active_only=True) or settings.plans

    # The subscription page is intentionally the single purchase entry point.
    # It shows exactly three commercial products; durations/prices are selected afterwards.
    lines_fa = [
        "<b>💎 خرید اشتراک NEXUS</b>",
        "",
        "سه سرویس اصلی را می‌توانید انتخاب کنید:",
        "",
        "📊 <b>VIP</b> — دسترسی به کانال و سیگنال‌های VIP",
        "🤖 <b>AutoTrade Expert</b> — اجرای خودکار معاملات",
        "⭐ <b>VIP + AutoTrade Expert</b> — پکیج کامل",
        "",
        f"وضعیت فعلی: VIP <b>{'فعال' if access.vip else 'غیرفعال'}</b> | AutoTrade Expert <b>{'فعال' if access.autotrade else 'غیرفعال'}</b>",
        "",
        "پس از انتخاب سرویس، مدت و قیمت از پلن‌های فعال پنل مدیریت نمایش داده می‌شود.",
        "💳 پرداخت با تتر یا ریال امکان‌پذیر است.",
    ]
    lines_en = [
        "<b>💎 NEXUS Subscription</b>",
        "",
        "Choose one of the three services:",
        "",
        "📊 <b>VIP</b> — VIP channel and signals",
        "🤖 <b>AutoTrade Expert</b> — automatic trade execution",
        "⭐ <b>VIP + AutoTrade Expert</b> — complete package",
        "",
        f"Current status: VIP <b>{'Active' if access.vip else 'Inactive'}</b> | AutoTrade Expert <b>{'Active' if access.autotrade else 'Inactive'}</b>",
        "",
        "After selecting a service, active durations and prices are loaded from Plan Management.",
        "💳 Pay with USDT or IRR.",
    ]
    text = tr(lang, "\n".join(lines_fa), "\n".join(lines_en))
    await screen(bot, cb.from_user.id, cb.message.chat.id, text, subscription_service_menu(lang, access.vip, access.autotrade))


@router.callback_query(F.data.startswith("buyservice:"))
async def buyservice(cb: CallbackQuery, bot: Bot):
    if not await gated(cb, bot):
        return
    lang = get_lang(cb.from_user.id)
    service = cb.data.split(":", 1)[1].upper()
    access = license_service.snapshot(cb.from_user.id)
    await cb.answer()

    if service not in {"VIP", "AUTO", "BUNDLE"}:
        await cb.answer(tr(lang, "سرویس نامعتبر است.", "Invalid service."), show_alert=True)
        return

    menu = plans_for_service(lang, service)
    count = sum(1 for row in menu.inline_keyboard for b in row if (b.callback_data or "").startswith("plan:"))
    labels = {
        "VIP": ("📊 VIP", "VIP"),
        "AUTO": ("🤖 AutoTrade Expert", "AutoTrade Expert"),
        "BUNDLE": ("⭐ VIP + AutoTrade Expert", "VIP + AutoTrade Expert"),
    }
    fa_label, en_label = labels[service]
    if count == 0:
        msg = tr(
            lang,
            f"<b>{fa_label}</b>\n\nبرای این سرویس هنوز پلن قیمت‌گذاری‌شده فعالی وجود ندارد. ادمین باید مدت و قیمت آن را در بخش مدیریت پلن‌ها تنظیم کند.",
            f"<b>{en_label}</b>\n\nNo active priced plan is available for this service yet. An admin must configure its duration and price in Plan Management.",
        )
    else:
        context_fa = ""
        context_en = ""
        if service == "AUTO" and access.vip and not access.autotrade:
            context_fa = "\n\n📌 اشتراک VIP شما حفظ می‌شود و AutoTrade Expert به‌صورت مستقل به آن اضافه خواهد شد."
            context_en = "\n\n📌 Your VIP subscription remains active; AutoTrade Expert will be added independently."
        elif service == "VIP" and access.autotrade and not access.vip:
            context_fa = "\n\n📌 AutoTrade Expert شما حفظ می‌شود و VIP به‌صورت مستقل اضافه خواهد شد."
            context_en = "\n\n📌 Your AutoTrade Expert access remains active; VIP will be added independently."
        elif service == "BUNDLE" and (access.vip or access.autotrade):
            context_fa = "\n\n⬆️ این خرید به‌عنوان ارتقای اشتراک محاسبه می‌شود و اعتبار سرویس موجود در قیمت لحاظ خواهد شد."
            context_en = "\n\n⬆️ This purchase is treated as an upgrade; eligible existing service value is included in the quote."
        msg = tr(lang, f"<b>{fa_label}</b>{context_fa}\n\nمدت اشتراک را انتخاب کنید.", f"<b>{en_label}</b>{context_en}\n\nChoose a subscription duration.")
    await screen(bot, cb.from_user.id, cb.message.chat.id, msg, menu)


@router.callback_query(F.data.startswith("plan:"))
async def select_plan(cb: CallbackQuery, bot: Bot, state: FSMContext):
    if not await gated(cb, bot): return
    lang = get_lang(cb.from_user.id)
    code = cb.data.split(":", 1)[1]
    plan = _plans().get(code)
    if not plan:
        await cb.answer(tr(lang, "پلن نامعتبر است.", "Invalid plan."), show_alert=True); return
    await state.clear()
    await state.update_data(plan_code=code, discount_percent=0.0, promo_code=None, promo_id=None, points_used=0, campaign_id=None)
    info = db.points_discount_info(cb.from_user.id)
    await cb.answer()
    campaign = db.best_campaign(cb.from_user.id, code)
    campaign_line = ""
    active_access = license_service.snapshot(cb.from_user.id)
    renewal_pct = float(plan.get("renewal_discount_percent", 0) or 0) if active_access.active else 0.0
    markup = plan_options(lang, code, info["possible_percent"] > 0, renewal_pct)
    if campaign:
        campaign_line = tr(lang, f"\n🎯 کمپین فعال: <b>{escape(campaign['title_fa'])}</b> — <b>{campaign['percent']:g}٪</b>", f"\n🎯 Active campaign: <b>{escape(campaign['title_en'])}</b> — <b>{campaign['percent']:g}%</b>")
        rows = list(markup.inline_keyboard)
        rows.insert(0, [InlineKeyboardButton(text=tr(lang, f"🎯 استفاده از کمپین {campaign['percent']:g}٪", f"🎯 Apply {campaign['percent']:g}% Campaign"), callback_data=f"discount:campaign:{code}:{campaign['id']}")])
        markup = InlineKeyboardMarkup(inline_keyboard=rows)
    access_label = license_service.plan_access_label(db.get_plan(code), lang)
    plan_vip = bool(plan.get("vip_access", True)); plan_auto = bool(plan.get("autotrade_access", True))
    if not active_access.active:
        purchase_kind_fa, purchase_kind_en = "خرید جدید", "New subscription"
    elif (plan_vip and not active_access.vip) or (plan_auto and not active_access.autotrade):
        purchase_kind_fa, purchase_kind_en = "ارتقای اشتراک", "Subscription upgrade"
    else:
        purchase_kind_fa, purchase_kind_en = "تمدید اشتراک", "Subscription renewal"
    renewal_line = tr(lang, f"\n🔁 تخفیف تمدید: <b>{renewal_pct:g}٪</b>" if renewal_pct else "", f"\n🔁 Renewal discount: <b>{renewal_pct:g}%</b>" if renewal_pct else "")
    text = tr(
        lang,
        f"<b>{escape(str(plan['fa']))}</b>\n\nنوع: <b>{purchase_kind_fa}</b>\nقیمت: <b>{escape(str(plan.get('usdt', plan.get('price_usdt','0'))))} USDT</b>\nدسترسی: <b>{escape(access_label)}</b>\nامتیاز: <b>{info['points']}</b>{renewal_line}{campaign_line}\n\nروش تخفیف را انتخاب کنید.",
        f"<b>{escape(str(plan['en']))}</b>\n\nType: <b>{purchase_kind_en}</b>\nPrice: <b>{escape(str(plan.get('usdt', plan.get('price_usdt','0'))))} USDT</b>\nAccess: <b>{escape(access_label)}</b>\nPoints: <b>{info['points']}</b>{renewal_line}{campaign_line}\n\nChoose a discount option.",
    )
    await screen(bot, cb.from_user.id, cb.message.chat.id, text, markup)


async def show_payment_methods(cb: CallbackQuery, bot: Bot, state: FSMContext, code: str):
    lang = get_lang(cb.from_user.id)
    data = await state.get_data()
    plan = _plans()[code]
    pct = float(data.get("discount_percent", 0) or 0)
    try:
        quote = pricing_service.quote_purchase(cb.from_user.id, code, pricing_service.Decimal(str(pct)))
    except Exception as exc:
        await screen(bot, cb.from_user.id, cb.message.chat.id, tr(lang, f"❌ قیمت‌گذاری قابل محاسبه نیست: {escape(str(exc))}", f"❌ Pricing is unavailable: {escape(str(exc))}"), kb(nav(lang, f"plan:{code}")))
        return
    setup_line = f"\n⚙️ هزینه فعال‌سازی: <b>{quote['setup_fee_usdt']:g} USDT</b>" if quote["setup_fee_usdt"] else ""
    credit_line = f"\n🎁 اعتبار باقی‌مانده: <b>{quote['upgrade_credit_usdt']:g} USDT</b>" if quote["upgrade_credit_usdt"] else ""
    text = tr(
        lang,
        f"<b>{escape(str(plan['fa']))}</b>\n\n💰 قیمت سرویس: <b>{quote['base_usdt']:g} USDT</b>{setup_line}{credit_line}\n<b>مبلغ نهایی: {quote['total_usdt']:g} USDT</b>\n\nروش پرداخت را انتخاب کنید:",
        f"<b>{escape(str(plan['en']))}</b>\n\n💰 Service price: <b>{quote['base_usdt']:g} USDT</b>{setup_line}{credit_line}\n<b>Final amount: {quote['total_usdt']:g} USDT</b>\n\nChoose a payment method:",
    )
    await screen(bot, cb.from_user.id, cb.message.chat.id, text, payment_method(lang, code))


@router.callback_query(F.data.startswith("discount:none:"))
async def discount_none(cb: CallbackQuery, bot: Bot, state: FSMContext):
    code = cb.data.rsplit(":", 1)[1]
    await state.update_data(plan_code=code, discount_percent=0.0, promo_code=None, promo_id=None, points_used=0, campaign_id=None)
    await cb.answer()
    await show_payment_methods(cb, bot, state, code)


@router.callback_query(F.data.startswith("discount:renewal:"))
async def discount_renewal(cb: CallbackQuery, bot: Bot, state: FSMContext):
    code = cb.data.rsplit(":", 1)[1]
    lang = get_lang(cb.from_user.id)
    plan = _plans().get(code)
    if not plan or not license_service.snapshot(cb.from_user.id).active:
        await cb.answer(tr(lang, "تخفیف تمدید برای شما فعال نیست.", "Renewal discount is not available."), show_alert=True)
        return
    pct = float(plan.get("renewal_discount_percent", 0) or 0)
    if pct <= 0:
        await cb.answer(tr(lang, "تخفیف تمدید این پلن فعال نیست.", "This plan has no renewal discount."), show_alert=True)
        return
    await state.update_data(plan_code=code, discount_percent=pct, promo_code=None, promo_id=None, points_used=0, campaign_id=None)
    await cb.answer(tr(lang, f"تخفیف تمدید {pct:g}٪ اعمال شد ✅", f"{pct:g}% renewal discount applied ✅"), show_alert=True)
    await show_payment_methods(cb, bot, state, code)


@router.callback_query(F.data.startswith("discount:promo:"))
async def discount_promo(cb: CallbackQuery, bot: Bot, state: FSMContext):
    code = cb.data.rsplit(":", 1)[1]
    lang = get_lang(cb.from_user.id)
    await state.set_state(Flow.waiting_promo)
    await state.update_data(plan_code=code, discount_percent=0.0, promo_code=None, promo_id=None, points_used=0, campaign_id=None)
    await cb.answer()
    await screen(bot, cb.from_user.id, cb.message.chat.id, tr(lang, "<b>🎟 کد تخفیف</b>\n\nکد تخفیف را ارسال کنید.", "<b>🎟 Promo Code</b>\n\nSend your promo code."), kb(nav(lang, f"plan:{code}")))


@router.message(Flow.waiting_promo)
async def receive_promo(message: Message, bot: Bot, state: FSMContext):
    db.upsert_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    lang = get_lang(message.from_user.id)
    code_text = (message.text or "").strip().upper()
    await clean_user_message(message)
    data = await state.get_data(); plan_code = data.get("plan_code")
    catalog = _plans(active_only=True)
    if not plan_code or str(plan_code) not in catalog:
        await state.clear()
        await screen(bot, message.from_user.id, message.chat.id, tr(lang, "❌ اطلاعات پلن از بین رفته یا پلن غیرفعال شده است. خرید را دوباره از منوی وی‌آی‌پی شروع کنید.", "❌ Plan data expired or the plan is inactive. Start the purchase again from the VIP menu."), kb(nav(lang, "vip")))
        return
    d = db.get_valid_discount(code_text, message.from_user.id) if code_text else None
    if not d:
        await screen(bot, message.from_user.id, message.chat.id, tr(lang, "❌ کد تخفیف نامعتبر، منقضی یا قبلاً استفاده شده است.", "❌ Promo code is invalid, expired, or already used."), kb(nav(lang, f"plan:{plan_code}")))
        return
    await state.set_state(None)
    await state.update_data(discount_percent=float(d["percent"]), promo_code=d["code"], promo_id=int(d["id"]), points_used=0)
    # Render directly because this is a message handler, not a callback.
    plan = catalog[str(plan_code)]
    pct = float(d["percent"])
    base_usdt = float(str(plan.get("usdt", plan.get("price_usdt", "0"))).replace(",",".")); final_usdt = round(base_usdt * (100-pct) / 100, 2)
    price_line = f"<s>{base_usdt:g} USDT</s> → <b>{final_usdt:g} USDT</b>"
    text = tr(lang, f"✅ کد <code>{escape(d['code'])}</code> اعمال شد.\nتخفیف: <b>{pct:g}٪</b>\nقیمت سرویس: {price_line}\n\nروش پرداخت را انتخاب کنید:", f"✅ Code <code>{escape(d['code'])}</code> applied.\nDiscount: <b>{pct:g}%</b>\nService price: {price_line}\n\nChoose a payment method:")
    await screen(bot, message.from_user.id, message.chat.id, text, payment_method(lang, str(plan_code)))


@router.callback_query(F.data.startswith("discount:points:"))
async def discount_points(cb: CallbackQuery, bot: Bot, state: FSMContext):
    code = cb.data.rsplit(":", 1)[1]
    lang = get_lang(cb.from_user.id)
    info = db.points_discount_info(cb.from_user.id)
    pct = info["possible_percent"]
    if pct <= 0:
        await cb.answer(tr(lang, "امتیاز کافی ندارید.", "You do not have enough points."), show_alert=True); return
    await state.update_data(plan_code=code, discount_percent=float(pct), promo_code=None, promo_id=None, points_used=int(info["points_needed"]), campaign_id=None)
    await cb.answer(tr(lang, f"{pct}٪ تخفیف امتیازی اعمال شد ⭐", f"{pct}% points discount applied ⭐"), show_alert=True)
    await show_payment_methods(cb, bot, state, code)


@router.callback_query(F.data.startswith("method:"))
async def select_method(cb: CallbackQuery, bot: Bot, state: FSMContext):
    if not await gated(cb, bot): return
    lang = get_lang(cb.from_user.id)
    _, code, method_raw = cb.data.split(":", 2)
    method = "rial" if method_raw == "irr" else method_raw
    plan = _plans().get(code)
    if not plan or method not in {"rial", "usdt"}:
        await cb.answer(tr(lang, "انتخاب نامعتبر است.", "Invalid selection."), show_alert=True); return
    if method == "usdt" and not _usdt_plan_ready(plan):
        await cb.answer(tr(lang, "پرداخت تتر هنوز کامل تنظیم نشده است.", "USDT payment is not fully configured."), show_alert=True); return
    data = await state.get_data()
    pct = float(data.get("discount_percent", 0) or 0)
    try:
        invoice = await pricing_service.create_invoice_quote(cb.from_user.id, code, method, pricing_service.Decimal(str(pct)))
    except Exception as exc:
        await cb.answer(tr(lang, f"خطا در ایجاد فاکتور: {exc}", f"Could not create invoice: {exc}"), show_alert=True); return
    await state.update_data(plan_code=code, payment_method=method, invoice_id=int(invoice["invoice_id"]))
    await cb.answer()
    expires = fmt_dt(invoice["expires_at"])
    if method == "rial":
        amount = f"{int(invoice['final_amount_rial']):,} ریال"
        text = tr(lang,
            f"<b>💳 فاکتور پرداخت ریالی</b>\n\nپلن: <b>{escape(str(plan['fa']))}</b>\nمبلغ مبنا: <b>{invoice['total_usdt']:g} USDT</b>\nنرخ لحظه‌ای USDT: <b>{invoice['usdt_rial_rate']:,} ریال</b>\nمبلغ نهایی: <b>{amount}</b>\n\nشماره کارت: <code>{escape(settings.payment_card)}</code>\nبه نام: <b>{escape(settings.payment_owner)}</b>\n\n⏳ اعتبار فاکتور تا: <b>{escape(expires)}</b>\nپس از پرداخت، تصویر رسید را ارسال کنید.",
            f"<b>💳 IRR Invoice</b>\n\nPlan: <b>{escape(str(plan['en']))}</b>\nBase amount: <b>{invoice['total_usdt']:g} USDT</b>\nLive USDT rate: <b>{invoice['usdt_rial_rate']:,} IRR</b>\nFinal amount: <b>{amount}</b>\n\nCard: <code>{escape(settings.payment_card)}</code>\nAccount name: <b>{escape(settings.payment_owner)}</b>\n\n⏳ Invoice valid until: <b>{escape(expires)}</b>\nAfter payment, send the receipt image.")
        await state.set_state(Flow.waiting_receipt)
    else:
        text = tr(lang,
            f"<b>₮ فاکتور پرداخت USDT</b>\n\nپلن: <b>{escape(str(plan['fa']))}</b>\nمبلغ نهایی: <b>{invoice['total_usdt']:g} USDT</b>\nشبکه: <b>{escape(settings.usdt_network)}</b>\nکیف پول:\n<code>{escape(settings.usdt_wallet)}</code>\n\n⏳ اعتبار فاکتور تا: <b>{escape(expires)}</b>\nابتدا TXID را ارسال کنید و سپس تصویر رسید را بفرستید.",
            f"<b>₮ USDT Invoice</b>\n\nPlan: <b>{escape(str(plan['en']))}</b>\nFinal amount: <b>{invoice['total_usdt']:g} USDT</b>\nNetwork: <b>{escape(settings.usdt_network)}</b>\nWallet:\n<code>{escape(settings.usdt_wallet)}</code>\n\n⏳ Invoice valid until: <b>{escape(expires)}</b>\nFirst send the TXID, then send the payment receipt.")
        await state.set_state(Flow.waiting_usdt_txid)
    await screen(bot, cb.from_user.id, cb.message.chat.id, text, kb(nav(lang, f"plan:{code}")))


# Backward compatibility for already-sent old inline buttons. New invoices do not use this callback.
@router.callback_query(F.data.startswith("receipt:"))
async def ask_receipt(cb: CallbackQuery, bot: Bot, state: FSMContext):
    if not await gated(cb, bot): return
    lang = get_lang(cb.from_user.id)
    _, code, method_raw = cb.data.split(":", 2)
    method = "rial" if method_raw == "irr" else method_raw
    if code not in _plans() or method not in {"rial", "usdt"}:
        await cb.answer(tr(lang, "انتخاب نامعتبر است.", "Invalid selection."), show_alert=True); return
    if method == "usdt" and not _usdt_plan_ready(_plans().get(code, {})):
        await cb.answer(tr(lang, "پرداخت تتر هنوز کامل تنظیم نشده است.", "USDT payment is not fully configured."), show_alert=True); return
    data = await state.get_data(); pct = float(data.get("discount_percent", 0) or 0)
    try:
        invoice = await pricing_service.create_invoice_quote(cb.from_user.id, code, method, pricing_service.Decimal(str(pct)))
    except Exception as exc:
        await cb.answer(str(exc), show_alert=True); return
    await state.update_data(plan_code=code, payment_method=method, invoice_id=int(invoice["invoice_id"]))
    await cb.answer()
    if method == "usdt":
        await state.set_state(Flow.waiting_usdt_txid)
        await screen(bot, cb.from_user.id, cb.message.chat.id, tr(lang, f"<b>₮ فاکتور #{invoice['invoice_id']}</b>\n\nمبلغ: <b>{invoice['total_usdt']:g} USDT</b>\n⏳ اعتبار تا: <b>{fmt_dt(invoice['expires_at'])}</b>\n\nابتدا TXID را ارسال کنید و سپس تصویر رسید را بفرستید.", f"<b>₮ Invoice #{invoice['invoice_id']}</b>\n\nAmount: <b>{invoice['total_usdt']:g} USDT</b>\n⏳ Valid until: <b>{fmt_dt(invoice['expires_at'])}</b>\n\nFirst send the TXID, then the receipt image."), kb(nav(lang, "vip")))
    else:
        await state.set_state(Flow.waiting_receipt)
        await screen(bot, cb.from_user.id, cb.message.chat.id, tr(lang, f"<b>💳 فاکتور #{invoice['invoice_id']}</b>\n\nمبلغ: <b>{int(invoice['final_amount_rial']):,} ریال</b>\nنرخ USDT: <b>{invoice['usdt_rial_rate']:,}</b>\n⏳ اعتبار تا: <b>{fmt_dt(invoice['expires_at'])}</b>\n\nتصویر رسید را ارسال کنید.", f"<b>💳 Invoice #{invoice['invoice_id']}</b>\n\nAmount: <b>{int(invoice['final_amount_rial']):,} IRR</b>\nUSDT rate: <b>{invoice['usdt_rial_rate']:,}</b>\n⏳ Valid until: <b>{fmt_dt(invoice['expires_at'])}</b>\n\nSend the receipt image."), kb(nav(lang, "vip")))


@router.message(Flow.waiting_receipt, F.photo)
async def receive_photo(message: Message, bot: Bot, state: FSMContext):
    db.upsert_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    lang = get_lang(message.from_user.id)
    data = await state.get_data(); code = str(data.get("plan_code")); method = str(data.get("payment_method", "rial")); invoice_id = data.get("invoice_id")
    plan = _plans().get(code)
    invoice = db.get_invoice(int(invoice_id)) if invoice_id else None
    if not plan or not invoice:
        await state.clear(); await clean_user_message(message); return
    if str(invoice["user_id"]) != str(message.from_user.id) or str(invoice["payment_status"]) != "pending":
        await state.clear(); await clean_user_message(message)
        await screen(bot, message.from_user.id, message.chat.id, tr(lang, "❌ این فاکتور دیگر معتبر نیست. خرید را دوباره شروع کنید.", "❌ This invoice is no longer valid. Start the purchase again."), kb(nav(lang,"vip"))); return
    try:
        from datetime import datetime, timezone
        if datetime.fromisoformat(str(invoice["expires_at"])) <= datetime.now(timezone.utc):
            db.expire_old_invoices(); raise ValueError("invoice expired")
    except Exception:
        await state.clear(); await clean_user_message(message)
        await screen(bot, message.from_user.id, message.chat.id, tr(lang, "⏳ اعتبار فاکتور تمام شده است. فاکتور جدید بگیرید.", "⏳ The invoice has expired. Create a new invoice."), kb(nav(lang,"vip"))); return

    pct = float(data.get("discount_percent", 0) or 0); promo_code = data.get("promo_code"); promo_id = data.get("promo_id")
    points_used = int(data.get("points_used", 0) or 0); txid = data.get("txid"); campaign_id = data.get("campaign_id")
    amount_usdt = float(invoice["base_amount_usdt"]); amount_rial = int(invoice["final_amount_rial"]) if invoice["final_amount_rial"] is not None else None
    price = f"{amount_rial:,} IRR" if method == "rial" else f"{amount_usdt:g} USDT"
    if points_used and not db.spend_points(message.from_user.id, points_used, "payment_reserve"):
        await state.clear(); await clean_user_message(message); await screen(bot,message.from_user.id,message.chat.id,tr(lang,"❌ موجودی امتیاز کافی نیست.","❌ Your points balance is no longer sufficient."),kb(nav(lang,"vip"))); return
    file_id = message.photo[-1].file_id
    payment_id = None
    try:
        payment_id = db.create_payment(message.from_user.id, code, int(plan["days"]), price, method, file_id, "photo", receipt_message_id=message.message_id,
            base_amount_irr=amount_rial, final_amount_irr=amount_rial, discount_percent=pct, promo_code=promo_code, points_used=points_used, txid=txid, campaign_id=campaign_id,
            invoice_id=int(invoice["id"]), amount_usdt=amount_usdt, amount_rial=amount_rial, transaction_hash=txid)
        if promo_id and not db.reserve_discount_use(int(promo_id), message.from_user.id, payment_id):
            raise ValueError("promo no longer available")
        if campaign_id and not db.reserve_campaign_use(int(campaign_id), message.from_user.id, payment_id):
            raise ValueError("campaign no longer available")
    except Exception as exc:
        if payment_id:
            db.cancel_payment_reservation(payment_id)
        elif points_used:
            db.refund_points(message.from_user.id, points_used, "payment_reserve_rollback")
        await state.clear(); await clean_user_message(message); await screen(bot,message.from_user.id,message.chat.id,tr(lang,f"❌ ثبت پرداخت ناموفق بود: {escape(str(exc))}",f"❌ Payment registration failed: {escape(str(exc))}"),kb(nav(lang,"vip"))); return

    db.set_setting("last_payment_invoice", str(invoice["id"]))
    deleted = await clean_user_message(message)
    await state.clear()
    await screen(bot,message.from_user.id,message.chat.id,tr(lang,f"✅ فاکتور <b>#{invoice['id']}</b> و پرداخت <b>#{payment_id}</b> ثبت شد و در انتظار بررسی ادمین است.",f"✅ Invoice <b>#{invoice['id']}</b> and payment <b>#{payment_id}</b> are registered and awaiting admin review."),kb(nav(lang,"main")))
    method_label = "ریال" if method == "rial" else f"USDT — {settings.usdt_network}"
    caption=(f"<b>🧾 New Payment / پرداخت جدید #{payment_id}</b>\nUser: <code>{message.from_user.id}</code>\nName: {escape(message.from_user.full_name)}\nPlan: <b>{escape(str(plan['en']))}</b>\nMethod: <b>{escape(method_label)}</b>\nInvoice: <b>#{invoice['id']}</b>\nAmount: <b>{escape(price)}</b>\nUSDT base: <b>{amount_usdt:g}</b>\nRate: <b>{invoice['usdt_rial_rate'] or '—'}</b>\nTXID: <code>{escape(str(txid or '—'))}</code>")
    for admin_id in settings.admin_ids:
        try:
            sent=await bot.send_photo(admin_id,file_id,caption=caption,parse_mode=ParseMode.HTML,reply_markup=admin_payment(payment_id, get_lang(admin_id))); db.save_admin_receipt(payment_id,admin_id,sent.message_id); await push_home_to_bottom(bot,int(admin_id))
        except Exception as exc:
            log.error("cannot notify admin %s: %s",admin_id,exc)


@router.message(Flow.waiting_receipt)
async def receipt_wrong_type(message: Message, bot: Bot):
    lang = get_lang(message.from_user.id); await clean_user_message(message)
    await screen(bot, message.from_user.id, message.chat.id, tr(lang, "لطفاً رسید را به‌صورت <b>تصویر</b> ارسال کنید.", "Please send the receipt as an <b>image</b>."), kb(nav(lang, "vip")))


async def cleanup_payment_messages(bot: Bot, pay) -> None:
    # Retry deleting the user's original receipt if it remained.
    if pay and pay["receipt_message_id"]:
        try:
            await bot.delete_message(pay["telegram_id"], int(pay["receipt_message_id"]))
        except Exception:
            pass
    # Delete receipt cards from every admin chat, not just the admin who clicked.
    for row in db.list_admin_receipts(int(pay["id"])):
        try:
            await bot.delete_message(int(row["admin_id"]), int(row["message_id"]))
        except Exception:
            pass
    db.clear_admin_receipts(int(pay["id"]))


async def revoke_user_invites(bot: Bot, user_id: int):
    for row in db.active_invites_for_user(user_id):
        try: await bot.revoke_chat_invite_link(settings.vip_channel_id, row["invite_link"])
        except Exception: pass
        db.mark_invite_revoked(row["invite_link"])


async def make_secure_invite(bot: Bot, user_id: int, license_id: int) -> str:
    await revoke_user_invites(bot, user_id)
    try: await bot.unban_chat_member(settings.vip_channel_id, user_id, only_if_banned=True)
    except Exception: pass
    invite = await bot.create_chat_invite_link(settings.vip_channel_id, name=f"NEXUS-{user_id}-{license_id}", creates_join_request=True)
    db.save_invite(user_id, license_id, invite.invite_link)
    return invite.invite_link


async def send_autotrade_license(bot: Bot, user_id: int, lic) -> None:
    """Send the Auto Trade license key after purchase/renewal.

    This is intentionally a separate message from the VIP channel access screen so
    the license remains visible/copyable even when the main single-message UI is
    edited later.
    """
    if not license_service.has_autotrade(user_id):
        return
    lang = get_lang(user_id)
    key = str(lic["license_key"] or "").strip()
    if not key:
        raise RuntimeError("Auto Trade license key was not generated")
    auto_exp = lic["autotrade_expires_at"] if "autotrade_expires_at" in lic.keys() and lic["autotrade_expires_at"] else lic["expires_at"]
    expires = fmt_dt(auto_exp)
    remaining = remaining_days(auto_exp)
    text = tr(
        lang,
        (
            "🤖 <b>NEXUS معاملات خودکار</b>\n\n"
            "✅ ماژول اتوترید شما فعال شد.\n\n"
            f"🔑 <b>License Key:</b>\n<code>{escape(key)}</code>\n\n"
            f"📅 اعتبار تا: <b>{expires}</b>\n"
            f"⏳ باقی‌مانده: <b>{remaining} روز</b>\n\n"
            "🖥 برای فعال‌سازی در MT5، اکسپرت NEXUS معاملات خودکار را روی چارت اجرا کنید "
            "و کلید مجوز بالا را در پنل راه‌اندازی وارد کنید.\n\n"
            "⚠️ هر لایسنس فقط به یک حساب MT5 متصل می‌شود."
        ),
        (
            "🤖 <b>NEXUS معاملات خودکار</b>\n\n"
            "✅ Your Auto Trade module is active.\n\n"
            f"🔑 <b>License Key:</b>\n<code>{escape(key)}</code>\n\n"
            f"📅 Valid until: <b>{expires}</b>\n"
            f"⏳ Remaining: <b>{remaining} days</b>\n\n"
            "🖥 To activate MT5, attach the NEXUS Auto Trade EA to a chart and enter "
            "the License Key above in the setup panel.\n\n"
            "⚠️ Each license can be linked to one MT5 account only."
        ),
    )
    await bot.send_message(user_id, text, parse_mode=ParseMode.HTML)

    # Deliver the compiled MT5 Expert Advisor automatically after the license.
    # The customer receives only the compiled EX5, never the MQL5 source.
    ea_path = Path(__file__).resolve().parents[1] / "assets" / "autotrade" / "NEXUS_AutoTrade.ex5"
    installer_ready = settings.autotrade_ex5_release_enabled and ea_path.is_file() and ea_path.stat().st_size > 0
    if installer_ready:
        ea_bytes = ea_path.read_bytes()
        await bot.send_document(
            user_id,
            BufferedInputFile(ea_bytes, filename="NEXUS_AutoTrade.ex5"),
            caption=tr(
                lang,
                "📦 <b>فایل نصب NEXUS معاملات خودکار برای متاتریدر ۵</b>",
                "📦 <b>NEXUS Auto Trade installer for MetaTrader 5</b>",
            ),
            parse_mode=ParseMode.HTML,
        )
    else:
        # License activation must never be rolled back just because the binary is
        # temporarily missing from the deployment package. The admin receives a
        # visible warning and can compile/upload the current EA source, while the
        # customer keeps the already-issued license.
        await bot.send_message(user_id, tr(
            lang,
            "⚠️ لایسنس شما فعال است، اما فایل نصب نسخه جدید هنوز روی سرور قرار نگرفته است. پس از آماده‌شدن فایل، از بخش «دریافت اکسپرت» آن را دریافت کنید.",
            "⚠️ Your license is active, but the current installer has not been placed on the server yet. Once available, download it from ‘Get MT5 EA’."
        ))
        for admin_id in settings.admin_ids:
            try:
                await bot.send_message(int(admin_id),
                    "⚠️ AutoTrade EX5 is missing. Compile mt5/NEXUS_AutoTrade/NEXUS_AutoTrade.mq5 (NEXUS v0.6.0) in MetaEditor and place the resulting EX5 at assets/autotrade/NEXUS_AutoTrade.ex5.")
                await push_home_to_bottom(bot, int(admin_id))
            except Exception:
                pass

    guide = tr(
        lang,
        (
            "📘 <b>آموزش نصب NEXUS معاملات خودکار</b>\n\n"
            "1️⃣ فایل <code>NEXUS_AutoTrade.ex5</code> بالا را دانلود کنید.\n"
            "2️⃣ در MetaTrader 5 از منوی <b>File → Open Data Folder</b> وارد پوشه داده شوید.\n"
            "3️⃣ وارد <code>MQL5 → Experts</code> شوید و فایل EX5 را در آن قرار دهید.\n"
            "4️⃣ MetaTrader 5 را یک‌بار بسته و دوباره اجرا کنید؛ یا Navigator را Refresh کنید.\n"
            "5️⃣ از <b>Navigator → Expert Advisors</b>، NEXUS معاملات خودکار را روی یک چارت بکشید.\n"
            "6️⃣ <b>Algo Trading</b> را فعال کنید.\n"
            "7️⃣ مجوز Key ارسال‌شده را در پنل روی چارت وارد کنید.\n"
            "8️⃣ مدیریت سرمایه را انتخاب کرده و <b>CONNECT & ACTIVATE</b> را بزنید.\n\n"
            "✅ در اتصال موفق، وضعیت <b>CONNECTED / WAITING FOR SIGNAL</b> نمایش داده می‌شود.\n\n"
            "⚠️ هر مجوز فقط برای یک حساب MT5 قابل اتصال است."
        ),
        (
            "📘 <b>NEXUS Auto Trade Installation</b>\n\n"
            "1️⃣ Download <code>NEXUS_AutoTrade.ex5</code> above.\n"
            "2️⃣ In MetaTrader 5 open <b>File → Open Data Folder</b>.\n"
            "3️⃣ Open <code>MQL5 → Experts</code> and place the EX5 file there.\n"
            "4️⃣ Restart MetaTrader 5 once, or refresh Navigator.\n"
            "5️⃣ From <b>Navigator → Expert Advisors</b>, attach NEXUS Auto Trade to a chart.\n"
            "6️⃣ Enable <b>Algo Trading</b>.\n"
            "7️⃣ Enter the License Key sent by the bot in the on-chart setup panel.\n"
            "8️⃣ Select money management and press <b>CONNECT & ACTIVATE</b>.\n\n"
            "✅ A successful connection shows <b>CONNECTED / WAITING FOR SIGNAL</b>.\n\n"
            "⚠️ Each License can be linked to one MT5 account only."
        ),
    )
    await bot.send_message(user_id, guide, parse_mode=ParseMode.HTML)

    # Every standalone delivery is followed by a fresh dashboard so the main
    # menu remains the last message in the user's chat.
    await push_home_to_bottom(bot, int(user_id))


async def send_license_link(bot: Bot, user_id: int, lic) -> str:
    if not license_service.has_vip(user_id):
        raise PermissionError("license does not include VIP access")
    lang = get_lang(user_id); link = await make_secure_invite(bot, user_id, lic["id"])
    vip_exp = lic["vip_expires_at"] if "vip_expires_at" in lic.keys() and lic["vip_expires_at"] else lic["expires_at"]
    text = tr(
        lang,
        "✅ <b>دسترسی وی‌آی‌پی شما فعال است.</b>\n\n" f"اعتبار تا: <b>{fmt_dt(vip_exp)}</b>\n" f"باقی‌مانده: <b>{remaining_days(vip_exp)} روز</b>\n\n" "این لینک مخصوص حساب تلگرام شماست و درخواست عضویت افراد دیگر رد می‌شود.\n\n" f"🔐 <a href=\"{link}\">درخواست ورود به کانال VIP</a>",
        "✅ <b>Your VIP access is active.</b>\n\n" f"Valid until: <b>{fmt_dt(vip_exp)}</b>\n" f"Remaining: <b>{remaining_days(vip_exp)} days</b>\n\n" "This link is tied to your Telegram account. Join requests from other users will be rejected.\n\n" f"🔐 <a href=\"{link}\">Request VIP Channel Access</a>",
    )
    await screen(bot, user_id, user_id, text, kb(nav(lang, "main")))
    return link


@router.callback_query(F.data.startswith("payok:"))
async def approve_payment(cb: CallbackQuery, bot: Bot):
    if not is_admin(cb.from_user.id):
        await cb.answer("دسترسی مجاز نیست." if get_lang(cb.from_user.id) == "fa" else "Access denied.", show_alert=True); return
    payment_id = int(cb.data.split(":", 1)[1]); pay = db.get_payment(payment_id)
    if not pay:
        await cb.answer("پرداخت پیدا نشد." if get_lang(cb.from_user.id) == "fa" else "Payment not found.", show_alert=True); return
    if not db.review_payment(payment_id, "approved", cb.from_user.id):
        await cb.answer(tr(get_lang(cb.from_user.id), "قبلاً بررسی شده است.", "Already reviewed."), show_alert=True); return
    db.add_audit(cb.from_user.id,"approve_payment",pay["telegram_id"],f"payment_id={payment_id}")
    lic = license_service.activate_payment(pay)
    await cleanup_payment_messages(bot, pay)
    access = license_service.snapshot(int(pay["telegram_id"]))
    user_id = int(pay["telegram_id"])
    delivery_errors: list[str] = []

    # Deliver each entitlement independently. A VIP-channel problem (for example
    # an invalid/changed VIP_CHANNEL_ID or missing channel permissions) must not
    # prevent AutoTrade license delivery to the customer. Likewise, a missing EX5
    # must not turn an otherwise valid VIP activation into a failed payment flow.
    if access.vip:
        try:
            await send_license_link(bot, user_id, lic)
        except Exception as exc:
            delivery_errors.append(f"VIP delivery: {type(exc).__name__}: {exc}")
            log.exception("VIP access delivery failed for payment=%s user=%s", payment_id, user_id)
            try:
                lang_user = get_lang(user_id)
                await bot.send_message(
                    user_id,
                    tr(
                        lang_user,
                        "⚠️ پرداخت شما تأیید شد، اما ساخت لینک ورود VIP با خطا مواجه شد. اشتراک شما فعال است و پشتیبانی آن را اصلاح می‌کند.",
                        "⚠️ Your payment was approved, but the VIP access link could not be generated. Your subscription is active; support will fix the access link.",
                    ),
                )
            except Exception as notify_exc:
                delivery_errors.append(f"VIP fallback notification: {type(notify_exc).__name__}: {notify_exc}")
    else:
        try:
            lang_user = get_lang(user_id)
            await screen(
                bot, user_id, user_id,
                tr(lang_user,
                   f"✅ اشتراک شما فعال شد. اعتبار تا <b>{fmt_dt(lic['expires_at'])}</b>.",
                   f"✅ Your subscription is active until <b>{fmt_dt(lic['expires_at'])}</b>."),
                kb(nav(lang_user, "main")),
            )
        except Exception as exc:
            delivery_errors.append(f"Subscription notification: {type(exc).__name__}: {exc}")
            log.exception("subscription notification failed for payment=%s user=%s", payment_id, user_id)

    if access.autotrade:
        try:
            # AutoTrade keys are intentionally not delivered at payment approval.
            # The paid user must first provide the MT5 account; only then is the
            # key generated, bound and delivered.
            db.prepare_autotrade_license_pending(user_id)
            lang_user=get_lang(user_id)
            await bot.send_message(
                user_id,
                tr(lang_user,
                   "✅ پرداخت شما تأیید شد.\n\nبرای صدور لایسنس اختصاصی AutoTrade، لطفاً شماره حساب MetaTrader 5 خود را ارسال کنید.\n\n⚠️ لایسنس فقط به همین حساب متصل خواهد شد و اجرای آن روی حساب دیگر مجاز نیست.",
                   "✅ Your payment is approved.\n\nTo issue your dedicated AutoTrade license, please send your MetaTrader 5 account number.\n\n⚠️ The license will be bound exclusively to this account and cannot be used on another account."
                ),
                parse_mode=ParseMode.HTML,
                reply_markup=kb([[("📌 ثبت شماره حساب MT5", "autotrade_submit_account")]]),
            )
        except Exception as exc:
            delivery_errors.append(f"AutoTrade account-request: {type(exc).__name__}: {exc}")
            log.exception("AutoTrade account request failed for payment=%s user=%s", payment_id, user_id)

    if delivery_errors:
        # Payment remains APPROVED. Report the exact failing delivery stage to the
        # admin instead of masking the original exception behind a generic message.
        detail = " | ".join(delivery_errors)
        await cb.answer(
            tr(get_lang(cb.from_user.id),
               "پرداخت تأیید شد؛ بخشی از دسترسی نیاز به پیگیری دارد.",
               "Payment approved; part of access delivery needs attention."),
            show_alert=True,
        )
        for admin_id in settings.admin_ids:
            try:
                await bot.send_message(
                    admin_id,
                    f"⚠️ Payment #{payment_id} approved. Delivery issue for user {user_id}: {escape(detail)}",
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                log.exception("Could not notify admin %s about payment delivery failure", admin_id)
    else:
        await cb.answer(tr(get_lang(cb.from_user.id), "تأیید شد ✅", "Approved ✅"))


@router.callback_query(F.data.startswith("payno:"))
async def reject_payment(cb: CallbackQuery, bot: Bot):
    if not is_admin(cb.from_user.id):
        await cb.answer("دسترسی مجاز نیست." if get_lang(cb.from_user.id) == "fa" else "Access denied.", show_alert=True); return
    payment_id = int(cb.data.split(":", 1)[1]); pay = db.get_payment(payment_id)
    if not pay:
        await cb.answer("پرداخت پیدا نشد." if get_lang(cb.from_user.id) == "fa" else "Payment not found.", show_alert=True); return
    if not db.review_payment(payment_id, "rejected", cb.from_user.id):
        await cb.answer(tr(get_lang(cb.from_user.id), "قبلاً بررسی شده است.", "Already reviewed."), show_alert=True); return
    if int(pay["points_used"] or 0) > 0:
        db.refund_points(pay["telegram_id"], int(pay["points_used"]), "payment_rejected_refund", str(payment_id))
    if pay["promo_code"]:
        db.release_discount_use(payment_id)
    if pay["campaign_id"]:
        db.release_campaign_use(payment_id)
    db.add_audit(cb.from_user.id,"reject_payment",pay["telegram_id"],f"payment_id={payment_id}")
    await cleanup_payment_messages(bot, pay)
    lang = get_lang(pay["telegram_id"])
    try: await screen(bot, pay["telegram_id"], pay["telegram_id"], tr(lang, "❌ رسید پرداخت شما تأیید نشد. اگر از امتیاز استفاده کرده بودید، امتیازها به حسابتان برگشت داده شد.", "❌ Your payment receipt was not approved. Any reserved points were returned to your account."), kb(nav(lang, "main")))
    except Exception: pass
    await cb.answer(tr(get_lang(cb.from_user.id), "رد شد", "Rejected"))


@router.chat_join_request()
async def secure_join(req: ChatJoinRequest, bot: Bot):
    if req.chat.id != settings.vip_channel_id: return
    link = req.invite_link.invite_link if req.invite_link else None
    row = db.get_invite(link) if link else None; lic = db.active_license(req.from_user.id)
    valid = bool(row and row["status"] == "active" and row["telegram_id"] == req.from_user.id and lic and lic["id"] == row["license_id"] and license_service.has_vip(req.from_user.id))
    lang = get_lang(req.from_user.id)
    if valid:
        await bot.approve_chat_join_request(settings.vip_channel_id, req.from_user.id); db.mark_invite_used(link)
        try: await bot.revoke_chat_invite_link(settings.vip_channel_id, link)
        except Exception: pass
        try:
            await bot.send_message(req.from_user.id, tr(lang, "✅ ورود شما به کانال وی‌آی‌پی تأیید شد.", "✅ Your VIP channel access has been approved."))
            await push_home_to_bottom(bot, int(req.from_user.id))
        except Exception: pass
    else:
        await bot.decline_chat_join_request(settings.vip_channel_id, req.from_user.id)
        try:
            await bot.send_message(req.from_user.id, tr(lang, "⛔ این لینک برای حساب شما معتبر نیست یا اشتراک فعالی ندارید.", "⛔ This link is not valid for your account or you do not have an active subscription."))
            await push_home_to_bottom(bot, int(req.from_user.id))
        except Exception: pass


@router.callback_query(F.data == "account")
async def account(cb: CallbackQuery, bot: Bot):
    if not await gated(cb, bot): return
    lang = get_lang(cb.from_user.id); await cb.answer()
    user = db.get_user(cb.from_user.id)
    lic = db.active_license(cb.from_user.id)
    access = license_service.snapshot(cb.from_user.id)
    refs = db.referral_stats(cb.from_user.id)
    level = db.user_level(cb.from_user.id)
    username = f"@{user['username']}" if user and user["username"] else "—"
    history = db.user_paid_license_history(cb.from_user.id, 10)

    if lang == "fa":
        lines = [
            "<b>حساب کاربری</b>",
            "",
            f"شناسه تلگرام: <code>{cb.from_user.id}</code>",
            f"نام کاربری: {escape(username)}",
            "زبان: فارسی",
        ]
        if lic:
            lines += [
                "اشتراک: <b>فعال</b>",
                f"پلن: <b>{escape(str(access.plan_code or '—'))}</b>",
                f"دسترسی VIP: <b>{'فعال' if access.vip else 'غیرفعال'}</b>",
                f"دسترسی Auto Trade: <b>{'فعال' if access.autotrade else 'غیرفعال'}</b>",
                f"شروع اعتبار: <b>{fmt_dt(lic['starts_at'])}</b>",
                f"پایان اعتبار: <b>{fmt_dt(lic['expires_at'])}</b>",
                f"باقی‌مانده: <b>{remaining_days(lic['expires_at'])} روز</b>",
            ]
        else:
            latest = db.latest_license(cb.from_user.id)
            lines += ["اشتراک وی‌آی‌پی: <b>غیرفعال</b>"]
            if latest:
                lines.append(f"آخرین پایان اعتبار: <b>{fmt_dt(latest['expires_at'])}</b>")
        lines += [
            f"امتیاز NEXUS: <b>{refs['points']}</b>",
            f"دعوت موفق: <b>{refs['successful']}</b>",
            f"سطح کاربری: <b>{level['fa']}</b>",
        ]
        if history:
            lines += ["", "<b>خریدهای پولی</b>"]
            for item in history:
                lines += [
                    f"پلن {escape(str(item['days']))} روزه",
                    f"شروع: <b>{fmt_dt(item['starts_at'])}</b>",
                    f"پایان: <b>{fmt_dt(item['expires_at'])}</b>",
                    "",
                ]
        text="\n".join(lines).rstrip()
    else:
        lines = [
            "<b>My Account</b>",
            "",
            f"Telegram ID: <code>{cb.from_user.id}</code>",
            f"Username: {escape(username)}",
            "Language: English",
        ]
        if lic:
            lines += [
                "Subscription: <b>Active</b>",
                f"Plan: <b>{escape(str(access.plan_code or '—'))}</b>",
                f"VIP access: <b>{'Active' if access.vip else 'Inactive'}</b>",
                f"Auto Trade access: <b>{'Active' if access.autotrade else 'Inactive'}</b>",
                f"Valid from: <b>{fmt_dt(lic['starts_at'])}</b>",
                f"Valid until: <b>{fmt_dt(lic['expires_at'])}</b>",
                f"Remaining: <b>{remaining_days(lic['expires_at'])} days</b>",
            ]
        else:
            latest = db.latest_license(cb.from_user.id)
            lines += ["VIP subscription: <b>Inactive</b>"]
            if latest:
                lines.append(f"Last expiry: <b>{fmt_dt(latest['expires_at'])}</b>")
        lines += [
            f"NEXUS Points: <b>{refs['points']}</b>",
            f"Successful referrals: <b>{refs['successful']}</b>",
            f"User level: <b>{level['en']}</b>",
        ]
        if history:
            lines += ["", "<b>Paid Purchases</b>"]
            for item in history:
                lines += [
                    f"{escape(str(item['days']))}-day plan",
                    f"Start: <b>{fmt_dt(item['starts_at'])}</b>",
                    f"End: <b>{fmt_dt(item['expires_at'])}</b>",
                    "",
                ]
        text="\n".join(lines).rstrip()
    await screen(bot, cb.from_user.id, cb.message.chat.id, text, account_menu(lang, access.vip, access.autotrade))


@router.callback_query(F.data == "new_vip_link")
async def new_vip_link(cb: CallbackQuery, bot: Bot):
    if not await gated(cb, bot): return
    lang = get_lang(cb.from_user.id); lic = db.active_license(cb.from_user.id)
    if not (lic and license_service.has_vip(cb.from_user.id)):
        await cb.answer(tr(lang, "اشتراک فعال ندارید.", "You do not have an active subscription."), show_alert=True); return
    try:
        await send_license_link(bot, cb.from_user.id, lic); await cb.answer(tr(lang, "لینک جدید ساخته شد ✅", "New link created ✅"))
    except Exception:
        log.exception("new invite failed"); await cb.answer(tr(lang, "ساخت لینک با خطا مواجه شد.", "Could not create the link."), show_alert=True)


@router.callback_query(F.data == "my_payments")
async def my_payments(cb: CallbackQuery, bot: Bot):
    if not await gated(cb, bot):
        return
    lang = get_lang(cb.from_user.id)
    await cb.answer()
    rows = db.user_payments(cb.from_user.id, "all", 20)
    if lang == "fa":
        text = "<b>💳 پرداخت‌های من</b>\n\n"
        if not rows:
            text += "هنوز پرداختی برای حساب شما ثبت نشده است."
        else:
            parts = []
            for row in rows:
                status_map = {
                    "approved": "🟢 موفق",
                    "pending": "🟡 در انتظار بررسی",
                    "rejected": "🔴 رد شده",
                    "cancelled": "⚪ لغو شده",
                    "failed": "🔴 ناموفق",
                }
                method = "₮ تتر" if str(row["payment_method"]).lower() == "usdt" else "💳 ریالی"
                amount = row["amount_usdt"] if row["amount_usdt"] is not None else row["final_amount_irr"]
                amount_text = f"{amount} USDT" if str(row["payment_method"]).lower() == "usdt" else f"{int(amount or 0):,} ریال"
                parts.append(
                    f"🧾 <b>#{row['id']}</b> — {escape(str(row['plan_code']))}\n"
                    f"{method} | {amount_text}\n"
                    f"{status_map.get(str(row['status']), str(row['status']))}\n"
                    f"📅 {fmt_dt(row['created_at'])}"
                )
            text += "\n\n".join(parts)
    else:
        text = "<b>💳 My Payments</b>\n\n"
        if not rows:
            text += "No payments have been recorded for your account yet."
        else:
            parts = []
            for row in rows:
                status_map = {
                    "approved": "🟢 Successful",
                    "pending": "🟡 Pending review",
                    "rejected": "🔴 Rejected",
                    "cancelled": "⚪ Cancelled",
                    "failed": "🔴 Failed",
                }
                method = "₮ USDT" if str(row["payment_method"]).lower() == "usdt" else "💳 IRR"
                amount = row["amount_usdt"] if row["amount_usdt"] is not None else row["final_amount_irr"]
                amount_text = f"{amount} USDT" if str(row["payment_method"]).lower() == "usdt" else f"{int(amount or 0):,} IRR"
                parts.append(
                    f"🧾 <b>#{row['id']}</b> — {escape(str(row['plan_code']))}\n"
                    f"{method} | {amount_text}\n"
                    f"{status_map.get(str(row['status']), str(row['status']))}\n"
                    f"📅 {fmt_dt(row['created_at'])}"
                )
            text += "\n\n".join(parts)
    await screen(bot, cb.from_user.id, cb.message.chat.id, text, my_payments_menu(lang))


@router.callback_query(F.data.startswith("my_payments:"))
async def my_payments_filter(cb: CallbackQuery, bot: Bot):
    if not await gated(cb, bot):
        return
    lang = get_lang(cb.from_user.id)
    status = cb.data.split(":", 1)[1].lower()
    await cb.answer()
    rows = db.user_payments(cb.from_user.id, status, 30)
    if lang == "fa":
        title = {"approved": "🟢 پرداخت‌های موفق", "pending": "🟡 پرداخت‌های در انتظار", "failed": "🔴 پرداخت‌های ناموفق", "all": "📜 تاریخچه کامل"}.get(status, "💳 پرداخت‌ها")
        if not rows:
            text = f"<b>{title}</b>\n\nموردی پیدا نشد."
        else:
            status_map = {"approved": "🟢 موفق", "pending": "🟡 در انتظار بررسی", "rejected": "🔴 رد شده", "cancelled": "⚪ لغو شده", "failed": "🔴 ناموفق"}
            items = []
            for row in rows:
                method = "₮ تتر" if str(row["payment_method"]).lower() == "usdt" else "💳 ریالی"
                amount = row["amount_usdt"] if row["amount_usdt"] is not None else row["final_amount_irr"]
                amount_text = f"{amount} USDT" if str(row["payment_method"]).lower() == "usdt" else f"{int(amount or 0):,} ریال"
                items.append(f"🧾 <b>#{row['id']}</b> — {escape(str(row['plan_code']))}\n{method} | {amount_text}\n{status_map.get(str(row['status']), str(row['status']))}\n📅 {fmt_dt(row['created_at'])}")
            text = f"<b>{title}</b>\n\n" + "\n\n".join(items)
    else:
        title = {"approved": "🟢 Successful Payments", "pending": "🟡 Pending Payments", "failed": "🔴 Failed Payments", "all": "📜 Full History"}.get(status, "💳 Payments")
        if not rows:
            text = f"<b>{title}</b>\n\nNo payments found."
        else:
            status_map = {"approved": "🟢 Successful", "pending": "🟡 Pending review", "rejected": "🔴 Rejected", "cancelled": "⚪ Cancelled", "failed": "🔴 Failed"}
            items = []
            for row in rows:
                method = "₮ USDT" if str(row["payment_method"]).lower() == "usdt" else "💳 IRR"
                amount = row["amount_usdt"] if row["amount_usdt"] is not None else row["final_amount_irr"]
                amount_text = f"{amount} USDT" if str(row["payment_method"]).lower() == "usdt" else f"{int(amount or 0):,} IRR"
                items.append(f"🧾 <b>#{row['id']}</b> — {escape(str(row['plan_code']))}\n{method} | {amount_text}\n{status_map.get(str(row['status']), str(row['status']))}\n📅 {fmt_dt(row['created_at'])}")
            text = f"<b>{title}</b>\n\n" + "\n\n".join(items)
    await screen(bot, cb.from_user.id, cb.message.chat.id, text, my_payments_menu(lang))


@router.callback_query(F.data == "support")
async def support(cb: CallbackQuery, bot: Bot):
    if not await gated(cb, bot): return
    lang = get_lang(cb.from_user.id); await cb.answer()
    markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=tr(lang, "🛟 ارتباط با پشتیبانی", "🛟 Contact Support"), url=settings.support_url)], [InlineKeyboardButton(text=tr(lang, "⬅️ بازگشت", "⬅️ Back"), callback_data="main"), InlineKeyboardButton(text=tr(lang, "🏠 منوی اصلی", "🏠 Main Menu"), callback_data="main")]])
    await screen(bot, cb.from_user.id, cb.message.chat.id, tr(lang, "<b>پشتیبانی NEXUS</b>\n\nبرای ارتباط با پشتیبانی از دکمه زیر استفاده کنید.", "<b>NEXUS Support</b>\n\nUse the button below to contact support."), markup)


@router.callback_query(F.data == "admin")
async def admin(cb: CallbackQuery, bot: Bot, state: FSMContext):
    if not is_admin(cb.from_user.id):
        await cb.answer("دسترسی مجاز نیست." if get_lang(cb.from_user.id) == "fa" else "Access denied.", show_alert=True); return
    await state.clear(); lang = get_lang(cb.from_user.id); await cb.answer()
    await screen(bot, cb.from_user.id, cb.message.chat.id, tr(lang, "<b>🛠 پنل ادمین NEXUS</b>", "<b>🛠 NEXUS Admin Panel</b>"), admin_menu(lang))


@router.callback_query(F.data == "admin_stats")
async def admin_stats(cb: CallbackQuery, bot: Bot):
    if not is_admin(cb.from_user.id): return
    lang = get_lang(cb.from_user.id); s = db.stats(); await cb.answer()
    text = tr(lang, f"<b>📊 آمار NEXUS</b>\n\n👥 کاربران: <b>{s['users']}</b>\n💎 VIP فعال: <b>{s['active']}</b>\n🧾 در انتظار: <b>{s['pending']}</b>\n✅ پرداخت تأییدشده: <b>{s['approved']}</b>\n⌛ منقضی/لغوشده: <b>{s['expired']}</b>\n🎁 دعوت موفق: <b>{s['referrals']}</b>\n⭐ امتیاز در گردش: <b>{s['points']}</b>\n🏷 تخفیف فعال: <b>{s['discounts']}</b>\n🎯 کمپین فعال: <b>{db.campaign_count()}</b>\n⚠️ انقضا تا ۳ روز: <b>{db.expiring_count(3)}</b>\n⚠️ انقضا تا ۷ روز: <b>{db.expiring_count(7)}</b>", f"<b>📊 NEXUS Statistics</b>\n\n👥 Users: <b>{s['users']}</b>\n💎 Active VIP: <b>{s['active']}</b>\n🧾 Pending: <b>{s['pending']}</b>\n✅ Approved payments: <b>{s['approved']}</b>\n⌛ Expired/cancelled: <b>{s['expired']}</b>\n🎁 Successful referrals: <b>{s['referrals']}</b>\n⭐ Points in circulation: <b>{s['points']}</b>\n🏷 Active discounts: <b>{s['discounts']}</b>\n🎯 Active campaigns: <b>{db.campaign_count()}</b>\n⚠️ Expiring in 3 days: <b>{db.expiring_count(3)}</b>\n⚠️ Expiring in 7 days: <b>{db.expiring_count(7)}</b>")
    await screen(bot, cb.from_user.id, cb.message.chat.id, text, kb(nav(lang, "admin")))


@router.callback_query(F.data == "admin_pending")
async def admin_pending(cb: CallbackQuery, bot: Bot):
    if not is_admin(cb.from_user.id): return
    lang = get_lang(cb.from_user.id); rows = db.list_pending_payments(); await cb.answer()
    if not rows:
        text = tr(lang, "<b>🧾 پرداخت‌های در انتظار</b>\n\nموردی وجود ندارد.", "<b>🧾 Pending Payments</b>\n\nNo pending payments.")
    else:
        lines = [f"#{r['id']} — <code>{r['telegram_id']}</code> — {r['days']}d — {r['payment_method'].upper()} — {r['discount_percent']:g}%" for r in rows]
        text = tr(lang, "<b>🧾 پرداخت‌های در انتظار</b>\n\n", "<b>🧾 Pending Payments</b>\n\n") + "\n".join(lines)
    await screen(bot, cb.from_user.id, cb.message.chat.id, text, kb(nav(lang, "admin")))


@router.callback_query(F.data == "admin_users")
async def admin_users(cb: CallbackQuery, bot: Bot):
    if not is_admin(cb.from_user.id): return
    lang = get_lang(cb.from_user.id); rows = db.list_users(12); await cb.answer(); buttons=[]
    for r in rows:
        name = f"@{r['username']}" if r["username"] else (r["first_name"] or str(r["telegram_id"])); buttons.append([(f"👤 {name}", f"admuser:{r['telegram_id']}")])
    buttons += nav(lang, "admin")
    await screen(bot, cb.from_user.id, cb.message.chat.id, tr(lang, "<b>👥 کاربران</b>\n\nآخرین کاربران را انتخاب کنید:", "<b>👥 Users</b>\n\nSelect a recent user:"), kb(buttons))


@router.callback_query(F.data.startswith("admuser:"))
async def admin_user_detail(cb: CallbackQuery, bot: Bot):
    if not is_admin(cb.from_user.id): return
    lang = get_lang(cb.from_user.id); target = int(cb.data.split(":", 1)[1]); await cb.answer()
    u = db.get_user(target); lic = db.active_license(target); access = license_service.snapshot(target); purchases = db.count_user_payments(target); refs = db.referral_stats(target)
    if not u:
        await cb.answer(tr(lang, "کاربر پیدا نشد", "User not found"), show_alert=True); return
    uname = f"@{u['username']}" if u["username"] else "—"; vip = (f"✅ {fmt_dt(lic['expires_at'])} ({remaining_days(lic['expires_at'])}d)" if lic else "❌")
    text = tr(lang, f"<b>👤 پروفایل کاربر</b>\n\nID: <code>{target}</code>\nUsername: {escape(uname)}\nزبان: {escape(u['language'] or '—')}\nPublic: {'✅' if u['joined_public'] else '❌'}\nاشتراک: {vip}\nVIP Access: {'✅' if access.vip else '❌'}\nAuto Trade: {'✅' if access.autotrade else '❌'}\nپلن: <b>{escape(str(access.plan_code or '—'))}</b>\nخریدهای تأییدشده: <b>{purchases}</b>\n⭐ امتیاز: <b>{refs['points']}</b>\n🎁 دعوت موفق: <b>{refs['successful']}</b>\nReferral: <code>{escape(u['referral_code'] or '—')}</code>", f"<b>👤 User Profile</b>\n\nID: <code>{target}</code>\nUsername: {escape(uname)}\nLanguage: {escape(u['language'] or '—')}\nPublic: {'✅' if u['joined_public'] else '❌'}\nSubscription: {vip}\nVIP Access: {'✅' if access.vip else '❌'}\nAuto Trade: {'✅' if access.autotrade else '❌'}\nPlan: <b>{escape(str(access.plan_code or '—'))}</b>\nApproved purchases: <b>{purchases}</b>\n⭐ Points: <b>{refs['points']}</b>\n🎁 Successful referrals: <b>{refs['successful']}</b>\nReferral: <code>{escape(u['referral_code'] or '—')}</code>")
    await screen(bot, cb.from_user.id, cb.message.chat.id, text, admin_user_actions(target, lang))


@router.callback_query(F.data.startswith("admextend:"))
async def admin_extend(cb: CallbackQuery, bot: Bot):
    if not is_admin(cb.from_user.id): return
    _, uid, days = cb.data.split(":", 2); target, days_i = int(uid), int(days)
    if not db.get_user(target):
        await cb.answer("کاربر پیدا نشد." if get_lang(cb.from_user.id) == "fa" else "User not found", show_alert=True); return
    lic = license_service.grant_admin(target, days_i, cb.from_user.id); db.add_audit(cb.from_user.id,"extend_vip",target,f"days={days_i}"); lang_admin=get_lang(cb.from_user.id)
    await cb.answer(tr(lang_admin, f"{days_i}+ روز ✅", f"+{days_i} days ✅"), show_alert=True)
    try:
        lang = get_lang(target); await bot.send_message(target, tr(lang, f"✅ ادمین {days_i} روز به اعتبار VIP شما اضافه کرد.\nانقضای جدید: {fmt_dt(lic['expires_at'])}", f"✅ Admin added {days_i} days to your VIP subscription.\nNew expiry: {fmt_dt(lic['expires_at'])}"))
    except Exception: pass


@router.callback_query(F.data.startswith("admpoints:"))
async def admin_points(cb: CallbackQuery, bot: Bot):
    if not is_admin(cb.from_user.id): return
    _, uid, amount = cb.data.split(":", 2); target, points = int(uid), int(amount); db.add_points(target, points, "admin_bonus", str(cb.from_user.id)); db.add_audit(cb.from_user.id,"add_points",target,f"points={points}")
    lang_admin = get_lang(cb.from_user.id); await cb.answer(tr(lang_admin, f"{points} امتیاز اضافه شد ⭐", f"{points} points added ⭐"), show_alert=True)
    try:
        lang = get_lang(target); await bot.send_message(target, tr(lang, f"⭐ مدیریت <b>{points} NEXUS Points</b> به حساب شما اضافه کرد.", f"⭐ Admin added <b>{points} NEXUS Points</b> to your account."), parse_mode=ParseMode.HTML)
    except Exception: pass


@router.callback_query(F.data.startswith("admlink:"))
async def admin_link(cb: CallbackQuery, bot: Bot):
    if not is_admin(cb.from_user.id): return
    target = int(cb.data.split(":", 1)[1]); lic = db.active_license(target); lang=get_lang(cb.from_user.id)
    if not (lic and license_service.has_vip(target)):
        await cb.answer(tr(lang, "وی‌آی‌پی فعال ندارد", "No active VIP"), show_alert=True); return
    try: await send_license_link(bot, target, lic); await cb.answer(tr(lang, "لینک وی‌آی‌پی ارسال شد ✅", "VIP link sent ✅"), show_alert=True)
    except Exception: log.exception("admin invite failed"); await cb.answer(tr(lang, "ساخت لینک خطا داد", "Invite failed"), show_alert=True)


@router.callback_query(F.data.startswith("admcancel:"))
async def admin_cancel(cb: CallbackQuery, bot: Bot):
    if not is_admin(cb.from_user.id): return
    target = int(cb.data.split(":", 1)[1]); db.cancel_active_license(target); db.add_audit(cb.from_user.id,"cancel_vip",target); await revoke_user_invites(bot, target)
    try: await bot.ban_chat_member(settings.vip_channel_id, target)
    except Exception: pass
    lang_admin=get_lang(cb.from_user.id); await cb.answer(tr(lang_admin, "وی‌آی‌پی لغو شد", "VIP cancelled"), show_alert=True)
    try:
        lang=get_lang(target); await bot.send_message(target, tr(lang, "⛔ دسترسی وی‌آی‌پی شما توسط مدیریت غیرفعال شد.", "⛔ Your VIP access was disabled by the administrator."))
    except Exception: pass


@router.callback_query(F.data == "admin_subs")
async def admin_subs(cb: CallbackQuery, bot: Bot):
    if not is_admin(cb.from_user.id): return
    lang=get_lang(cb.from_user.id); s=db.stats(); ec=db.entitlement_counts(); await cb.answer()
    text=tr(lang, f"<b>💎 مدیریت اشتراک‌ها</b>\n\nاشتراک فعال: <b>{s['active']}</b>\nدسترسی VIP: <b>{ec['vip']}</b>\nدسترسی Auto Trade: <b>{ec['autotrade']}</b>\nانقضا تا ۳ روز: <b>{db.expiring_count(3)}</b>\nانقضا تا ۷ روز: <b>{db.expiring_count(7)}</b>\nمنقضی/لغوشده: <b>{s['expired']}</b>\n\nبرای مدیریت فردی از بخش کاربران وارد پروفایل شوید.", f"<b>💎 Subscription Management</b>\n\nActive subscriptions: <b>{s['active']}</b>\nVIP access: <b>{ec['vip']}</b>\nAuto Trade access: <b>{ec['autotrade']}</b>\nExpiring in 3 days: <b>{db.expiring_count(3)}</b>\nExpiring in 7 days: <b>{db.expiring_count(7)}</b>\nExpired/cancelled: <b>{s['expired']}</b>\n\nOpen a user profile for individual management.")
    await screen(bot, cb.from_user.id, cb.message.chat.id, text, kb(nav(lang,"admin")))


@router.callback_query(F.data == "admin_plans")
async def admin_plans(cb: CallbackQuery, bot: Bot, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    await state.clear(); lang=get_lang(cb.from_user.id); await cb.answer(); lines=[]
    for p in db.list_plans(active_only=False):
        status="✅" if p["active"] else "⛔"
        usdt=f"{p['usdt_price']} USDT" if not str(p['usdt_price']).upper().startswith("SET_") else tr(lang,"تنظیم نشده","Not configured")
        access_bits=[]
        if bool(p["vip_access"]): access_bits.append("VIP")
        if bool(p["autotrade_access"]): access_bits.append("AUTO")
        access_label=" + ".join(access_bits) or "—"
        renew=float(p["renewal_discount_percent"] or 0)
        lines.append(f"{status} <b>{escape(str(p['code']))}</b> — {p['duration_days'] or p['days']} days\nUSDT: <b>{escape(usdt)} USDT</b>\nSetup: <b>{escape(str(p['setup_fee_usdt'] or 0))} USDT</b>\nAccess: <b>{access_label}</b> | Renewal: <b>{renew:g}%</b>")
    text=tr(lang,"<b>🎟 مدیریت پلن‌ها و قیمت‌ها</b>\n\n","<b>🎟 Plans & Pricing</b>\n\n")+("\n\n".join(lines) if lines else "—")
    await screen(bot, cb.from_user.id, cb.message.chat.id, text, admin_plan_list_menu(lang))


@router.callback_query(F.data.startswith("planadm:"))
async def admin_plan_open(cb: CallbackQuery, bot: Bot, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    code=cb.data.split(":",1)[1]; lang=get_lang(cb.from_user.id); await cb.answer()
    if code == "new":
        await state.clear(); await state.set_state(Flow.admin_plan_code)
        await screen(bot,cb.from_user.id,cb.message.chat.id,tr(lang,"کد کوتاه پلن را وارد کنید. مثال: <code>365</code> یا <code>PRO90</code>","Enter a short plan code, e.g. <code>365</code> or <code>PRO90</code>"),kb(nav(lang,"admin_plans")))
        return
    p=db.get_plan(code)
    if not p:
        await screen(bot,cb.from_user.id,cb.message.chat.id,tr(lang,"پلن پیدا نشد.","Plan not found."),admin_plan_list_menu(lang)); return
    access_parts=[]
    if bool(p["vip_access"]): access_parts.append("VIP")
    if bool(p["autotrade_access"]): access_parts.append("Auto Trade")
    access_label=" + ".join(access_parts) or "—"
    text=tr(lang,
        f"<b>🎟 پلن {escape(str(p['code']))}</b>\n\nمدت: <b>{p['duration_days'] or p['days']} روز</b>\nعنوان: <b>{escape(str(p['title_fa']))}</b>\nقیمت: <b>{escape(str(p['price_usdt'] or p['usdt_price']))} USDT</b>\nSetup Fee: <b>{escape(str(p['setup_fee_usdt'] or 0))} USDT</b>\nدسترسی: <b>{escape(access_label)}</b>\nتخفیف تمدید: <b>{float(p['renewal_discount_percent'] or 0):g}٪</b>\nوضعیت: <b>{'فعال' if p['active'] else 'غیرفعال'}</b>",
        f"<b>🎟 Plan {escape(str(p['code']))}</b>\n\nDuration: <b>{p['duration_days'] or p['days']} days</b>\nTitle: <b>{escape(str(p['title_en']))}</b>\nPrice: <b>{escape(str(p['price_usdt'] or p['usdt_price']))} USDT</b>\nSetup Fee: <b>{escape(str(p['setup_fee_usdt'] or 0))} USDT</b>\nAccess: <b>{escape(access_label)}</b>\nRenewal discount: <b>{float(p['renewal_discount_percent'] or 0):g}%</b>\nStatus: <b>{'Active' if p['active'] else 'Disabled'}</b>")
    await screen(bot,cb.from_user.id,cb.message.chat.id,text,admin_plan_edit_menu(lang,str(p['code']),bool(p['active'])))


@router.callback_query(F.data.startswith("planedit:"))
async def admin_plan_edit(cb: CallbackQuery, bot: Bot, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    _,field,code=cb.data.split(":",2); lang=get_lang(cb.from_user.id)
    if field not in {"irr","usdt","setup"} or not db.get_plan(code): return
    await cb.answer(); await state.update_data(plan_edit_code=code, plan_edit_field=field)
    if field == "irr":
        await state.clear(); await cb.answer(tr(lang,"قیمت‌گذاری فقط بر اساس تتر است.","Pricing is USDT-only."), show_alert=True); return
    elif field == "setup":
        await state.set_state(Flow.admin_plan_setup)
        prompt=tr(lang,"هزینه راه‌اندازی را به تتر وارد کنید. برای رایگان بودن 0 بفرستید.","Enter Setup & Activation fee in USDT. Send 0 for free.")
    else:
        await state.set_state(Flow.admin_plan_usdt)
        prompt=tr(lang,"قیمت تتر جدید را فقط به عدد وارد کنید.","Enter the new USDT price as a number.")
    await screen(bot,cb.from_user.id,cb.message.chat.id,prompt,kb(nav(lang,f"planadm:{code}")))


@router.callback_query(F.data.startswith("plantoggle:"))
async def admin_plan_toggle(cb: CallbackQuery, bot: Bot):
    if not is_admin(cb.from_user.id): return
    code=cb.data.split(":",1)[1]; p=db.get_plan(code); lang=get_lang(cb.from_user.id)
    if not p: return
    db.set_plan_active(code,not bool(p["active"])); db.add_audit(cb.from_user.id,"plan_toggle",None,f"{code}:{int(not bool(p['active']))}")
    await cb.answer(tr(lang,"وضعیت پلن تغییر کرد ✅","Plan status updated ✅"),show_alert=True)
    fresh=db.get_plan(code)
    text=tr(lang,f"پلن <b>{escape(code)}</b> اکنون {'فعال' if fresh['active'] else 'غیرفعال'} است.",f"Plan <b>{escape(code)}</b> is now {'active' if fresh['active'] else 'disabled'}.")
    await screen(bot,cb.from_user.id,cb.message.chat.id,text,admin_plan_edit_menu(lang,code,bool(fresh['active'])))


@router.message(Flow.admin_plan_code)
async def admin_plan_code_input(message: Message, bot: Bot, state: FSMContext):
    if not is_admin(message.from_user.id): return
    raw=(message.text or "").strip().upper(); lang=get_lang(message.from_user.id); await clean_user_message(message)
    if not re.fullmatch(r"[A-Z0-9_-]{1,16}",raw) or db.get_plan(raw):
        await screen(bot,message.from_user.id,message.chat.id,tr(lang,"❌ کد نامعتبر یا تکراری است.","❌ Invalid or duplicate plan code."),kb(nav(lang,"admin_plans"))); return
    await state.update_data(new_plan_code=raw); await state.set_state(Flow.admin_plan_days)
    await screen(bot,message.from_user.id,message.chat.id,tr(lang,"مدت پلن را به روز وارد کنید. مثال: <code>30</code>","Enter plan duration in days. Example: <code>30</code>"),kb(nav(lang,"admin_plans")))


@router.message(Flow.admin_plan_days)
async def admin_plan_days_input(message: Message, bot: Bot, state: FSMContext):
    if not is_admin(message.from_user.id): return
    raw=(message.text or "").strip(); lang=get_lang(message.from_user.id); await clean_user_message(message)
    if not raw.isdigit() or not (1 <= int(raw) <= 3650):
        await screen(bot,message.from_user.id,message.chat.id,tr(lang,"❌ تعداد روز معتبر نیست.","❌ Invalid number of days."),kb(nav(lang,"admin_plans"))); return
    await state.update_data(new_plan_days=int(raw)); await state.set_state(Flow.admin_plan_title_fa)
    await screen(bot,message.from_user.id,message.chat.id,"عنوان فارسی پلن را وارد کنید.",kb(nav(lang,"admin_plans")))


@router.message(Flow.admin_plan_title_fa)
async def admin_plan_title_fa_input(message: Message, bot: Bot, state: FSMContext):
    if not is_admin(message.from_user.id): return
    title=(message.text or "").strip()[:80]; lang=get_lang(message.from_user.id); await clean_user_message(message)
    if not title: return
    await state.update_data(new_plan_title_fa=title); await state.set_state(Flow.admin_plan_title_en)
    await screen(bot,message.from_user.id,message.chat.id,tr(lang,"عنوان انگلیسی پلن را وارد کنید.","Enter the English plan title."),kb(nav(lang,"admin_plans")))


@router.message(Flow.admin_plan_title_en)
async def admin_plan_title_en_input(message: Message, bot: Bot, state: FSMContext):
    if not is_admin(message.from_user.id): return
    title=(message.text or "").strip()[:80]; lang=get_lang(message.from_user.id); await clean_user_message(message)
    if not title: return
    await state.update_data(new_plan_title_en=title); await state.set_state(Flow.admin_plan_usdt)
    await screen(bot,message.from_user.id,message.chat.id,tr(lang,"قیمت پلن را فقط به تتر وارد کنید.","Enter the plan price in USDT only."),kb(nav(lang,"admin_plans")))


@router.message(Flow.admin_plan_irr)
async def admin_plan_irr_input(message: Message, bot: Bot, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await clean_user_message(message)
    await screen(bot,message.from_user.id,message.chat.id,tr(get_lang(message.from_user.id),"قیمت ریالی حذف شده است؛ قیمت فقط با تتر ثبت می‌شود.","IRR fixed pricing has been removed; plans are priced only in USDT."),kb(nav(get_lang(message.from_user.id),"admin_plans")))


@router.message(Flow.admin_plan_usdt)
async def admin_plan_usdt_input(message: Message, bot: Bot, state: FSMContext):
    if not is_admin(message.from_user.id): return
    raw=(message.text or "").strip(); lang=get_lang(message.from_user.id); await clean_user_message(message); data=await state.get_data()
    value="SET_PRICE" if raw in {"-","—",""} else raw.replace(",",".")
    if value != "SET_PRICE":
        try:
            if float(value) <= 0: raise ValueError
        except Exception:
            await screen(bot,message.from_user.id,message.chat.id,tr(lang,"❌ قیمت تتر معتبر نیست.","❌ Invalid USDT price."),kb(nav(lang,"admin_plans"))); return
    if data.get("plan_edit_field") == "usdt":
        code=str(data["plan_edit_code"]); db.update_plan_price(code,"usdt",value); db.add_audit(message.from_user.id,"plan_price_usdt",None,f"{code}:{value}"); await state.clear()
        p=db.get_plan(code); await screen(bot,message.from_user.id,message.chat.id,tr(lang,"✅ قیمت تتر اصلاح شد.","✅ USDT price updated."),admin_plan_edit_menu(lang,code,bool(p['active']))); return
    await state.update_data(new_plan_usdt=value); await state.set_state(Flow.admin_plan_setup)
    await screen(bot,message.from_user.id,message.chat.id,tr(lang,"هزینه راه‌اندازی را به تتر وارد کنید. برای رایگان بودن 0 بفرستید.","Enter Setup & Activation fee in USDT. Send 0 for free."),kb(nav(lang,"admin_plans")))


@router.message(Flow.admin_plan_setup)
async def admin_plan_setup_input(message: Message, bot: Bot, state: FSMContext):
    if not is_admin(message.from_user.id): return
    raw=(message.text or "").strip().replace(",","."); lang=get_lang(message.from_user.id); await clean_user_message(message); data=await state.get_data()
    try:
        amount=float(raw);
        if amount < 0: raise ValueError
    except Exception:
        await screen(bot,message.from_user.id,message.chat.id,tr(lang,"❌ هزینه راه‌اندازی معتبر نیست.","❌ Invalid Setup Fee."),kb(nav(lang,"admin_plans"))); return
    if data.get("plan_edit_field") == "setup":
        code=str(data["plan_edit_code"]); db.update_plan_setup_fee(code,raw); db.add_audit(message.from_user.id,"plan_setup_fee",None,f"{code}:{raw}"); await state.clear(); p=db.get_plan(code)
        await screen(bot,message.from_user.id,message.chat.id,tr(lang,"✅ هزینه راه‌اندازی اصلاح شد.","✅ Setup Fee updated."),admin_plan_edit_menu(lang,code,bool(p['active']))); return
    d=dict(data)
    usdt=str(d.get("new_plan_usdt","0"))
    code=str(d["new_plan_code"]).upper()
    auto=code.startswith(("AUTO", "AEX"))
    bundle=code.startswith("AUTO")
    db.create_plan(
        code,
        int(d["new_plan_days"]),
        str(d["new_plan_title_fa"]),
        str(d["new_plan_title_en"]),
        "",
        usdt,
        vip_access=(not auto or bundle),
        autotrade_access=auto,
        service_type=("auto_trade" if auto else "signal"),
        setup_fee_usdt=raw,
    )
    db.add_audit(message.from_user.id,"plan_create",None,code); await state.clear(); await screen(bot,message.from_user.id,message.chat.id,tr(lang,"✅ پلن جدید ساخته شد.","✅ New plan created."),admin_plan_list_menu(lang))


@router.callback_query(F.data == "admin_rewards")
async def admin_rewards(cb: CallbackQuery, bot: Bot):
    if not is_admin(cb.from_user.id): return
    lang=get_lang(cb.from_user.id); await cb.answer()
    reward=int(db.get_setting("referral_points_per_success","100")); rate=int(db.get_setting("points_per_percent","100")); cap=int(db.get_setting("max_points_discount_percent","30"))
    text=tr(lang, f"<b>🎁 رفرال و امتیاز</b>\n\nپاداش هر دعوت موفق: <b>{reward} Points</b>\nنرخ تبدیل: <b>{rate} Points = 1% تخفیف</b>\nسقف تخفیف امتیازی: <b>{cap}%</b>", f"<b>🎁 Referrals & Points</b>\n\nReward per successful referral: <b>{reward} Points</b>\nConversion: <b>{rate} Points = 1% discount</b>\nPoints-discount cap: <b>{cap}%</b>")
    await screen(bot, cb.from_user.id, cb.message.chat.id, text, reward_settings_menu(lang))


async def ask_reward_value(cb: CallbackQuery, bot: Bot, state: FSMContext, mode: str):
    lang=get_lang(cb.from_user.id); await state.set_state(Flow.admin_reward_value); await state.update_data(reward_mode=mode); await cb.answer()
    prompts={
        "ref": tr(lang,"مقدار امتیاز برای هر دعوت موفق را به عدد ارسال کنید. مثال: 100","Send points awarded per successful referral. Example: 100"),
        "rate": tr(lang,"تعداد امتیاز لازم برای ۱٪ تخفیف را ارسال کنید. مثال: 100","Send points required for 1% discount. Example: 100"),
        "cap": tr(lang,"سقف تخفیف امتیازی هر خرید را به درصد ارسال کنید. مثال: 30","Send the maximum points discount per purchase as a percentage. Example: 30"),
    }
    await screen(bot,cb.from_user.id,cb.message.chat.id,"<b>⚙️</b>\n\n"+prompts[mode],kb(nav(lang,"admin_rewards")))


@router.callback_query(F.data == "reward_set_ref")
async def reward_set_ref(cb: CallbackQuery, bot: Bot, state: FSMContext): await ask_reward_value(cb,bot,state,"ref")
@router.callback_query(F.data == "reward_set_rate")
async def reward_set_rate(cb: CallbackQuery, bot: Bot, state: FSMContext): await ask_reward_value(cb,bot,state,"rate")
@router.callback_query(F.data == "reward_set_cap")
async def reward_set_cap(cb: CallbackQuery, bot: Bot, state: FSMContext): await ask_reward_value(cb,bot,state,"cap")


@router.message(Flow.admin_reward_value)
async def reward_value(message: Message, bot: Bot, state: FSMContext):
    if not is_admin(message.from_user.id): return
    lang=get_lang(message.from_user.id); raw=(message.text or "").strip(); await clean_user_message(message)
    if not raw.isdigit() or int(raw)<=0:
        await screen(bot,message.from_user.id,message.chat.id,tr(lang,"❌ فقط عدد صحیح مثبت ارسال کنید.","❌ Send a positive integer only."),kb(nav(lang,"admin_rewards"))); return
    value=int(raw); data=await state.get_data(); mode=data.get("reward_mode")
    if mode=="cap" and value>100:
        await screen(bot,message.from_user.id,message.chat.id,tr(lang,"❌ سقف درصد نمی‌تواند بیشتر از 100 باشد.","❌ Percentage cap cannot exceed 100."),kb(nav(lang,"admin_rewards"))); return
    key={"ref":"referral_points_per_success","rate":"points_per_percent","cap":"max_points_discount_percent"}.get(mode)
    if key: db.set_setting(key,str(value))
    await state.clear(); await screen(bot,message.from_user.id,message.chat.id,tr(lang,"✅ تنظیمات ذخیره شد.","✅ Settings saved."),kb(nav(lang,"admin")))


@router.callback_query(F.data == "admin_discounts")
async def admin_discounts(cb: CallbackQuery, bot: Bot, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    await state.clear(); lang=get_lang(cb.from_user.id); await cb.answer()
    await screen(bot,cb.from_user.id,cb.message.chat.id,tr(lang,"<b>🏷 مدیریت تخفیف‌ها</b>\n\nکدهای تخفیف مناسبتی را از این بخش ایجاد و مدیریت کنید.","<b>🏷 Discount Management</b>\n\nCreate and manage seasonal promo codes here."),discounts_menu(lang))


@router.callback_query(F.data == "discount_list")
async def discount_list(cb: CallbackQuery, bot: Bot):
    if not is_admin(cb.from_user.id): return
    lang=get_lang(cb.from_user.id); rows=db.list_discounts(); await cb.answer(); lines=[]; buttons=[]
    for d in rows[:12]:
        status="✅" if d["active"] else "❌"; maxuses="∞" if d["max_uses"] is None else str(d["max_uses"]); lines.append(f"{status} <code>{escape(d['code'])}</code> — {d['percent']:g}% — {d['used_count']}/{maxuses} — {fmt_dt(d['expires_at'])}")
        buttons.append([(f"{'⛔' if d['active'] else '✅'} {d['code']}", f"discount_toggle:{d['id']}")])
    buttons += nav(lang,"admin_discounts")
    text=tr(lang,"<b>📋 تخفیف‌ها</b>\n\n","<b>📋 Discounts</b>\n\n")+("\n".join(lines) if lines else tr(lang,"هنوز کدی ساخته نشده است.","No promo codes created yet."))
    await screen(bot,cb.from_user.id,cb.message.chat.id,text,kb(buttons))


@router.callback_query(F.data.startswith("discount_toggle:"))
async def discount_toggle(cb: CallbackQuery, bot: Bot):
    if not is_admin(cb.from_user.id): return
    lang=get_lang(cb.from_user.id); did=int(cb.data.split(":",1)[1])
    row=next((d for d in db.list_discounts(100) if int(d["id"])==did),None)
    if not row:
        await cb.answer(tr(lang,"کد پیدا نشد.","Discount not found."),show_alert=True); return
    if row["active"]:
        db.disable_discount(did); await cb.answer(tr(lang,"تخفیف غیرفعال شد.","Discount disabled."),show_alert=True)
    else:
        now_utc = datetime.now(timezone.utc)
        expired = bool(row["expires_at"] and datetime.fromisoformat(row["expires_at"]) <= now_utc)
        exhausted = bool(row["max_uses"] is not None and int(row["used_count"]) >= int(row["max_uses"]))
        if expired:
            await cb.answer(tr(lang,"این تخفیف منقضی شده و قابل فعال‌سازی مجدد نیست.","This discount is expired and cannot be re-enabled."),show_alert=True); return
        if exhausted:
            await cb.answer(tr(lang,"سقف استفاده این تخفیف تکمیل شده است.","This discount has reached its usage limit."),show_alert=True); return
        db.set_discount_active(did, True); await cb.answer(tr(lang,"تخفیف فعال شد.","Discount enabled."),show_alert=True)
    rows=db.list_discounts(); lines=[]; buttons=[]
    for d in rows[:12]:
        status="✅" if d["active"] else "❌"; maxuses="∞" if d["max_uses"] is None else str(d["max_uses"]); lines.append(f"{status} <code>{escape(d['code'])}</code> — {d['percent']:g}% — {d['used_count']}/{maxuses} — {fmt_dt(d['expires_at'])}")
        buttons.append([(f"{'⛔' if d['active'] else '✅'} {d['code']}", f"discount_toggle:{d['id']}")])
    buttons += nav(lang,"admin_discounts")
    text=tr(lang,"<b>📋 تخفیف‌ها</b>\n\n","<b>📋 Discounts</b>\n\n")+("\n".join(lines) if lines else tr(lang,"هنوز کدی ساخته نشده است.","No promo codes created yet."))
    await screen(bot,cb.from_user.id,cb.message.chat.id,text,kb(buttons))


@router.callback_query(F.data == "discount_create")
async def discount_create(cb: CallbackQuery, bot: Bot, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    lang=get_lang(cb.from_user.id); await state.set_state(Flow.admin_discount_code); await cb.answer()
    await screen(bot,cb.from_user.id,cb.message.chat.id,tr(lang,"<b>➕ ساخت تخفیف</b>\n\nکد تخفیف را ارسال کنید. مثال: <code>NOWRUZ20</code>","<b>➕ Create Discount</b>\n\nSend the promo code. Example: <code>NOWRUZ20</code>"),kb(nav(lang,"admin_discounts")))


@router.message(Flow.admin_discount_code)
async def discount_code_input(message: Message, bot: Bot, state: FSMContext):
    if not is_admin(message.from_user.id): return
    lang=get_lang(message.from_user.id); code=re.sub(r"[^A-Za-z0-9_-]","",(message.text or "").upper())[:32]; await clean_user_message(message)
    if len(code)<3 or db.get_discount_by_code(code):
        await screen(bot,message.from_user.id,message.chat.id,tr(lang,"❌ کد نامعتبر است یا قبلاً وجود دارد. کد دیگری ارسال کنید.","❌ Invalid or duplicate code. Send another code."),kb(nav(lang,"admin_discounts"))); return
    await state.update_data(discount_code=code); await state.set_state(Flow.admin_discount_percent)
    await screen(bot,message.from_user.id,message.chat.id,tr(lang,f"کد: <code>{code}</code>\n\nدرصد تخفیف را ارسال کنید. مثال: <b>20</b>",f"Code: <code>{code}</code>\n\nSend discount percentage. Example: <b>20</b>"),kb(nav(lang,"admin_discounts")))


@router.message(Flow.admin_discount_percent)
async def discount_percent_input(message: Message, bot: Bot, state: FSMContext):
    if not is_admin(message.from_user.id): return
    lang=get_lang(message.from_user.id); raw=(message.text or "").strip(); await clean_user_message(message)
    try: pct=float(raw)
    except ValueError: pct=-1
    if not (0 < pct <= 100):
        await screen(bot,message.from_user.id,message.chat.id,tr(lang,"❌ درصد باید بین 0 تا 100 باشد.","❌ Percentage must be between 0 and 100."),kb(nav(lang,"admin_discounts"))); return
    await state.update_data(discount_percent=pct); await state.set_state(Flow.admin_discount_days)
    await screen(bot,message.from_user.id,message.chat.id,tr(lang,"تخفیف چند روز فعال باشد؟ مثال: <b>7</b>","How many days should this promo remain active? Example: <b>7</b>"),kb(nav(lang,"admin_discounts")))


@router.message(Flow.admin_discount_days)
async def discount_days_input(message: Message, bot: Bot, state: FSMContext):
    if not is_admin(message.from_user.id): return
    lang=get_lang(message.from_user.id); raw=(message.text or "").strip(); await clean_user_message(message)
    if not raw.isdigit() or int(raw)<=0:
        await screen(bot,message.from_user.id,message.chat.id,tr(lang,"❌ تعداد روز معتبر نیست.","❌ Invalid number of days."),kb(nav(lang,"admin_discounts"))); return
    await state.update_data(discount_days=int(raw)); await state.set_state(Flow.admin_discount_max)
    await screen(bot,message.from_user.id,message.chat.id,tr(lang,"حداکثر چند بار قابل استفاده باشد؟ برای نامحدود عدد <b>0</b> بفرستید.","Maximum number of uses? Send <b>0</b> for unlimited."),kb(nav(lang,"admin_discounts")))


@router.message(Flow.admin_discount_max)
async def discount_max_input(message: Message, bot: Bot, state: FSMContext):
    if not is_admin(message.from_user.id): return
    lang=get_lang(message.from_user.id); raw=(message.text or "").strip(); await clean_user_message(message)
    if not raw.isdigit():
        await screen(bot,message.from_user.id,message.chat.id,tr(lang,"❌ فقط عدد ارسال کنید.","❌ Send a number only."),kb(nav(lang,"admin_discounts"))); return
    data=await state.get_data(); max_uses=int(raw) or None
    try:
        db.create_discount(data["discount_code"],float(data["discount_percent"]),int(data["discount_days"]),max_uses,message.from_user.id)
    except Exception as exc:
        log.exception("create discount failed"); await state.clear(); await screen(bot,message.from_user.id,message.chat.id,tr(lang,f"❌ ساخت تخفیف ناموفق بود: {escape(str(exc))}",f"❌ Could not create discount: {escape(str(exc))}"),kb(nav(lang,"admin"))); return
    await state.clear(); await screen(bot,message.from_user.id,message.chat.id,tr(lang,f"✅ کد <code>{escape(data['discount_code'])}</code> با تخفیف <b>{float(data['discount_percent']):g}٪</b> ساخته شد.",f"✅ Promo <code>{escape(data['discount_code'])}</code> created with <b>{float(data['discount_percent']):g}%</b> discount."),kb(nav(lang,"admin_discounts")))


@router.callback_query(F.data == "autotrade_submit_account")
async def autotrade_submit_account(cb: CallbackQuery, bot: Bot, state: FSMContext):
    if not await gated(cb, bot): return
    lang=get_lang(cb.from_user.id)
    await state.set_state(Flow.autotrade_initial_account)
    await cb.answer()
    await screen(bot,cb.from_user.id,cb.message.chat.id,tr(
        lang,
        "<b>📌 ثبت حساب MetaTrader 5</b>\n\nشماره حساب MT5 خود را ارسال کنید.",
        "<b>📌 Register MetaTrader 5 Account</b>\n\nSend your MT5 account number."
    ),kb(nav(lang,"client_autotrade_access")))

@router.message(Flow.autotrade_initial_account)
async def autotrade_initial_account_input(message: Message, bot: Bot, state: FSMContext):
    uid=int(message.from_user.id); lang=get_lang(uid); raw=(message.text or "").strip()
    await clean_user_message(message)
    if not raw.isdigit() or not (3 <= len(raw) <= 20):
        await screen(bot,uid,message.chat.id,tr(lang,"❌ شماره حساب MT5 معتبر نیست.","❌ Invalid MT5 account number."),kb(nav(lang,"client_autotrade_access"))); return
    try:
        lic=db.issue_autotrade_license_for_account(uid,raw)
        db.add_audit(uid,"mt5_account_bound_and_license_issued",int(lic["id"]),f"account={raw}")
        await state.clear()
        await screen(bot,uid,message.chat.id,tr(
            lang,
            f"✅ حساب MT5 ثبت شد و لایسنس اختصاصی صادر شد.\n\nحساب: <code>{escape(raw)}</code>\nلایسنس: <code>{escape(str(lic['license_key']))}</code>\nاعتبار تا: <b>{fmt_dt(lic['autotrade_expires_at'])}</b>",
            f"✅ MT5 account registered and dedicated License issued.\n\nAccount: <code>{escape(raw)}</code>\nLicense: <code>{escape(str(lic['license_key']))}</code>\nValid until: <b>{fmt_dt(lic['autotrade_expires_at'])}</b>"
        ),autotrade_user_menu(lang,mt5_connected=False))
    except Exception as exc:
        await state.clear()
        await screen(bot,uid,message.chat.id,tr(lang,f"❌ صدور لایسنس ناموفق بود:\n<code>{escape(str(exc))}</code>",f"❌ License issuance failed:\n<code>{escape(str(exc))}</code>"),autotrade_user_menu(lang,mt5_connected=False))

@router.callback_query(F.data == "autotrade_account_change")
async def autotrade_account_change(cb: CallbackQuery, bot: Bot, state: FSMContext):
    if not await gated(cb, bot): return
    uid=int(cb.from_user.id); lang=get_lang(uid); current=db.mt5_account(uid)
    if not current:
        await cb.answer(tr(lang,"حساب MT5 فعالی برای تغییر وجود ندارد.","No active MT5 account is linked."), show_alert=True); return
    await state.set_state(Flow.autotrade_account_change)
    await cb.answer()
    await screen(bot, uid, cb.message.chat.id, tr(
        lang,
        f"<b>🔄 درخواست تغییر حساب MT5</b>\n\nحساب فعلی: <code>{escape(str(current['account_number']))}</code>\n\nشماره حساب جدید را ارسال کنید.\n\n⚠️ حساب جدید پس از تأیید ادمین فعال می‌شود و حساب قبلی تا آن زمان فعال باقی می‌ماند.",
        f"<b>🔄 Change MT5 Account</b>\n\nCurrent account: <code>{escape(str(current['account_number']))}</code>\n\nSend the new MT5 account number.\n\n⚠️ The new account becomes active only after admin approval; the current account remains active until then."
    ), kb(nav(lang,"client_autotrade_access")))

@router.message(Flow.autotrade_account_change)
async def autotrade_account_change_input(message: Message, bot: Bot, state: FSMContext):
    uid=int(message.from_user.id); lang=get_lang(uid); raw=(message.text or "").strip()
    await clean_user_message(message)
    if not raw.isdigit() or not (3 <= len(raw) <= 20):
        await screen(bot,uid,message.chat.id,tr(lang,"❌ شماره حساب MT5 معتبر نیست.","❌ Invalid MT5 account number."),kb(nav(lang,"client_autotrade_access"))); return
    try:
        current=db.mt5_account(uid)
        if not current:
            raise ValueError("no active MT5 account is linked")
        req=db.request_mt5_account_change(uid,raw,None,None,"Customer requested account change")
        db.add_audit(uid,"mt5_account_change_requested",int(req["id"]),f"{current['account_number']} -> {raw}")
        for admin_id in settings.admin_ids:
            try:
                await bot.send_message(admin_id,
                    f"🔄 <b>MT5 Account Change Request</b>\n\nUser: <code>{uid}</code>\nCurrent: <code>{escape(str(current['account_number']))}</code>\nNew: <code>{escape(raw)}</code>\nRequest: <code>#{int(req['id'])}</code>",
                    parse_mode=ParseMode.HTML,
                    reply_markup=kb([[("✅ Review", f"admin_mt5_change:{int(req['id'])}")]]))
            except Exception:
                log.exception("Could not notify admin about MT5 account change request")
        await state.clear()
        await screen(bot,uid,message.chat.id,tr(
            lang,
            f"✅ درخواست تغییر حساب ثبت شد.\n\nحساب فعلی: <code>{escape(str(current['account_number']))}</code>\nحساب جدید: <code>{escape(raw)}</code>\n\n⏳ پس از بررسی و تأیید ادمین، حساب جدید فعال خواهد شد.",
            f"✅ Account change request submitted.\n\nCurrent: <code>{escape(str(current['account_number']))}</code>\nNew: <code>{escape(raw)}</code>\n\n⏳ The new account will become active after admin approval."
        ),autotrade_user_menu(lang,mt5_connected=True))
    except Exception as exc:
        await state.clear()
        await screen(bot,uid,message.chat.id,tr(lang,f"❌ ثبت درخواست ناموفق بود:\n<code>{escape(str(exc))}</code>",f"❌ Request failed:\n<code>{escape(str(exc))}</code>"),autotrade_user_menu(lang,mt5_connected=True))

@router.callback_query(F.data == "admin_autotrade")
async def admin_autotrade(cb: CallbackQuery, bot: Bot):
    if not is_admin(cb.from_user.id): return
    lang=get_lang(cb.from_user.id); await cb.answer()
    count=db.autotrade_waitlist_count(); rows=db.autotrade_waitlist_users(10)
    names="\n".join(f"• @{r['username']}" if r['username'] else f"• {r['telegram_id']}" for r in rows) or "—"
    requests=db.pending_mt5_account_change_requests()
    req_lines=[]
    for r in requests[:10]:
        req_lines.append(f"• #{r['id']} — {r['telegram_id']}: {r['old_account_number']} → {r['new_account_number']}")
    req_text="\n".join(req_lines) or "—"
    markup=kb([[("🔄 درخواست‌های تغییر حساب", "admin_mt5_account_changes")], *nav(lang,"admin")])
    await screen(bot,cb.from_user.id,cb.message.chat.id,tr(lang,
        f"<b>🤖 NEXUS AUTO TRADE</b>\n\n🔔 لیست انتظار: <b>{count}</b>\n\n<b>درخواست‌های تغییر حساب:</b>\n{escape(req_text)}",
        f"<b>🤖 NEXUS AUTO TRADE</b>\n\n🔔 Waitlist: <b>{count}</b>\n\n<b>Account change requests:</b>\n{escape(req_text)}"),markup)

@router.callback_query(F.data == "admin_mt5_account_changes")
async def admin_mt5_account_changes(cb: CallbackQuery, bot: Bot):
    if not is_admin(cb.from_user.id): return
    lang=get_lang(cb.from_user.id); await cb.answer()
    rows=db.pending_mt5_account_change_requests()
    if not rows:
        await screen(bot,cb.from_user.id,cb.message.chat.id,tr(lang,"درخواستی وجود ندارد.","No pending requests."),kb(nav(lang,"admin_autotrade"))); return
    buttons=[]
    for r in rows[:20]:
        buttons.append([(f"#{r['id']} | {r['old_account_number']} → {r['new_account_number']}",f"admin_mt5_change:{r['id']}")])
    buttons += nav(lang,"admin_autotrade")
    await screen(bot,cb.from_user.id,cb.message.chat.id,tr(lang,"<b>درخواست‌های تغییر حساب MT5</b>","<b>MT5 Account Change Requests</b>"),kb(buttons))

@router.callback_query(F.data.startswith("admin_mt5_change:"))
async def admin_mt5_change(cb: CallbackQuery, bot: Bot):
    if not is_admin(cb.from_user.id): return
    rid=int(cb.data.split(":",1)[1]); rows=[r for r in db.pending_mt5_account_change_requests() if int(r["id"])==rid]
    lang=get_lang(cb.from_user.id)
    if not rows:
        await cb.answer(tr(lang,"درخواست پیدا نشد.","Request not found."),show_alert=True); return
    r=rows[0]; await cb.answer()
    markup=kb([[("✅ تأیید تغییر",f"admin_mt5_change_review:{rid}:approve"),("❌ رد درخواست",f"admin_mt5_change_review:{rid}:reject")]]+nav(lang,"admin_mt5_account_changes"))
    await screen(bot,cb.from_user.id,cb.message.chat.id,tr(lang,
        f"<b>درخواست تغییر حساب #{rid}</b>\n\nکاربر: <code>{r['telegram_id']}</code>\nحساب فعلی: <code>{r['old_account_number']}</code>\nحساب جدید: <code>{r['new_account_number']}</code>",
        f"<b>Account change #{rid}</b>\n\nUser: <code>{r['telegram_id']}</code>\nCurrent: <code>{r['old_account_number']}</code>\nNew: <code>{r['new_account_number']}</code>"),markup)

@router.callback_query(F.data.startswith("admin_mt5_change_review:"))
async def admin_mt5_change_review(cb: CallbackQuery, bot: Bot):
    if not is_admin(cb.from_user.id): return
    _,rid,decision=cb.data.split(":",2); rid=int(rid); approve=decision=="approve"; lang=get_lang(cb.from_user.id)
    try:
        row=db.review_mt5_account_change(rid,int(cb.from_user.id),approve,"Approved by admin" if approve else "Rejected by admin")
        db.add_audit(int(cb.from_user.id),"mt5_account_change_reviewed",rid,f"status={row['status']} old={row['old_account_number']} new={row['new_account_number']}")
        target=int(row["telegram_id"])
        customer_lang=get_lang(target)
        if approve:
            notice=tr(customer_lang,
                f"✅ درخواست تغییر حساب تأیید شد.\n\nحساب جدید: <code>{escape(str(row['new_account_number']))}</code>\nلایسنس AutoTrade اکنون به حساب جدید متصل است.",
                f"✅ Your account change was approved.\n\nNew account: <code>{escape(str(row['new_account_number']))}</code>\nYour AutoTrade license is now bound to the new account.")
        else:
            notice=tr(customer_lang,
                f"❌ درخواست تغییر حساب رد شد.\n\nحساب فعلی شما همچنان <code>{escape(str(row['old_account_number']))}</code> است.",
                f"❌ Your account change request was rejected.\n\nYour current account remains <code>{escape(str(row['old_account_number']))}</code>.")
        await bot.send_message(target,notice,parse_mode=ParseMode.HTML)
    except Exception as exc:
        await cb.answer(tr(lang,f"خطا: {exc}",f"Error: {exc}"),show_alert=True); return
    await cb.answer(tr(lang,"انجام شد.","Done."))
    await admin_mt5_account_changes(cb,bot)

@router.callback_query(F.data.startswith("discount:campaign:"))
async def discount_campaign(cb: CallbackQuery, bot: Bot, state: FSMContext):
    if not await gated(cb, bot): return
    lang = get_lang(cb.from_user.id)
    try:
        _, _, code, campaign_id = cb.data.split(":", 3)
        campaign_id = int(campaign_id)
    except Exception:
        await cb.answer(tr(lang, "کمپین نامعتبر است.", "Invalid campaign."), show_alert=True); return
    campaign = db.best_campaign(cb.from_user.id, code)
    if not campaign or int(campaign["id"]) != campaign_id:
        await cb.answer(tr(lang, "این کمپین دیگر برای شما فعال نیست.", "This campaign is no longer available for you."), show_alert=True); return
    await state.update_data(plan_code=code, discount_percent=float(campaign["percent"]), promo_code=None, promo_id=None, points_used=0, campaign_id=campaign_id)
    await cb.answer(tr(lang, f"کمپین {campaign['percent']:g}٪ اعمال شد 🎯", f"{campaign['percent']:g}% campaign applied 🎯"), show_alert=True)
    await show_payment_methods(cb, bot, state, code)


@router.message(Flow.waiting_usdt_txid)
async def receive_usdt_txid(message: Message, bot: Bot, state: FSMContext):
    lang = get_lang(message.from_user.id)
    txid = (message.text or "").strip()
    await clean_user_message(message)
    if not re.fullmatch(r"(?:0x)?[A-Fa-f0-9]{64}", txid):
        await screen(bot, message.from_user.id, message.chat.id, tr(lang, "❌ TXID معتبر نیست. هش تراکنش 64 کاراکتری را ارسال کنید.", "❌ Invalid TXID. Send the 64-character transaction hash."), kb(nav(lang, "vip")))
        return
    invoice_id = (await state.get_data()).get("invoice_id")
    invoice = db.get_invoice(int(invoice_id)) if invoice_id else None
    if not invoice or str(invoice["payment_status"]) != "pending":
        await screen(bot, message.from_user.id, message.chat.id, tr(lang,"❌ فاکتور معتبر نیست؛ فاکتور جدید ایجاد کنید.","❌ The invoice is not valid; create a new invoice."), kb(nav(lang,"vip"))); return
    if db.txid_exists(txid):
        await screen(bot, message.from_user.id, message.chat.id, tr(lang, "⛔ این TXID قبلاً در سیستم ثبت شده است و دوباره قابل استفاده نیست.", "⛔ This TXID has already been registered and cannot be reused."), kb(nav(lang, "vip")))
        return
    await state.update_data(txid=txid)
    await state.set_state(Flow.waiting_receipt)
    await screen(bot, message.from_user.id, message.chat.id, tr(lang, f"✅ TXID ثبت شد:\n<code>{escape(txid)}</code>\n\nحالا تصویر رسید پرداخت USDT را ارسال کنید.", f"✅ TXID registered:\n<code>{escape(txid)}</code>\n\nNow send the USDT payment receipt image."), kb(nav(lang, "vip")))


@router.callback_query(F.data == "ref_leaderboard")
async def referral_leaderboard(cb: CallbackQuery, bot: Bot):
    if not await gated(cb, bot): return
    lang=get_lang(cb.from_user.id); await cb.answer()
    monthly=db.referral_leaderboard(10, monthly=True)
    alltime=db.referral_leaderboard(10, monthly=False)
    def render(rows):
        out=[]; medals=["🥇","🥈","🥉"]
        for i,r in enumerate(rows):
            name=("@"+r["username"]) if r["username"] else (r["first_name"] or str(r["telegram_id"]))
            prefix=medals[i] if i<3 else f"{i+1}."
            out.append(f"{prefix} {escape(name)} — <b>{int(r['referrals'])}</b> / ⭐ {int(r['points'] or 0)}")
        return "\n".join(out) or tr(lang,"هنوز دعوت موفقی ثبت نشده است.","No successful referrals yet.")
    text=tr(lang, f"<b>🏆 رتبه‌بندی دعوت NEXUS</b>\n\n<b>این ماه:</b>\n{render(monthly)}\n\n<b>کل دوره:</b>\n{render(alltime)}", f"<b>🏆 NEXUS Referral Leaderboard</b>\n\n<b>This month:</b>\n{render(monthly)}\n\n<b>All time:</b>\n{render(alltime)}")
    await screen(bot,cb.from_user.id,cb.message.chat.id,text,kb(nav(lang,"referral")))


@router.callback_query(F.data == "admin_campaigns")
async def admin_campaigns(cb: CallbackQuery, bot: Bot, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    await state.clear(); lang=get_lang(cb.from_user.id); await cb.answer()
    await screen(bot,cb.from_user.id,cb.message.chat.id,tr(lang,"<b>🎯 کمپین Engine</b>\n\nتخفیف‌های خودکار مناسبتی را برای همه یا گروه مشخصی از کاربران و پلن‌ها ایجاد کنید.","<b>🎯 Campaign Engine</b>\n\nCreate automatic seasonal discounts for selected users and plans."),campaign_menu(lang))


@router.callback_query(F.data == "campaign_list")
async def campaign_list(cb: CallbackQuery, bot: Bot):
    if not is_admin(cb.from_user.id): return
    lang=get_lang(cb.from_user.id); await cb.answer(); rows=db.list_campaigns(20); lines=[]; buttons=[]
    for c in rows[:12]:
        status="✅" if c["active"] else "❌"; plan=c["plan_code"] or "ALL"; limit="∞" if c["max_uses"] is None else str(c["max_uses"])
        title=c["title_fa"] if lang=="fa" else c["title_en"]
        lines.append(f"{status} <b>{escape(title)}</b> — {c['percent']:g}% — {plan} — {c['audience']} — {c['used_count']}/{limit} — {fmt_dt(c['expires_at'])}")
        buttons.append([(f"{'⛔' if c['active'] else '✅'} #{c['id']}",f"campaign_toggle:{c['id']}")])
    buttons += nav(lang,"admin_campaigns")
    await screen(bot,cb.from_user.id,cb.message.chat.id,tr(lang,"<b>📋 کمپین‌ها</b>\n\n","<b>📋 Campaigns</b>\n\n")+("\n".join(lines) if lines else tr(lang,"کمپینی وجود ندارد.","No campaigns yet.")),kb(buttons))


@router.callback_query(F.data.startswith("campaign_toggle:"))
async def campaign_toggle(cb: CallbackQuery, bot: Bot):
    if not is_admin(cb.from_user.id): return
    cid=int(cb.data.split(":",1)[1]); rows=db.list_campaigns(100); row=next((x for x in rows if int(x["id"])==cid),None); lang=get_lang(cb.from_user.id)
    if not row:
        await cb.answer(tr(lang,"کمپین پیدا نشد.","Campaign not found."),show_alert=True); return
    db.set_campaign_active(cid,not bool(row["active"])); await cb.answer(tr(lang,"وضعیت تغییر کرد.","Status changed."),show_alert=True)
    rows=db.list_campaigns(20); lines=[]; buttons=[]
    for c in rows[:12]:
        status="✅" if c["active"] else "❌"; title=c["title_fa"] if lang=="fa" else c["title_en"]; plan=c["plan_code"] or "ALL"; limit="∞" if c["max_uses"] is None else str(c["max_uses"])
        lines.append(f"{status} <b>{escape(title)}</b> — {c['percent']:g}% — {plan} — {c['audience']} — {c['used_count']}/{limit}")
        buttons.append([(f"{'⛔' if c['active'] else '✅'} #{c['id']}",f"campaign_toggle:{c['id']}")])
    buttons += nav(lang,"admin_campaigns")
    await screen(bot,cb.from_user.id,cb.message.chat.id,tr(lang,"<b>📋 کمپین‌ها</b>\n\n","<b>📋 Campaigns</b>\n\n")+("\n".join(lines) if lines else "—"),kb(buttons))


@router.callback_query(F.data == "campaign_create")
async def campaign_create(cb: CallbackQuery, bot: Bot, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    lang=get_lang(cb.from_user.id); await state.set_state(Flow.admin_campaign_title); await cb.answer()
    await screen(bot,cb.from_user.id,cb.message.chat.id,tr(lang,"<b>➕ کمپین جدید</b>\n\nعنوان را به شکل زیر بفرستید:\n<code>عنوان فارسی | انگلیسی Title</code>","<b>➕ New Campaign</b>\n\nSend title as:\n<code>Persian Title | English Title</code>"),kb(nav(lang,"admin_campaigns")))


@router.message(Flow.admin_campaign_title)
async def campaign_title_input(message: Message, bot: Bot, state: FSMContext):
    if not is_admin(message.from_user.id): return
    lang=get_lang(message.from_user.id); raw=(message.text or "").strip(); await clean_user_message(message)
    parts=[x.strip() for x in raw.split("|",1)]
    if not parts[0]:
        await screen(bot,message.from_user.id,message.chat.id,tr(lang,"❌ عنوان معتبر نیست.","❌ Invalid title."),kb(nav(lang,"admin_campaigns"))); return
    fa=parts[0]; en=parts[1] if len(parts)>1 and parts[1] else parts[0]
    await state.update_data(campaign_title_fa=fa,campaign_title_en=en); await state.set_state(Flow.admin_campaign_percent)
    await screen(bot,message.from_user.id,message.chat.id,tr(lang,"درصد تخفیف را بفرستید. مثال: <b>20</b>","Send discount percentage. Example: <b>20</b>"),kb(nav(lang,"admin_campaigns")))


@router.message(Flow.admin_campaign_percent)
async def campaign_percent_input(message: Message, bot: Bot, state: FSMContext):
    if not is_admin(message.from_user.id): return
    lang=get_lang(message.from_user.id); await clean_user_message(message)
    try: pct=float((message.text or "").strip())
    except ValueError: pct=-1
    if not 0<pct<=100:
        await screen(bot,message.from_user.id,message.chat.id,tr(lang,"❌ درصد باید 1 تا 100 باشد.","❌ Percentage must be 1-100."),kb(nav(lang,"admin_campaigns"))); return
    await state.update_data(campaign_percent=pct); await state.set_state(Flow.admin_campaign_days)
    await screen(bot,message.from_user.id,message.chat.id,tr(lang,"کمپین چند روز فعال باشد؟","How many days should the campaign stay active?"),kb(nav(lang,"admin_campaigns")))


@router.message(Flow.admin_campaign_days)
async def campaign_days_input(message: Message, bot: Bot, state: FSMContext):
    if not is_admin(message.from_user.id): return
    lang=get_lang(message.from_user.id); raw=(message.text or "").strip(); await clean_user_message(message)
    if not raw.isdigit() or int(raw)<=0:
        await screen(bot,message.from_user.id,message.chat.id,tr(lang,"❌ تعداد روز معتبر نیست.","❌ Invalid days."),kb(nav(lang,"admin_campaigns"))); return
    await state.update_data(campaign_days=int(raw)); await state.set_state(None)
    await screen(bot,message.from_user.id,message.chat.id,tr(lang,"کمپین برای کدام پلن باشد؟","Which plan should this campaign apply to?"),campaign_plan_menu(lang))


@router.callback_query(F.data.startswith("campaign_plan:"))
async def campaign_plan_pick(cb: CallbackQuery, bot: Bot, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    plan=cb.data.split(":",1)[1]; lang=get_lang(cb.from_user.id)
    if plan != "all" and not db.get_plan(plan, active_only=True): return
    await state.update_data(campaign_plan=None if plan=="all" else plan); await cb.answer()
    await screen(bot,cb.from_user.id,cb.message.chat.id,tr(lang,"کمپین برای کدام گروه کاربران باشد؟","Which user group should receive the campaign?"),campaign_audience_menu(lang))


@router.callback_query(F.data.startswith("campaign_aud:"))
async def campaign_audience_pick(cb: CallbackQuery, bot: Bot, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    aud=cb.data.split(":",1)[1]; lang=get_lang(cb.from_user.id)
    if aud not in {"all","vip","nonvip","expired"}: return
    await state.update_data(campaign_audience=aud); await state.set_state(Flow.admin_campaign_max); await cb.answer()
    await screen(bot,cb.from_user.id,cb.message.chat.id,tr(lang,"حداکثر استفاده کل کمپین را بفرستید؛ برای نامحدود <b>0</b>.","Send maximum total uses; <b>0</b> for unlimited."),kb(nav(lang,"admin_campaigns")))


@router.message(Flow.admin_campaign_max)
async def campaign_max_input(message: Message, bot: Bot, state: FSMContext):
    if not is_admin(message.from_user.id): return
    lang=get_lang(message.from_user.id); raw=(message.text or "").strip(); await clean_user_message(message)
    if not raw.isdigit():
        await screen(bot,message.from_user.id,message.chat.id,tr(lang,"❌ فقط عدد ارسال کنید.","❌ Send a number."),kb(nav(lang,"admin_campaigns"))); return
    d=await state.get_data(); maxuses=int(raw) or None
    cid=db.create_campaign(d["campaign_title_fa"],d["campaign_title_en"],float(d["campaign_percent"]),int(d["campaign_days"]),d.get("campaign_plan"),d.get("campaign_audience","all"),maxuses,message.from_user.id)
    await state.clear(); await screen(bot,message.from_user.id,message.chat.id,tr(lang,f"✅ کمپین #{cid} ساخته شد و از همین حالا فعال است.",f"✅ Campaign #{cid} created and is active now."),kb(nav(lang,"admin_campaigns")))


@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(cb: CallbackQuery, bot: Bot, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    await state.clear(); lang=get_lang(cb.from_user.id); await cb.answer()
    await screen(bot,cb.from_user.id,cb.message.chat.id,tr(lang,"<b>📣 ارسال پیام Center</b>\n\nگروه هدف پیام را انتخاب کنید.","<b>📣 Broadcast Center</b>\n\nChoose the target audience."),broadcast_target_menu(lang))


@router.callback_query(F.data.startswith("broadcast_target:"))
async def broadcast_target_pick(cb: CallbackQuery, bot: Bot, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    target=cb.data.split(":",1)[1]; lang=get_lang(cb.from_user.id)
    if target not in {"all","vip","nonvip","expired","highpoints"}: return
    count=len(db.broadcast_targets(target)); await state.update_data(broadcast_target=target,broadcast_count=count); await state.set_state(Flow.admin_broadcast_message); await cb.answer()
    await screen(bot,cb.from_user.id,cb.message.chat.id,tr(lang,f"مخاطب انتخاب شد: <b>{count}</b> کاربر.\n\nمتن پیام را ارسال کنید.",f"Selected audience: <b>{count}</b> users.\n\nSend the message text."),kb(nav(lang,"admin")))


@router.message(Flow.admin_broadcast_message)
async def broadcast_message_input(message: Message, bot: Bot, state: FSMContext):
    if not is_admin(message.from_user.id): return
    lang=get_lang(message.from_user.id); text=(message.text or "").strip(); await clean_user_message(message)
    if not text:
        await screen(bot,message.from_user.id,message.chat.id,tr(lang,"❌ متن خالی است.","❌ Message is empty."),kb(nav(lang,"admin"))); return
    d=await state.get_data(); await state.update_data(broadcast_text=text); await state.set_state(None)
    await screen(bot,message.from_user.id,message.chat.id,tr(lang,f"<b>پیش‌نمایش ارسال</b>\n\nمخاطب: <b>{d.get('broadcast_count',0)}</b> کاربر\n\n{escape(text)}",f"<b>Broadcast Preview</b>\n\nAudience: <b>{d.get('broadcast_count',0)}</b> users\n\n{escape(text)}"),broadcast_confirm_menu(lang))


async def _run_broadcast_job(bot: Bot, admin_id: int, admin_chat_id: int, lang: str, bid: int, ids: list[int], text: str) -> None:
    sent = failed = 0
    try:
        for uid in ids:
            try:
                await bot.send_message(uid, text)
                sent += 1
                try:
                    await push_home_to_bottom(bot, int(uid))
                except Exception as menu_exc:
                    log.warning("broadcast menu refresh failed for %s: %s", uid, menu_exc)
            except Exception as exc:
                failed += 1
                log.warning("broadcast #%s failed for %s: %s", bid, uid, exc)
            await asyncio.sleep(0.10)
    finally:
        db.finish_broadcast(bid, sent, failed)
        try:
            await screen(bot, admin_id, admin_chat_id, tr(lang, f"✅ ارسال #{bid} تمام شد.\nموفق: <b>{sent}</b>\nناموفق: <b>{failed}</b>", f"✅ Broadcast #{bid} finished.\nSent: <b>{sent}</b>\nFailed: <b>{failed}</b>"), kb(nav(lang, "admin")))
        except Exception:
            log.exception("broadcast completion UI failed for #%s", bid)


@router.callback_query(F.data == "broadcast_confirm")
async def broadcast_confirm(cb: CallbackQuery, bot: Bot, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    lang=get_lang(cb.from_user.id); d=await state.get_data(); target=d.get("broadcast_target"); text=d.get("broadcast_text")
    if not target or not text:
        await cb.answer(tr(lang,"اطلاعات ارسال از بین رفته؛ دوباره شروع کنید.","Broadcast data expired; start again."),show_alert=True); return
    ids=db.broadcast_targets(target); bid=db.create_broadcast(cb.from_user.id,target,text,len(ids))
    await cb.answer(tr(lang,"ارسال در پس‌زمینه شروع شد…","Broadcast started in background…"))
    await state.clear()
    await screen(bot, cb.from_user.id, cb.message.chat.id, tr(lang, f"📣 ارسال #{bid} در پس‌زمینه شروع شد.\nمخاطب: <b>{len(ids)}</b> کاربر\n\nمی‌توانید هم‌زمان از پنل استفاده کنید.", f"📣 Broadcast #{bid} started in background.\nAudience: <b>{len(ids)}</b> users\n\nYou can keep using the admin panel."), kb(nav(lang,"admin")))
    task = asyncio.create_task(_run_broadcast_job(bot, cb.from_user.id, cb.message.chat.id, lang, bid, [int(x) for x in ids], text))
    BACKGROUND_TASKS.add(task)
    task.add_done_callback(BACKGROUND_TASKS.discard)


@router.callback_query(F.data == "admin_crm")
async def admin_crm(cb: CallbackQuery, bot: Bot):
    if not is_admin(cb.from_user.id): return
    lang=get_lang(cb.from_user.id); await cb.answer()
    await screen(bot,cb.from_user.id,cb.message.chat.id,tr(lang,"<b>🚀 مدیریت مشتری & Retention</b>\n\nمدیریت حفظ مشتری، تمدید، Trial، سطح کاربران، Audit و بکاپ.","<b>🚀 CRM & Retention</b>\n\nManage retention, renewals, trials, user levels, audit and backups."),admin_crm_menu(lang))


@router.callback_query(F.data == "admin_dashboard")
async def admin_dashboard(cb: CallbackQuery, bot: Bot):
    if not is_admin(cb.from_user.id): return
    lang=get_lang(cb.from_user.id); d=db.dashboard_stats(); await cb.answer()
    text=tr(lang,
        f"<b>📈 داشبورد NEXUS CRM</b>\n\n👥 کاربران: <b>{d['users']}</b>\n💎 VIP فعال: <b>{d['active']}</b>\n🧾 پرداخت در انتظار: <b>{d['pending']}</b>\n⚠️ انقضا تا ۳ روز: <b>{db.expiring_count(3)}</b>\n⚠️ انقضا تا ۷ روز: <b>{db.expiring_count(7)}</b>\n🎁 Trial استفاده‌شده: <b>{d['trials']}</b>\n🤖 Waiting List: <b>{d['waitlist']}</b>\n\n💰 فروش امروز: <b>{d['revenue_today_usdt']:g} USDT</b>\n📅 فروش ماه: <b>{d['revenue_month_usdt']:g} USDT</b>\n🏦 فروش کل: <b>{d['revenue_all_usdt']:g} USDT</b>",
        f"<b>📈 NEXUS CRM Dashboard</b>\n\n👥 Users: <b>{d['users']}</b>\n💎 Active VIP: <b>{d['active']}</b>\n🧾 Pending payments: <b>{d['pending']}</b>\n⚠️ Expiring in 3 days: <b>{db.expiring_count(3)}</b>\n⚠️ Expiring in 7 days: <b>{db.expiring_count(7)}</b>\n🎁 Trials used: <b>{d['trials']}</b>\n🤖 Waitlist: <b>{d['waitlist']}</b>\n\n💰 Revenue today: <b>{d['revenue_today_usdt']:g} USDT</b>\n📅 Monthly revenue: <b>{d['revenue_month_usdt']:g} USDT</b>\n🏦 Total revenue: <b>{d['revenue_all_usdt']:g} USDT</b>")
    await screen(bot,cb.from_user.id,cb.message.chat.id,text,kb(nav(lang,"admin_crm")))


@router.callback_query(F.data == "admin_retention")
async def admin_retention(cb: CallbackQuery, bot: Bot):
    if not is_admin(cb.from_user.id): return
    lang=get_lang(cb.from_user.id); await cb.answer()
    text=tr(lang,
        f"<b>⏳ تمدید و حفظ مشتری</b>\n\nتا ۱ روز: <b>{db.expiring_count(1)}</b>\nتا ۳ روز: <b>{db.expiring_count(3)}</b>\nتا ۷ روز: <b>{db.expiring_count(7)}</b>\n\n✅ تمدید زودهنگام روزهای باقی‌مانده را از بین نمی‌برد؛ اعتبار جدید به تاریخ انقضای فعلی اضافه می‌شود.",
        f"<b>⏳ Renewal & Retention</b>\n\nWithin 1 day: <b>{db.expiring_count(1)}</b>\nWithin 3 days: <b>{db.expiring_count(3)}</b>\nWithin 7 days: <b>{db.expiring_count(7)}</b>\n\n✅ Early renewal never loses remaining days; new time is appended to the current expiry.")
    await screen(bot,cb.from_user.id,cb.message.chat.id,text,kb(nav(lang,"admin_crm")))


@router.callback_query(F.data == "admin_levels")
async def admin_levels(cb: CallbackQuery, bot: Bot):
    if not is_admin(cb.from_user.id): return
    lang=get_lang(cb.from_user.id); counts=db.user_level_counts()
    await cb.answer(); text=tr(lang,
        f"<b>🏅 سطح کاربران</b>\n\n🥉 Bronze: <b>{counts['bronze']}</b>\n🥈 Silver: <b>{counts['silver']}</b>\n🥇 Gold: <b>{counts['gold']}</b>\n💎 Diamond: <b>{counts['diamond']}</b>\n\nامتیاز سطح = خرید تأییدشده ×۳ + دعوت موفق.",
        f"<b>🏅 User Levels</b>\n\n🥉 Bronze: <b>{counts['bronze']}</b>\n🥈 Silver: <b>{counts['silver']}</b>\n🥇 Gold: <b>{counts['gold']}</b>\n💎 Diamond: <b>{counts['diamond']}</b>\n\nLevel score = approved purchases ×3 + successful referrals.")
    await screen(bot,cb.from_user.id,cb.message.chat.id,text,kb(nav(lang,"admin_crm")))


@router.callback_query(F.data.startswith("admtrial:"))
async def admin_trial(cb: CallbackQuery, bot: Bot):
    if not is_admin(cb.from_user.id): return
    _,uid,days=cb.data.split(":",2); target=int(uid); days_i=int(days); lang=get_lang(cb.from_user.id)
    lic=db.grant_trial(target,days_i,cb.from_user.id)
    if not lic:
        await cb.answer(tr(lang,"این کاربر قبلاً Trial دریافت کرده است.","This user has already used a trial."),show_alert=True); return
    db.add_audit(cb.from_user.id,"grant_trial",target,f"days={days_i}")
    await cb.answer(tr(lang,"Trial فعال شد ✅","Trial activated ✅"),show_alert=True)
    try:
        tlang=get_lang(target); await bot.send_message(target,tr(tlang,f"🎁 یک Trial VIP <b>{days_i} روزه</b> برای شما فعال شد.\nانقضا: <b>{fmt_dt(lic['expires_at'])}</b>",f"🎁 A <b>{days_i}-day VIP Trial</b> has been activated for you.\nExpiry: <b>{fmt_dt(lic['expires_at'])}</b>"),parse_mode=ParseMode.HTML)
        await send_license_link(bot,target,lic)
    except Exception: log.exception("trial notification/invite failed")


@router.callback_query(F.data == "admin_audit")
async def admin_audit(cb: CallbackQuery, bot: Bot):
    if not is_admin(cb.from_user.id): return
    lang=get_lang(cb.from_user.id); rows=db.recent_audits(20); await cb.answer()
    lines=[f"#{r['id']} | {r['action']} | target={r['target_id'] or '—'} | admin={r['admin_id']} | {fmt_dt(r['created_at'])}" for r in rows]
    text=tr(lang,"<b>🧾 Audit Log</b>\n\n","<b>🧾 Audit Log</b>\n\n")+("\n".join(lines) if lines else "—")
    await screen(bot,cb.from_user.id,cb.message.chat.id,text,kb(nav(lang,"admin_crm")))


def create_db_backup() -> Path:
    root=Path(__file__).resolve().parent.parent; backup_dir=root/"backup"; backup_dir.mkdir(exist_ok=True)
    stamp=datetime.now(TZ).strftime("%Y-%m-%d_%H-%M-%S")
    dst=backup_dir/f"nexus_bot_{stamp}.db"
    import sqlite3
    src=sqlite3.connect(db.DB_PATH); out=sqlite3.connect(dst)
    try: src.backup(out)
    finally: out.close(); src.close()
    files=sorted(backup_dir.glob("nexus_bot_*.db"),key=lambda x:x.stat().st_mtime,reverse=True)
    for old in files[30:]:
        try: old.unlink()
        except OSError: pass
    return dst


@router.callback_query(F.data == "admin_backup")
async def admin_backup(cb: CallbackQuery, bot: Bot):
    if not is_admin(cb.from_user.id): return
    lang=get_lang(cb.from_user.id)
    try:
        path=await asyncio.to_thread(create_db_backup); db.add_audit(cb.from_user.id,"manual_backup",None,path.name); await cb.answer(tr(lang,"بکاپ ساخته شد ✅","Backup created ✅"),show_alert=True)
        await screen(bot,cb.from_user.id,cb.message.chat.id,tr(lang,f"<b>💾 بکاپ دیتابیس ساخته شد</b>\n\n<code>{escape(path.name)}</code>\n\nحداکثر ۳۰ بکاپ آخر نگهداری می‌شود.",f"<b>💾 Database backup created</b>\n\n<code>{escape(path.name)}</code>\n\nThe latest 30 backups are retained."),kb(nav(lang,"admin_crm")))
    except Exception as exc:
        log.exception("backup failed"); await cb.answer(tr(lang,"بکاپ ناموفق بود.","Backup failed."),show_alert=True)


# =========================
# NEXUS v6.2 Admin Groups
# =========================
async def _admin_group(cb: CallbackQuery, bot: Bot, title_fa: str, title_en: str, markup) -> None:
    if not is_admin(cb.from_user.id):
        await cb.answer("دسترسی مجاز نیست." if get_lang(cb.from_user.id) == "fa" else "Access denied.", show_alert=True); return
    lang = get_lang(cb.from_user.id); await cb.answer()
    await screen(bot, cb.from_user.id, cb.message.chat.id, tr(lang, f"<b>{title_fa}</b>", f"<b>{title_en}</b>"), markup(lang))


@router.callback_query(F.data == "admin_group_users")
async def admin_group_users_cb(cb: CallbackQuery, bot: Bot): await _admin_group(cb, bot, "👥 کاربران و اشتراک‌ها", "👥 Users & Subscriptions", admin_users_group)

@router.callback_query(F.data == "admin_group_finance")
async def admin_group_finance_cb(cb: CallbackQuery, bot: Bot): await _admin_group(cb, bot, "💳 مالی و پرداخت", "💳 Finance & Payments", admin_finance_group)

@router.callback_query(F.data == "admin_group_rewards")
async def admin_group_rewards_cb(cb: CallbackQuery, bot: Bot): await _admin_group(cb, bot, "🎁 رفرال و وفاداری", "🎁 Referral & Loyalty", admin_rewards_group)

@router.callback_query(F.data == "admin_group_content")
async def admin_group_content_cb(cb: CallbackQuery, bot: Bot): await _admin_group(cb, bot, "📢 محتوا و کانال‌ها", "📢 Content & Channels", admin_content_group)

@router.callback_query(F.data == "admin_group_marketing")
async def admin_group_marketing_cb(cb: CallbackQuery, bot: Bot): await _admin_group(cb, bot, "📣 کمپین و پیام‌رسانی", "📣 Campaigns & Messaging", admin_marketing_group)

@router.callback_query(F.data == "admin_group_reports")
async def admin_group_reports_cb(cb: CallbackQuery, bot: Bot): await _admin_group(cb, bot, "📊 گزارشات", "📊 Reports", admin_reports_group)

@router.callback_query(F.data == "pricing_settings")
async def pricing_settings(cb: CallbackQuery, bot: Bot):
    if not is_admin(cb.from_user.id): return
    lang=get_lang(cb.from_user.id); await cb.answer()
    rate=db.get_setting("usdt_rial_manual_rate", "") or db.get_setting("usdt_rial_last_rate", "—")
    ttl=int(db.get_setting("rial_invoice_ttl_minutes", str(settings.rial_invoice_ttl_minutes)))
    source=db.get_setting("usdt_rial_rate_source", settings.usdt_rial_rate_source)
    proration = db.get_setting("upgrade_proration_enabled", "true").strip().lower() in {"1","true","yes","on"}
    fa_proration = "فعال" if proration else "غیرفعال"
    text=tr(lang,f"<b>💱 تنظیمات نرخ و قیمت‌گذاری</b>\n\nنرخ فعلی: <b>{escape(str(rate))}</b> ریال/USDT\nمنبع: <b>{escape(source)}</b>\nاعتبار فاکتور ریالی: <b>{ttl} دقیقه</b>\nمحاسبه اعتبار باقی‌مانده در ارتقا: <b>{fa_proration}</b>\n\nبرای تغییر نرخ دستی، مدت اعتبار فاکتور یا منبع نرخ از گزینه‌های زیر استفاده کنید.",f"<b>💱 Pricing Settings</b>\n\nCurrent rate: <b>{escape(str(rate))}</b> IRR/USDT\nSource: <b>{escape(source)}</b>\nRial invoice TTL: <b>{ttl} minutes</b>\nUpgrade proration: <b>{'ON' if proration else 'OFF'}</b>")
    pricing_rows = [[('💱 تغییر نرخ دستی تتر','pricing_rate'),('⏱ مدت اعتبار فاکتور','pricing_ttl')],[('🌐 منبع نرخ','pricing_source')],[('🧮 فعال/غیرفعال‌کردن محاسبه ارتقا','pricing_proration')],[('🧹 حذف نرخ دستی','pricing_clear_rate')]] if lang=='fa' else [[('💱 Override USDT Rate','pricing_rate'),('⏱ Invoice TTL','pricing_ttl')],[('🌐 Rate Source','pricing_source')],[('🧮 Toggle Upgrade Proration','pricing_proration')],[('🧹 Clear Manual Override','pricing_clear_rate')]]
    await screen(bot,cb.from_user.id,cb.message.chat.id,text,kb(pricing_rows+nav(lang,'admin_group_system')))

@router.callback_query(F.data == "pricing_source")
async def pricing_source_input(cb: CallbackQuery, bot: Bot, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    lang=get_lang(cb.from_user.id); await state.set_state(Flow.admin_rate_source); await cb.answer(); await screen(bot,cb.from_user.id,cb.message.chat.id,tr(lang,"URL منبع نرخ تتر/ریال را وارد کنید. برای Nobitex می‌توانید همان URL پیش‌فرض را وارد کنید.","Enter the USDT/RIAL provider URL. You may use the default Nobitex URL."),kb(nav(lang,'pricing_settings')))

@router.message(Flow.admin_rate_source)
async def pricing_source_save(message: Message, bot: Bot, state: FSMContext):
    if not is_admin(message.from_user.id): return
    raw=(message.text or '').strip(); lang=get_lang(message.from_user.id); await clean_user_message(message)
    if not raw.startswith(('https://','http://')):
        await screen(bot,message.from_user.id,message.chat.id,tr(lang,'❌ URL معتبر نیست.','❌ Invalid URL.'),kb(nav(lang,'pricing_settings'))); return
    db.set_setting('usdt_rial_rate_url',raw); db.set_setting('usdt_rial_rate_source','custom'); db.add_audit(message.from_user.id,'usdt_rial_rate_source',None,raw); await state.clear(); await screen(bot,message.from_user.id,message.chat.id,tr(lang,'✅ منبع نرخ تغییر کرد.','✅ Rate provider updated.'),kb(nav(lang,'pricing_settings')))

@router.callback_query(F.data == "pricing_rate")
async def pricing_rate_input(cb: CallbackQuery, bot: Bot, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    lang=get_lang(cb.from_user.id); await state.set_state(Flow.admin_usdt_rate); await cb.answer(); await screen(bot,cb.from_user.id,cb.message.chat.id,tr(lang,"نرخ دستی تتر به ریال را فقط به عدد وارد کنید.","Enter the manual USDT/RIAL rate as a number."),kb(nav(lang,'pricing_settings')))

@router.message(Flow.admin_usdt_rate)
async def pricing_rate_save(message: Message, bot: Bot, state: FSMContext):
    if not is_admin(message.from_user.id): return
    raw=(message.text or '').strip().replace(',',''); lang=get_lang(message.from_user.id); await clean_user_message(message)
    try:
        rate=float(raw);
        if rate<=0: raise ValueError
    except Exception:
        await screen(bot,message.from_user.id,message.chat.id,tr(lang,'❌ نرخ نامعتبر است.','❌ Invalid rate.'),kb(nav(lang,'pricing_settings'))); return
    db.set_setting('usdt_rial_manual_rate',raw); db.set_setting('usdt_rial_last_rate',raw); db.set_setting('usdt_rial_last_rate_at',datetime.now(timezone.utc).isoformat()); db.add_audit(message.from_user.id,'usdt_rial_manual_override',None,raw); await state.clear(); await screen(bot,message.from_user.id,message.chat.id,tr(lang,'✅ نرخ دستی ثبت شد.','✅ Manual rate saved.'),kb(nav(lang,'pricing_settings')))

@router.callback_query(F.data == "pricing_proration")
async def pricing_proration(cb: CallbackQuery, bot: Bot):
    if not is_admin(cb.from_user.id): return
    current=db.get_setting("upgrade_proration_enabled","true").strip().lower() in {"1","true","yes","on"}
    db.set_setting("upgrade_proration_enabled","false" if current else "true"); db.add_audit(cb.from_user.id,"upgrade_proration_toggle",None,"off" if current else "on")
    await cb.answer(tr(get_lang(cb.from_user.id),"محاسبه اعتبار باقی‌مانده برای Upgrade " + ("غیرفعال شد." if current else "فعال شد."),"Upgrade proration " + ("disabled." if current else "enabled.")),show_alert=True)
    await pricing_settings(cb,bot)

@router.callback_query(F.data == "pricing_clear_rate")
async def pricing_clear_rate(cb: CallbackQuery, bot: Bot):
    if not is_admin(cb.from_user.id): return
    db.set_setting('usdt_rial_manual_rate',''); db.add_audit(cb.from_user.id,'usdt_rial_manual_override_clear'); await cb.answer(tr(get_lang(cb.from_user.id),'نرخ دستی حذف شد.','Override cleared.'),show_alert=True); await pricing_settings(cb,bot)

@router.callback_query(F.data == "pricing_ttl")
async def pricing_ttl_input(cb: CallbackQuery, bot: Bot, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    lang=get_lang(cb.from_user.id); await state.set_state(Flow.admin_invoice_ttl); await cb.answer(); await screen(bot,cb.from_user.id,cb.message.chat.id,tr(lang,'مدت اعتبار فاکتور ریالی را به دقیقه وارد کنید.','Enter the rial invoice TTL in minutes.'),kb(nav(lang,'pricing_settings')))

@router.message(Flow.admin_invoice_ttl)
async def pricing_ttl_save(message: Message, bot: Bot, state: FSMContext):
    if not is_admin(message.from_user.id): return
    raw=(message.text or '').strip(); lang=get_lang(message.from_user.id); await clean_user_message(message)
    if not raw.isdigit() or not 1<=int(raw)<=120:
        await screen(bot,message.from_user.id,message.chat.id,tr(lang,'❌ مقدار مدت اعتبار باید بین 1 تا 120 دقیقه باشد.','❌ TTL must be between 1 and 120 minutes.'),kb(nav(lang,'pricing_settings'))); return
    db.set_setting('rial_invoice_ttl_minutes',raw); db.add_audit(message.from_user.id,'rial_invoice_ttl',None,raw); await state.clear(); await screen(bot,message.from_user.id,message.chat.id,tr(lang,'✅ مدت اعتبار ذخیره شد؛ فاکتورهای جدید از این مقدار استفاده می‌کنند.','✅ TTL saved; new invoices will use this value.'),kb(nav(lang,'pricing_settings')))


@router.callback_query(F.data == "admin_group_system")
async def admin_group_system_cb(cb: CallbackQuery, bot: Bot): await _admin_group(cb, bot, "⚙️ تنظیمات سیستم", "⚙️ System Settings", admin_system_group)


@router.callback_query(F.data == "admin_channels_status")
async def admin_channels_status(cb: CallbackQuery, bot: Bot):
    if not is_admin(cb.from_user.id): return
    lang=get_lang(cb.from_user.id); await cb.answer()
    rows=[]
    checks=[("Public", settings.public_channel_id), ("Free", settings.free_channel_target), ("VIP", settings.vip_channel_id)]
    for name,target in checks:
        try:
            chat=await bot.get_chat(target)
            rows.append(f"✅ {name}: <code>{escape(str(chat.id))}</code>")
        except Exception as exc:
            rows.append(f"❌ {name}: {escape(str(exc))}")
    await screen(bot,cb.from_user.id,cb.message.chat.id,tr(lang,"<b>📡 وضعیت کانال‌ها</b>\n\n","<b>📡 Channel Status</b>\n\n")+"\n".join(rows),kb(nav(lang,"admin_group_content")))


# =========================
# NEXUS v6.4 Signal Center
# =========================
_DIGIT_TRANSLATION = str.maketrans({
    "۰":"0","۱":"1","۲":"2","۳":"3","۴":"4","۵":"5","۶":"6","۷":"7","۸":"8","۹":"9",
    "٠":"0","١":"1","٢":"2","٣":"3","٤":"4","٥":"5","٦":"6","٧":"7","٨":"8","٩":"9",
})

def _normalize_numeric_text(text: str) -> str:
    value = (text or "").strip().translate(_DIGIT_TRANSLATION)
    value = value.replace("٫", ".").replace("٬", "").replace(" ", "")
    # Preserve the previous decimal-comma behavior while accepting Persian/Arabic digits.
    return value.replace(",", ".")

def _fnum(text: str) -> float:
    return float(_normalize_numeric_text(text))


def _rr(entry: float, sl: float, target: float, direction: str) -> float | None:
    return risk_reward(entry, sl, target, direction)


def _format_price(v) -> str:
    if v is None: return "—"
    f=float(v)
    if abs(f)>=1000: return f"{f:g}"
    return f"{f:.5f}".rstrip("0").rstrip(".")


async def _download_bytes(bot: Bot, file_id: str | None) -> bytes | None:
    if not file_id: return None
    buf=BytesIO()
    await bot.download(file_id, destination=buf)
    return buf.getvalue()


def _signal_dict_for_card(row) -> dict:
    targets = db.get_signal_targets(int(row["id"]))
    return {
        "code": row["code"],
        "market_type": row["market_type"],
        "symbol": row["symbol"],
        "direction": row["direction"],
        "order_type": str(row["order_type"] if "order_type" in row.keys() and row["order_type"] else "MARKET").upper(),
        "entry": _format_price(row["entry_price"]),
        "stop_loss": _format_price(row["stop_loss"]),
        "targets": [_format_price(t["price"]) for t in targets],
        "volume_mode": str(row["volume_mode"] if "volume_mode" in row.keys() and row["volume_mode"] else "RISK").upper(),
        "lot_size": f"{float(row['lot_size']):g} Lot" if row["lot_size"] is not None else None,
        "leverage": f"{float(row['leverage']):g}X" if row["leverage"] is not None else None,
        "risk_percent": f"{float(row['risk_percent']):g}",
        "rr": f"1:{float(row['rr_ratio']):g}" if row["rr_ratio"] else "—",
        "trailing_code": row["trailing_code"] or "—",
        "trailing_name": row["trailing_name"] or "—",
    }


def _copy_price(value) -> str:
    """Render a price as Telegram inline-code so it is visually distinct and easy to copy.

    Telegram does not let bots force arbitrary text to use the client's hyperlink color
    unless that text is a real link. Using <code> keeps the value honest (not a fake link)
    and gives users the native tap/hold copy affordance available in Telegram clients.
    """
    return f"<code>{escape(_format_price(value))}</code>"


def _signal_caption(row, lang: str = "en", *, status: str | None = None) -> str:
    """Canonical LTR English signal card used by every publication path.

    Signal cards are deliberately language-neutral. Telegram channel posts must
    remain stable across clients and must never contain Persian BiDi fragments or
    literal ``\\n`` sequences.
    """
    order_type = str(row["order_type"] if "order_type" in row.keys() and row["order_type"] else "MARKET").upper()
    direction = str(row["direction"] or "").upper()
    symbol = str(row["symbol"] or "").upper()
    tf = str(row["timeframe"] if "timeframe" in row.keys() and row["timeframe"] else "M5").upper()
    state = str(status or row["status"] or "SIGNAL").upper()
    type_labels = {
        "MARKET": "MARKET",
        "BUY_LIMIT": "BUY LIMIT",
        "SELL_LIMIT": "SELL LIMIT",
        "BUY_STOP": "BUY STOP",
        "SELL_STOP": "SELL STOP",
        "BUY_STOP_LIMIT": "BUY STOP LIMIT",
        "SELL_STOP_LIMIT": "SELL STOP LIMIT",
        "LIMIT": "LIMIT",
    }
    state_labels = {
        "ACTIVE": "ACTIVE", "PENDING": "PENDING", "CLOSED": "CLOSED",
        "CANCELLED": "CANCELLED", "EXPIRED": "EXPIRED", "DRAFT": "DRAFT",
    }
    targets = db.get_signal_targets(int(row["id"]))
    if not targets:
        legacy = [row["tp1"], row["tp2"], row["tp3"]]
        targets = [{"target_no": i + 1, "price": value} for i, value in enumerate(legacy) if value is not None]
    rr = ("1:" + format(float(row["rr_ratio"]), "g")) if row["rr_ratio"] else "—"
    volume_mode = str(row["volume_mode"] or "RISK").upper()
    if volume_mode == "FIXED" and row["lot_size"] is not None:
        size_line = f"📦 Volume: <b>{float(row['lot_size']):g} lots</b>"
    else:
        size_line = f"📊 Risk: <b>{float(row['risk_percent']):g}%</b>"
    tp_lines = "\n".join(
        f"🎯 TP{int(t['target_no'])}: {_copy_price(t['price'])}" for t in targets
    ) or "🎯 TP: —"
    stop_limit = ""
    if order_type in {"BUY_STOP_LIMIT", "SELL_STOP_LIMIT"} and "stop_limit_price" in row.keys() and row["stop_limit_price"]:
        stop_limit = f"\n🔹 Stop-Limit Price: {_copy_price(row['stop_limit_price'])}"
    return (
        "<b>━━━━━━━━ NEXUS SIGNAL ━━━━━━━━</b>\n"
        f"<b>{escape(str(row['code']))}</b>  🟦 {escape(type_labels.get(order_type, order_type))}\n\n"
        f"📌 Symbol: <b>{escape(symbol)}</b>\n"
        f"↕️ Direction: <b>{escape(direction)}</b>\n"
        f"⏱ Timeframe: <b>{escape(tf)}</b>\n"
        f"📍 Entry: {_copy_price(row['entry_price'])}{stop_limit}\n"
        f"🛑 Stop Loss: {_copy_price(row['stop_loss'])}\n"
        f"{tp_lines}\n"
        f"{size_line}\n"
        f"📐 R:R: <b>{escape(rr)}</b>\n"
        f"📌 Status: <b>{escape(state_labels.get(state, state))}</b>\n"
        f"🔧 Trailing: <b>{escape(str(row['trailing_code'] or '—'))}</b>"
    )



async def _publish_one_channel(bot: Bot, target, row, chart_frame: bytes, caption: str) -> int:
    """Publish exactly one signal post: framed chart + compact copyable caption."""
    try:
        await bot.get_chat(target)
    except Exception as exc:
        raise RuntimeError(f"Channel {target!s} is not accessible to the bot: {exc}") from exc

    msg = await bot.send_photo(
        target,
        BufferedInputFile(chart_frame, filename=f"{row['code']}_chart.png"),
        caption=caption,
        parse_mode=ParseMode.HTML,
    )
    return msg.message_id


async def _publish_signal(bot: Bot, row, *, only_missing: bool = False) -> tuple[int | None, int | None, list[str]]:
    chart = await _download_bytes(bot, row["chart_file_id"])
    chart_frame = await asyncio.to_thread(build_chart_frame, chart)
    caption = _signal_caption(row, get_lang(int(row["created_by"])))
    # Publication is idempotent: an already delivered channel message is the
    # canonical signal post and must never be published again for the same Signal.
    free_id = int(row["free_message_id"]) if row["free_message_id"] else None
    vip_id = int(row["vip_message_id"]) if row["vip_message_id"] else None
    new_free_id = new_vip_id = None
    errors: list[str] = []

    if row["destination"] in {"FREE", "BOTH"} and free_id is None:
        try:
            free_id = await _publish_one_channel(bot, settings.free_channel_target, row, chart_frame, caption)
            new_free_id = free_id
        except Exception as exc:
            log.exception("free signal publish failed for %s", row["code"])
            errors.append(f"FREE: {exc}")

    if row["destination"] in {"VIP", "BOTH"} and vip_id is None:
        try:
            vip_id = await _publish_one_channel(bot, settings.vip_channel_id, row, chart_frame, caption)
            new_vip_id = vip_id
        except Exception as exc:
            log.exception("VIP signal publish failed for %s", row["code"])
            errors.append(f"VIP: {exc}")

    db.set_signal_publish_messages(int(row["id"]), new_free_id, new_vip_id)
    requested = 2 if row["destination"] == "BOTH" else 1
    succeeded = int(free_id is not None) + int(vip_id is not None)
    if succeeded == 0:
        db.set_signal_status(int(row["id"]), "PUBLISH_FAILED")
    elif succeeded < requested:
        db.set_signal_status(int(row["id"]), "PARTIAL_PUBLISH")
    else:
        db.set_signal_status(int(row["id"]), "ACTIVE")
    return free_id, vip_id, errors


async def _reply_signal_update(bot: Bot, row, text: str) -> tuple[int | None, int | None, list[str]]:
    """Append one message to the end of each channel's Reply Chain.

    The original signal is only the anchor. Every new message replies to the
    latest successfully delivered message. A per-(signal,channel) asyncio lock
    serializes concurrent handlers so SL/TP/BE events cannot branch the chain.
    """
    free_mid = vip_mid = None
    errors: list[str] = []

    async def send_reply(target, latest_id, original_id, label: str) -> int | None:
        signal_id = int(row["id"])
        channel = label.upper()
        lock = await _reply_chain_lock(signal_id, channel)
        async with lock:
            parents: list[int] = []
            for raw in (latest_id, original_id):
                if raw is None:
                    continue
                try:
                    mid = int(raw)
                except (TypeError, ValueError):
                    continue
                if mid not in parents:
                    parents.append(mid)

            if not parents:
                errors.append(f"{label}: no published signal message is available for reply")
                return None

            last_exc: Exception | None = None
            for parent_id in parents:
                try:
                    m = await bot.send_message(
                        target, text, parse_mode=ParseMode.HTML,
                        reply_parameters=ReplyParameters(message_id=parent_id),
                    )
                    # Persist the new tail while the chain lock is still held.
                    if channel == "FREE":
                        db.set_signal_latest_reply(signal_id, free_message_id=m.message_id)
                    else:
                        db.set_signal_latest_reply(signal_id, vip_message_id=m.message_id)
                    return m.message_id
                except Exception as exc:
                    last_exc = exc
                    log.exception(
                        "[NEXUS][TELEGRAM] %s reply failed signal=%s parent=%s",
                        label, row["code"], parent_id,
                    )
            errors.append(f"{label}: {last_exc}")
            return None

    if row["destination"] in {"FREE", "BOTH"}:
        free_mid = await send_reply(
            settings.free_channel_target,
            row["free_last_message_id"], row["free_message_id"], "FREE",
        )
    if row["destination"] in {"VIP", "BOTH"}:
        vip_mid = await send_reply(
            settings.vip_channel_id,
            row["vip_last_message_id"], row["vip_message_id"], "VIP",
        )
    return free_mid, vip_mid, errors


@router.callback_query(F.data == "admin_signals")
async def admin_signals(cb: CallbackQuery, bot: Bot, state: FSMContext):
    if not is_admin(cb.from_user.id):
        await cb.answer("Access denied.", show_alert=True); return
    await state.clear(); lang=get_lang(cb.from_user.id); await cb.answer()
    await screen(
        bot, cb.from_user.id, cb.message.chat.id,
        tr(lang,
           "<b>📊 گزارش سیگنال‌های MT5</b>\n\nصدور، ویرایش و لغو فقط از MT5 Admin انجام می‌شود. این بخش فقط وضعیت سیگنال‌های فعال، نتایج بسته‌شده و آمار را نمایش می‌دهد.",
           "<b>📊 MT5 Signal Reports</b>\n\nIssuing, editing and cancelling are MT5-only. This section is read-only and shows active signals, closed results and statistics."),
        signal_center_menu(lang),
    )


@router.callback_query(F.data == "trailing_guide")
async def trailing_guide(cb: CallbackQuery, bot: Bot):
    if not is_admin(cb.from_user.id): return
    lang=get_lang(cb.from_user.id); await cb.answer()
    text=tr(lang,
        "<b>📚 راهنمای مدل‌های حدضرر متحرک</b>\n\nهر مدل یک روش متفاوت برای مدیریت معامله بعد از ورود دارد. یکی از مدل‌های زیر را انتخاب کنید تا منطق عملکرد آن را ببینید.\n\nاین راهنما فقط برای تصمیم‌گیری ادمین است؛ هنگام صدور سیگنال، کد انتخاب‌شده در سیگنال ذخیره و روی معاملات خودکار به‌صورت NEXUS LOCKED اجرا می‌شود.",
        "<b>📚 Trailing Models Guide</b>\n\nEach model manages the trade differently after entry. Choose a model below to view its behavior.\n\nThis guide is for admin selection; the chosen profile is stored with the Signal and executed in NEXUS LOCKED mode by Auto Trade.")
    await screen(bot,cb.from_user.id,cb.message.chat.id,text,trailing_guide_menu(lang))


@router.callback_query(F.data.startswith("trailguide:"))
async def trailing_guide_detail(cb: CallbackQuery, bot: Bot):
    if not is_admin(cb.from_user.id): return
    lang=get_lang(cb.from_user.id); code=cb.data.split(":",1)[1].upper(); await cb.answer()
    try:
        detail=profile_guide(code,lang)
    except ValueError:
        await cb.answer(tr(lang,"مدل نامعتبر است.","Invalid trailing profile."),show_alert=True); return
    lines=detail.split("\n",2)
    name=lines[1] if len(lines)>1 else ""
    body=lines[2] if len(lines)>2 else ""
    text=(f"<b>{escape(code)}</b>\n<b>{escape(name)}</b>\n\n{escape(body)}\n\n"+
          tr(lang,"هنگام صدور سیگنال فقط نام این مدل را انتخاب کنید؛ تنظیمات آن همراه تصویر سیگنال ذخیره می‌شود.","When issuing a signal, select this model; its settings are saved with the Signal Snapshot."))
    await screen(bot,cb.from_user.id,cb.message.chat.id,text,trailing_guide_detail_menu(lang))


@router.callback_query(F.data == "signal_create")
async def signal_create(cb: CallbackQuery, bot: Bot, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    await state.clear(); await state.update_data(signal_publish_token=secrets.token_urlsafe(16)); lang=get_lang(cb.from_user.id); await cb.answer()
    await screen(bot,cb.from_user.id,cb.message.chat.id,tr(lang,"<b>۱/۱۳ — نوع بازار</b>\n\nبازار سیگنال را انتخاب کنید.","<b>1/13 — Market</b>\n\nChoose the signal market."),signal_market_menu(lang))


@router.callback_query(F.data.startswith("sigmarket:"))
async def signal_market(cb: CallbackQuery, bot: Bot, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    market=cb.data.split(":",1)[1]
    if market not in {"FOREX","CRYPTO"}: return
    await state.update_data(signal_market=market); await state.set_state(Flow.signal_chart); lang=get_lang(cb.from_user.id); await cb.answer()
    await screen(bot,cb.from_user.id,cb.message.chat.id,tr(lang,"<b>۲/۱۳ — تصویر چارت</b>\n\nاسکرین‌شات تحلیل چارت را ارسال کنید. تصویر کامل و بدون Crop در قاب NEXUS قرار می‌گیرد.","<b>2/13 — Chart Image</b>\n\nSend the chart screenshot. It will be framed without cropping."),kb(nav(lang,"admin_signals")))


@router.message(Flow.signal_chart, F.photo)
async def signal_chart(message: Message, bot: Bot, state: FSMContext):
    if not is_admin(message.from_user.id): return
    file_id=message.photo[-1].file_id; await state.update_data(signal_chart_file_id=file_id); await clean_user_message(message)
    data=await state.get_data(); await state.set_state(None); lang=get_lang(message.from_user.id)
    await screen(bot,message.from_user.id,message.chat.id,tr(lang,"<b>۳/۱۳ — نماد</b>\n\nنماد را از لیست انتخاب کنید یا ورود دستی را بزنید.","<b>3/13 — Symbol</b>\n\nChoose a symbol or use manual entry."),signal_symbol_menu(lang,str(data.get("signal_market"))))


@router.message(Flow.signal_chart)
async def signal_chart_invalid(message: Message, bot: Bot):
    if not is_admin(message.from_user.id): return
    await clean_user_message(message); lang=get_lang(message.from_user.id)
    await screen(bot,message.from_user.id,message.chat.id,tr(lang,"لطفاً تصویر چارت را به‌صورت Photo ارسال کنید.","Please send the chart as a photo."),kb(nav(lang,"admin_signals")))


async def _show_signal_direction(bot: Bot, user_id: int, chat_id: int, state: FSMContext) -> None:
    data=await state.get_data(); lang=get_lang(user_id); await state.set_state(None)
    await screen(bot,user_id,chat_id,tr(lang,"<b>۴/۱۳ — جهت معامله</b>","<b>4/13 — Direction</b>"),signal_direction_menu(lang,str(data.get("signal_market"))))


@router.callback_query(F.data.startswith("sigsymbol:"))
async def signal_symbol_pick(cb: CallbackQuery, bot: Bot, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    value=cb.data.split(":",1)[1]; lang=get_lang(cb.from_user.id); await cb.answer()
    if value == "MANUAL":
        await state.set_state(Flow.signal_symbol)
        await screen(bot,cb.from_user.id,cb.message.chat.id,tr(lang,"نماد را دستی وارد کنید. مثال: <code>USDJPY</code>","Enter the symbol manually, e.g. <code>USDJPY</code>"),kb(nav(lang,"admin_signals")))
        return
    if not re.fullmatch(r"[A-Z0-9._/-]{3,20}",value): return
    await state.update_data(signal_symbol=value)
    await _show_signal_direction(bot,cb.from_user.id,cb.message.chat.id,state)


@router.message(Flow.signal_symbol)
async def signal_symbol(message: Message, bot: Bot, state: FSMContext):
    if not is_admin(message.from_user.id): return
    symbol=(message.text or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9._/-]{3,20}",symbol):
        await clean_user_message(message); return
    await state.update_data(signal_symbol=symbol); await clean_user_message(message)
    await _show_signal_direction(bot,message.from_user.id,message.chat.id,state)


@router.callback_query(F.data.startswith("sigdir:"))
async def signal_direction(cb: CallbackQuery, bot: Bot, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    direction=cb.data.split(":",1)[1]
    if direction not in {"BUY","SELL","LONG","SHORT"}: return
    await state.update_data(signal_direction=direction); await state.set_state(None); lang=get_lang(cb.from_user.id); await cb.answer()
    await screen(bot,cb.from_user.id,cb.message.chat.id,
                 tr(lang,"<b>تایم‌فریم</b>\n\nتایم‌فریم تحلیل سیگنال را انتخاب کنید.",
                    "<b>Timeframe</b>\n\nChoose the analysis timeframe for this signal."),
                 signal_timeframe_menu(lang))


@router.callback_query(F.data.startswith("sigtf:"))
async def signal_timeframe_pick(cb: CallbackQuery, bot: Bot, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    timeframe = cb.data.split(":", 1)[1].upper()
    if timeframe not in {"M1","M3","M5","M15","M30","H1","H4","D1","W1"}: return
    await state.update_data(signal_timeframe=timeframe, signal_order_type="MARKET")
    await state.set_state(None)
    lang=get_lang(cb.from_user.id); await cb.answer()
    await screen(bot,cb.from_user.id,cb.message.chat.id,
                 tr(lang,"<b>نوع سفارش</b>\n\n⚡ بازار: ورود در قیمت لحظه‌ای با کنترل فاصله مجاز ورود.\n⏳ لیمیت: سفارش در قیمت ورود ثبت می‌شود و تا فعال شدن منتظر می‌ماند.",
                    "<b>Order Type</b>\n\n⚡ Market: enter at market after entry-deviation validation.\n⏳ Limit: place a pending order at the specified Entry price."),
                 signal_order_type_menu(lang))


@router.callback_query(F.data.startswith("sigorder:"))
async def signal_order_type_pick(cb: CallbackQuery, bot: Bot, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    order_type=cb.data.split(":",1)[1].upper(); lang=get_lang(cb.from_user.id)
    if order_type not in {"MARKET","BUY_LIMIT","SELL_LIMIT","BUY_STOP","SELL_STOP","BUY_STOP_LIMIT","SELL_STOP_LIMIT"}: return
    await state.update_data(signal_order_type=order_type)
    await state.set_state(Flow.signal_entry)
    await cb.answer()
    hint=("قیمت ورود سفارش Pending را وارد کنید. نوع سفارش انتخاب‌شده با قیمت و Bid/Ask اعتبارسنجی می‌شود." if order_type!="MARKET" else "قیمت مرجع ورود را وارد کنید. ورود لحظه‌ای فقط در محدوده مجاز اجرا می‌شود.")
    hint_en=("Enter the pending-order entry price. The selected order type will be validated against Bid/Ask." if order_type!="MARKET" else "Enter the reference entry price. Market execution is allowed only within the configured deviation.")
    await screen(bot,cb.from_user.id,cb.message.chat.id,tr(lang,f"<b>Entry — {order_type}</b>\n\n{hint}",f"<b>Entry — {order_type}</b>\n\n{hint_en}"),kb(nav(lang,"admin_signals")))


async def _number_step(message: Message, bot: Bot, state: FSMContext, key: str, next_state: State, fa: str, en: str):
    if not is_admin(message.from_user.id): return
    try: value=_fnum(message.text or "")
    except Exception:
        await clean_user_message(message); lang=get_lang(message.from_user.id); await screen(bot,message.from_user.id,message.chat.id,tr(lang,"❌ عدد معتبر وارد کنید.","❌ Enter a valid number."),kb(nav(lang,"admin_signals"))); return
    await state.update_data(**{key:value}); await clean_user_message(message); await state.set_state(next_state); lang=get_lang(message.from_user.id)
    await screen(bot,message.from_user.id,message.chat.id,tr(lang,fa,en),kb(nav(lang,"admin_signals")))


@router.message(Flow.signal_entry)
async def signal_entry(message: Message, bot: Bot, state: FSMContext):
    if not is_admin(message.from_user.id): return
    try:
        value=_fnum(message.text or "")
    except Exception:
        await clean_user_message(message); return
    data=await state.get_data()
    await state.update_data(signal_entry=value)
    await clean_user_message(message)
    order_type=str(data.get("signal_order_type") or "MARKET").upper()
    lang=get_lang(message.from_user.id)
    if order_type in {"BUY_STOP_LIMIT","SELL_STOP_LIMIT"}:
        await state.set_state(Flow.signal_stop_limit)
        await screen(
            bot,message.from_user.id,message.chat.id,
            tr(lang,
               "<b>قیمت Limit سفارش</b>\n\nقیمت Limit را وارد کنید.",
               "<b>Stop-Limit Price</b>\n\nEnter the Limit price used after the Stop trigger is activated."),
            kb(nav(lang,"admin_signals"))
        )
        return
    await state.set_state(Flow.signal_sl)
    await screen(bot,message.from_user.id,message.chat.id,
                 tr(lang,"<b>حدضرر</b>\n\nحد ضرر را وارد کنید.","<b>Stop Loss</b>\n\nEnter stop loss."),
                 kb(nav(lang,"admin_signals")))

@router.message(Flow.signal_stop_limit)
async def signal_stop_limit(message: Message, bot: Bot, state: FSMContext):
    if not is_admin(message.from_user.id): return
    try: value=_fnum(message.text or "")
    except Exception:
        await clean_user_message(message); return
    if value <= 0:
        await clean_user_message(message); return
    await state.update_data(signal_stop_limit_price=value)
    await clean_user_message(message)
    await state.set_state(Flow.signal_sl)
    lang=get_lang(message.from_user.id)
    await screen(bot,message.from_user.id,message.chat.id,
                 tr(lang,"<b>حدضرر</b>\n\nحد ضرر را وارد کنید.","<b>Stop Loss</b>\n\nEnter stop loss."),
                 kb(nav(lang,"admin_signals")))

@router.message(Flow.signal_sl)
async def signal_sl(message: Message, bot: Bot, state: FSMContext):
    if not is_admin(message.from_user.id): return
    try: value=_fnum(message.text or "")
    except Exception:
        await clean_user_message(message); return
    await state.update_data(signal_sl=value, signal_targets=[])
    await clean_user_message(message)
    await state.set_state(Flow.signal_tp_count)
    lang=get_lang(message.from_user.id)
    await screen(
        bot,message.from_user.id,message.chat.id,
        tr(lang,
           "<b>تعداد حدسود</b>\n\nتعداد تارگت‌های این سیگنال را وارد کنید. مثال: <code>2</code> یا <code>10</code>\nحداکثر: 30",
           "<b>Take Profit Count</b>\n\nEnter how many targets this signal has, e.g. <code>2</code> or <code>10</code>.\nMaximum: 30"),
        kb(nav(lang,"admin_signals"))
    )


@router.message(Flow.signal_tp_count)
async def signal_tp_count(message: Message, bot: Bot, state: FSMContext):
    if not is_admin(message.from_user.id): return
    raw=_normalize_numeric_text(message.text or "")
    try: count=int(raw)
    except Exception:
        await clean_user_message(message); return
    if count < 1 or count > 30:
        await clean_user_message(message); return
    await state.update_data(signal_tp_count=count, signal_targets=[], signal_tp_index=1)
    await clean_user_message(message)
    await state.set_state(Flow.signal_tp_value)
    lang=get_lang(message.from_user.id)
    await screen(
        bot,message.from_user.id,message.chat.id,
        tr(lang,
           f"<b>TP1 از {count}</b>\n\nقیمت TP1 را وارد کنید.",
           f"<b>TP1 of {count}</b>\n\nEnter TP1 price."),
        kb(nav(lang,"admin_signals"))
    )


def _position_prompt(lang: str, market: str) -> str:
    return tr(
        lang,
        "<b>حجم ثابت</b>\n\nحجم معامله را به لات وارد کنید. مثال: <code>0.10</code>",
        "<b>Fixed Lot</b>\n\nEnter the trade volume in lots, e.g. <code>0.10</code>",
    )


@router.message(Flow.signal_tp_value)
async def signal_tp_value(message: Message, bot: Bot, state: FSMContext):
    if not is_admin(message.from_user.id): return
    try: value=_fnum(message.text or "")
    except Exception:
        await clean_user_message(message); return
    data=await state.get_data()
    count=int(data.get("signal_tp_count") or 0)
    index=int(data.get("signal_tp_index") or 1)
    targets=list(data.get("signal_targets") or [])
    targets.append(float(value))
    await clean_user_message(message)
    if index < count:
        next_index=index+1
        await state.update_data(signal_targets=targets, signal_tp_index=next_index)
        lang=get_lang(message.from_user.id)
        await screen(
            bot,message.from_user.id,message.chat.id,
            tr(lang,
               f"<b>TP{next_index} از {count}</b>\n\nقیمت TP{next_index} را وارد کنید.",
               f"<b>TP{next_index} of {count}</b>\n\nEnter TP{next_index} price."),
            kb(nav(lang,"admin_signals"))
        )
        return

    await state.update_data(signal_targets=targets, signal_tp_index=count)
    lang=get_lang(message.from_user.id)
    market=str(data.get("signal_market") or "FOREX")
    await state.set_state(None)
    await screen(
        bot,message.from_user.id,message.chat.id,
        tr(lang,
           "<b>روش محاسبه حجم</b>\n\nانتخاب کنید: مدیریت ریسک بر اساس درصد سرمایه و فاصله SL، یا حجم ثابت لات. دسته‌بندی بازار فقط برای گزارش‌گیری است و هیچ تفاوتی در اجرای معامله ایجاد نمی‌کند.",
           "<b>Position Sizing Method</b>\n\nChoose Risk Management based on account risk and SL distance, or Fixed Lot. Market category is reporting-only and does not change execution."),
        signal_volume_mode_menu(lang),
    )


@router.callback_query(F.data.startswith("sigvol:"))
async def signal_volume_mode_pick(cb: CallbackQuery, bot: Bot, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    mode=cb.data.split(":",1)[1].upper(); lang=get_lang(cb.from_user.id)
    if mode not in {"RISK","FIXED"}: return
    await state.update_data(signal_volume_mode=mode)
    await cb.answer()
    if mode == "FIXED":
        await state.set_state(Flow.signal_position)
        await screen(bot,cb.from_user.id,cb.message.chat.id,
                     tr(lang,"<b>حجم ثابت</b>\n\nحجم معامله را وارد کنید. مثال: <code>0.02</code>\n\nاین مقدار برای اجرای معاملات خودکار ملاک خواهد بود.",
                        "<b>Fixed Lot</b>\n\nEnter Lot Size, e.g. <code>0.02</code>.\n\nAuto Trade will use this exact sizing mode."),
                     kb(nav(lang,"admin_signals")))
    else:
        await state.set_state(Flow.signal_risk)
        await screen(bot,cb.from_user.id,cb.message.chat.id,
                     tr(lang,"<b>مدیریت ریسک</b>\n\nدرصد ریسک حساب را وارد کنید؛ مثال: <code>1</code>\n\nاکسپرت حجم را با توجه به Balance و فاصله ورود تا SL محاسبه می‌کند.",
                        "<b>Risk Management</b>\n\nEnter account risk %, e.g. <code>1</code>.\n\nThe EA calculates volume from balance and Entry-to-SL distance."),
                     kb(nav(lang,"admin_signals")))


@router.message(Flow.signal_position)
async def signal_position_input(message: Message, bot: Bot, state: FSMContext):
    if not is_admin(message.from_user.id): return
    try: value=_fnum(message.text or "")
    except Exception: await clean_user_message(message); return
    if value <= 0: await clean_user_message(message); return
    data=await state.get_data(); market=str(data.get("signal_market") or "FOREX")
    key="signal_lot"
    if value > 100000: await clean_user_message(message); return
    await state.update_data(**{key:value}); await clean_user_message(message); lang=get_lang(message.from_user.id)
    if str(data.get("signal_volume_mode") or "").upper() == "FIXED":
        await state.update_data(signal_risk=0.0)
        await state.set_state(None)
        await screen(bot,message.from_user.id,message.chat.id,
                     tr(lang,"<b>نوع حدضرر متحرک</b>\n\nپروفایل مدیریت تریلینگ را انتخاب کنید. قوانین این مدل روی معاملات خودکار قفل می‌شود.",
                        "<b>Trailing Type</b>\n\nChoose the trailing profile. This profile is locked for Auto Trade management."),
                     signal_trailing_preset_menu(lang))
    else:
        await state.set_state(Flow.signal_risk)
        await screen(bot,message.from_user.id,message.chat.id,tr(lang,"<b>ریسک</b>\n\nدرصد ریسک را وارد کنید؛ مثال: <code>1</code>","<b>Risk</b>\n\nEnter risk percent, e.g. <code>1</code>"),kb(nav(lang,"admin_signals")))


@router.message(Flow.signal_risk)
async def signal_risk(message: Message, bot: Bot, state: FSMContext):
    if not is_admin(message.from_user.id): return
    try: risk=_fnum(message.text or "")
    except Exception: await clean_user_message(message); return
    if risk<=0 or risk>100: await clean_user_message(message); return
    data=await state.get_data()
    updates={"signal_risk":risk, "signal_volume_mode":"RISK"}
    await state.update_data(**updates); await clean_user_message(message); await state.set_state(None); lang=get_lang(message.from_user.id)
    await screen(bot,message.from_user.id,message.chat.id,tr(lang,"<b>نوع حدضرر متحرک</b>\n\nپروفایل مدیریت تریلینگ را انتخاب کنید.","<b>Trailing Type</b>\n\nChoose the trailing-management profile."),signal_trailing_preset_menu(lang))


@router.callback_query(F.data.startswith("sigtrail:"))
async def signal_trailing_pick(cb: CallbackQuery, bot: Bot, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    code=cb.data.split(":",1)[1]; presets=dict(TRAILING_PRESETS); name=presets.get(code); lang=get_lang(cb.from_user.id)
    if not name: return
    await state.update_data(signal_trailing_code=code,signal_trailing_name=name); await cb.answer()
    await screen(bot,cb.from_user.id,cb.message.chat.id,tr(lang,"<b>مقصد انتشار</b>\n\nسیگنال در کدام کانال ارسال شود؟","<b>Publish Destination</b>\n\nWhere should the signal be published?"),signal_destination_menu(lang))


@router.callback_query(F.data.startswith("sigdest:"))
async def signal_destination(cb: CallbackQuery, bot: Bot, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    dest=cb.data.split(":",1)[1]
    if dest not in {"FREE","VIP","BOTH"}: return
    await state.update_data(signal_destination=dest); data=await state.get_data(); lang=get_lang(cb.from_user.id); await cb.answer()
    targets=[float(v) for v in (data.get("signal_targets") or [])]
    if not targets:
        await cb.answer(tr(lang,"حداقل یک TP لازم است.","At least one TP is required."),show_alert=True); return
    target=targets[-1]
    rr=_rr(float(data["signal_entry"]),float(data["signal_sl"]),float(target),str(data["signal_direction"]))
    await state.update_data(signal_rr=rr)
    if lang == "fa":
        direction_text={"BUY":"خرید","SELL":"فروش","LONG":"لانگ","SHORT":"شورت"}.get(str(data["signal_direction"]).upper(),str(data["signal_direction"]))
        market_text="فارکس" if data["signal_market"]=="FOREX" else "کریپتو"
        dest_text={"FREE":"عمومی","VIP":"VIP","BOTH":"هر دو"}.get(dest,dest)
        vm=str(data.get("signal_volume_mode") or "RISK").upper()
        extra=(f"روش حجم: <b>Fixed Lot</b>\nحجم: <b>{float(data.get('signal_lot') or 0):g} لات</b>\n" if vm=="FIXED" else f"روش حجم: <b>Risk Management</b>\nریسک: <b>{float(data['signal_risk']):g}%</b>\n")
        tp_lines="\n".join(f"هدف {i}: <code>{_format_price(price)}</code>" for i,price in enumerate(targets,1))
        preview=(f"<b>پیش‌نمایش سیگنال</b>\n\n"
                 f"نماد: <b>{escape(str(data['signal_symbol']))}</b>\n"
                 f"جهت: <b>{escape(direction_text)}</b>\n"
                 f"بازار: <b>{market_text}</b>\n"
                 f"نوع سفارش: <b>{escape(str(data.get('signal_order_type') or 'MARKET'))}</b>\nتایم‌فریم: <b>{escape(str(data.get('signal_timeframe') or 'M5'))}</b>\n\n"
                 f"ورود: <code>{_format_price(data['signal_entry'])}</code>\n"
                 f"حد ضرر: <code>{_format_price(data['signal_sl'])}</code>\n"
                 f"{tp_lines}\n\n"
                 f"{extra}"
                 f"نسبت سود به زیان: <b>{('1:'+format(rr,'g')) if rr else '—'}</b>\n\n"
                 f"تریلینگ: <b>{escape(str(data['signal_trailing_code']))}</b>\n"
                 f"{escape(str(data['signal_trailing_name']))}\n\n"
                 f"مقصد: <b>{dest_text}</b>")
    else:
        vm=str(data.get("signal_volume_mode") or "RISK").upper()
        extra=(f"Sizing: <b>Fixed Lot</b>\nLot Size: <b>{float(data.get('signal_lot') or 0):g}</b>\n" if vm=="FIXED" else f"Sizing: <b>Risk Management</b>\nRisk: <b>{float(data['signal_risk']):g}%</b>\n")
        tp_lines="\n".join(f"TP{i}: <code>{_format_price(price)}</code>" for i,price in enumerate(targets,1))
        preview=(f"<b>Signal Preview</b>\n\n"
                 f"Symbol: <b>{escape(str(data['signal_symbol']))}</b>\n"
                 f"Direction: <b>{escape(str(data['signal_direction']))}</b>\n"
                 f"Market: <b>{escape(str(data['signal_market']))}</b>\n"
                 f"Order Type: <b>{escape(str(data.get('signal_order_type') or 'MARKET'))}</b>\n\n"
                 f"Entry: <code>{_format_price(data['signal_entry'])}</code>\n"
                 f"SL: <code>{_format_price(data['signal_sl'])}</code>\n"
                 f"{tp_lines}\n\n"
                 f"{extra}"
                 f"R:R: <b>{('1:'+format(rr,'g')) if rr else '—'}</b>\n\n"
                 f"Trailing: <b>{escape(str(data['signal_trailing_code']))}</b>\n"
                 f"{escape(str(data['signal_trailing_name']))}\n\n"
                 f"Destination: <b>{dest}</b>")
    await screen(bot,cb.from_user.id,cb.message.chat.id,preview,signal_confirm_menu(lang))


@router.callback_query(F.data == "sigpublish")
async def signal_publish(cb: CallbackQuery, bot: Bot, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    lang=get_lang(cb.from_user.id)
    lock=SIGNAL_PUBLISH_LOCKS.setdefault(cb.from_user.id,asyncio.Lock())
    if lock.locked():
        await cb.answer(tr(lang,"⏳ انتشار همین سیگنال در حال انجام است. دوباره کلیک نکنید.","⏳ This signal is already being published. Do not click again."),show_alert=True)
        return
    async with lock:
        data=await state.get_data()
        if data.get("signal_publish_committed"):
            await cb.answer(tr(lang,"✅ این سیگنال قبلاً برای انتشار ثبت شده است.","✅ This signal has already been committed for publication."),show_alert=True)
            return
        required=["signal_market","signal_symbol","signal_direction","signal_timeframe","signal_order_type","signal_entry","signal_sl","signal_targets","signal_risk","signal_volume_mode","signal_trailing_code","signal_trailing_name","signal_destination"]
        if str(data.get("signal_volume_mode")).upper() == "FIXED":
            required.append("signal_lot")
        if str(data.get("signal_order_type")).upper() in {"BUY_STOP_LIMIT","SELL_STOP_LIMIT"}:
            required.append("signal_stop_limit_price")
        if any(k not in data for k in required):
            await cb.answer(tr(lang,"اطلاعات سیگنال ناقص است.","Signal data is incomplete."),show_alert=True); return

        order_type = str(data.get("signal_order_type") or "MARKET").upper()
        direction = str(data.get("signal_direction") or "").upper()
        if order_type in {"BUY_LIMIT","BUY_STOP","BUY_STOP_LIMIT"} and direction not in {"BUY","LONG"}:
            await cb.answer(tr(lang,"نوع سفارش خرید با جهت فروش سازگار نیست.","A BUY pending type requires BUY/LONG direction."),show_alert=True); return
        if order_type in {"SELL_LIMIT","SELL_STOP","SELL_STOP_LIMIT"} and direction not in {"SELL","SHORT"}:
            await cb.answer(tr(lang,"نوع سفارش فروش با جهت خرید سازگار نیست.","A SELL pending type requires SELL/SHORT direction."),show_alert=True); return

        # Commit the draft before any network call. A second click cannot create another Signal ID.
        await state.update_data(signal_publish_committed=True)
        await cb.answer(tr(lang,"⏳ در حال انتشار… لطفاً صبر کنید.","⏳ Publishing… please wait."))
        row=None
        try:
            row=db.create_signal(
                market_type=data["signal_market"],symbol=data["signal_symbol"],direction=data["signal_direction"],
                entry_price=float(data["signal_entry"]),stop_loss=float(data["signal_sl"]),targets=[float(v) for v in data["signal_targets"]],
                risk_percent=float(data["signal_risk"]),
                rr_ratio=data.get("signal_rr"),destination=data["signal_destination"],chart_file_id=data.get("signal_chart_file_id"),
                created_by=cb.from_user.id,lot_size=data.get("signal_lot"),leverage=None,
                timeframe=str(data.get("signal_timeframe") or "M5"),
                trailing_code=data.get("signal_trailing_code"),trailing_name=data.get("signal_trailing_name"),
                order_type=str(data.get("signal_order_type") or "MARKET"),
                 stop_limit_price=(float(data["signal_stop_limit_price"]) if str(data.get("signal_order_type") or "").upper() in {"BUY_STOP_LIMIT","SELL_STOP_LIMIT"} else None),
                max_entry_deviation_abs=(settings.autotrade_xauusd_max_entry_deviation_abs if str(data.get("signal_symbol") or "").upper().replace("/","").replace("-","").startswith("XAUUSD") else None),
                max_entry_deviation_pct=(None if str(data.get("signal_symbol") or "").upper().replace("/","").replace("-","").startswith("XAUUSD") else settings.autotrade_default_max_entry_deviation_pct),
                volume_mode=str(data.get("signal_volume_mode") or "RISK"),
                publish_token=str(data.get("signal_publish_token") or "") or None,
            )
            free_id,vip_id,errors=await _publish_signal(bot,row)
            db.add_audit(cb.from_user.id,"create_signal",int(row["id"]),f"{row['code']} {row['destination']} free={free_id} vip={vip_id}")
            await state.clear()
            if errors:
                err_text="\n".join(f"• {escape(e[:350])}" for e in errors)
                if free_id or vip_id:
                    title=tr(lang,"⚠️ سیگنال به‌صورت ناقص منتشر شد.","⚠️ Signal was partially published.")
                else:
                    title=tr(lang,"❌ سیگنال در کانال مقصد منتشر نشد.","❌ Signal was not published to the destination channel.")
                await screen(bot,cb.from_user.id,cb.message.chat.id,f"{title}\n\n{err_text}\n\n"+tr(lang,"برای انتشار مجدد از دکمه تلاش مجدد همان سیگنال استفاده کنید؛ سیگنال جدید نسازید.","Use Retry on the same Signal; do not create a second signal."),signal_center_menu(lang))
            else:
                await screen(bot,cb.from_user.id,cb.message.chat.id,tr(lang,f"✅ <b>{row['code']}</b> منتشر شد.\n\n{escape(row['symbol'])} — {escape(row['direction'])}\nمقصد: <b>{escape(row['destination'])}</b>\n\n🔒 انتشار تکراری این Signal ID مسدود است.",f"✅ <b>{row['code']}</b> published.\n\n{escape(row['symbol'])} — {escape(row['direction'])}\nDestination: <b>{escape(row['destination'])}</b>\n\n🔒 Duplicate publication for this Signal ID is blocked."),signal_center_menu(lang))
        except Exception as exc:
            log.exception("signal publish failed")
            # If a DB signal already exists, clear the draft and force Retry on that signal.
            if row is not None:
                await state.clear()
            else:
                await state.update_data(signal_publish_committed=False)
            await screen(bot,cb.from_user.id,cb.message.chat.id,tr(lang,f"❌ خطا در انتشار:\n<code>{escape(str(exc))}</code>",f"❌ Publication error:\n<code>{escape(str(exc))}</code>"),signal_center_menu(lang))

@router.callback_query(F.data.startswith("sigretry:"))
async def signal_retry_publish(cb: CallbackQuery, bot: Bot):
    if not is_admin(cb.from_user.id): return
    sid=int(cb.data.split(":",1)[1]); row=db.get_signal(sid); lang=get_lang(cb.from_user.id)
    if not row or row["status"]=="CLOSED":
        await cb.answer(tr(lang,"سیگنال پیدا نشد یا بسته شده است.","Signal not found or already closed."),show_alert=True); return
    await cb.answer(tr(lang,"در حال تلاش مجدد…","Retrying…"))
    free_id,vip_id,errors=await _publish_signal(bot,row,only_missing=True)
    db.add_audit(cb.from_user.id,"signal_retry_publish",sid,f"free={free_id} vip={vip_id} errors={len(errors)}")
    if errors:
        text=tr(lang,"⚠️ تلاش مجدد کامل نشد.","⚠️ Retry was not fully successful.")+"\n\n"+"\n".join(f"• {escape(e[:350])}" for e in errors)
    else:
        text=tr(lang,"✅ انتشار سیگنال کامل شد.","✅ Signal publication completed.")
    fresh=db.get_signal(sid)
    await screen(bot,cb.from_user.id,cb.message.chat.id,text,signal_manage_menu(sid,lang) if fresh else signal_center_menu(lang))


async def _render_admin_signal_center(bot: Bot, user_id: int, chat_id: int) -> None:
    lang = get_lang(user_id)
    # The Admin Live Center is intentionally NOT signal-history driven. It only
    # renders broker-confirmed current positions/orders from the MT5 snapshot.
    # This prevents stale NX-0002...NX-0009 rows from surviving a fresh DB.
    accounts = db.mt5_live_accounts()
    now = datetime.now(timezone.utc)
    live_accounts=[]
    positions=[]; orders=[]
    for a in accounts:
        try:
            seen=datetime.fromisoformat(str(a["last_seen_at"]).replace("Z","+00:00"))
        except Exception:
            continue
        age=max(0,(now-seen).total_seconds())
        if age <= max(15, settings.autotrade_notification_ttl_seconds*2):
            live_accounts.append((a,age))
            positions.extend(db.mt5_live_positions(str(a["account_number"]),nexus_only=True))
            orders.extend(db.mt5_live_orders(str(a["account_number"]),nexus_only=True))

    lines=[tr(lang,"<b>📡 مرکز زنده MT5 — فقط وضعیت فعلی</b>","<b>📡 MT5 Live Center — Current State Only</b>"),""]
    if live_accounts:
        for a,age in live_accounts:
            lines.append(tr(lang,
                f"🟢 <b>ONLINE</b> | حساب: <code>{escape(str(a['account_number']))}</code> | Broker: {escape(str(a.get('broker') or '—'))} | Sync: {int(age)}s",
                f"🟢 <b>ONLINE</b> | Account: <code>{escape(str(a['account_number']))}</code> | Broker: {escape(str(a.get('broker') or '—'))} | Sync: {int(age)}s"))
    else:
        lines.append(tr(lang,"🔴 <b>MT5 OFFLINE / NO LIVE HEARTBEAT</b>","🔴 <b>MT5 OFFLINE / NO LIVE HEARTBEAT</b>"))
    lines.append("")
    lines.append(tr(lang,f"🟢 معاملات باز: <b>{len(positions)}</b> | سفارش‌های Pending: <b>{len(orders)}</b>",f"🟢 Open positions: <b>{len(positions)}</b> | Pending orders: <b>{len(orders)}</b>"))
    buttons=[]
    for r in positions:
        code=str(r.get("signal_code") or "MANUAL")
        label=f"{code} | {r.get('symbol','')} {r.get('direction','')} | {float(r.get('volume') or 0):g} | #{r.get('ticket','')}"
        sid=0
        row=db.get_signal_by_code(code) if code.startswith("NX-") else None
        if row: sid=int(row["id"])
        if sid:
            buttons.append([(label,f"sigmanage:{sid}")])
        else:
            lines.append(escape(label))
    for r in orders:
        code=str(r.get("signal_code") or "MANUAL")
        label=f"⏳ {code} | {r.get('symbol','')} {r.get('direction','')} | {float(r.get('volume') or 0):g} | #{r.get('ticket','')}"
        sid=0; row=db.get_signal_by_code(code) if code.startswith("NX-") else None
        if row: sid=int(row["id"])
        if sid: buttons.append([(label,f"sigmanage:{sid}")])
        else: lines.append(escape(label))
    if not positions and not orders:
        lines.append(tr(lang,"هیچ معامله یا سفارش فعالی در MT5 وجود ندارد.","No active MT5 position or pending order."))
    lines.append("")
    lines.append(tr(lang,"🔒 منبع: MT5 Live Snapshot؛ تاریخچه سیگنال نمایش داده نمی‌شود.","🔒 Source: MT5 Live Snapshot; signal history is not shown."))
    buttons.append([(tr(lang,"🔄 همگام‌سازی زنده","🔄 Live Sync"),"signal_refresh")])
    buttons += nav(lang,"admin_signals")
    await screen(bot,user_id,chat_id,"\n".join(lines),kb(buttons))


async def _replace_callback_dashboard_message(cb: CallbackQuery) -> None:
    """Delete the clicked legacy dashboard as well as the DB-tracked dashboard.

    Fresh DB starts without the message id of an older Telegram process. When
    an admin clicks an old panel button, deleting that callback message prevents
    legacy NX-xxxx lists from remaining visible beside the new Live Center.
    """
    try:
        if cb.message:
            await cb.message.delete()
    except Exception:
        pass


@router.callback_query(F.data == "signal_refresh")
async def signal_refresh(cb: CallbackQuery, bot: Bot):
    if not is_admin(cb.from_user.id): return
    await cb.answer(tr(get_lang(cb.from_user.id), "وضعیت زنده تازه شد.", "Live state refreshed."))
    await _replace_callback_dashboard_message(cb)
    await _render_admin_signal_center(bot, cb.from_user.id, cb.message.chat.id)


@router.callback_query(F.data == "signal_active")
async def signal_active(cb: CallbackQuery, bot: Bot):
    if not is_admin(cb.from_user.id): return
    await cb.answer()
    await _replace_callback_dashboard_message(cb)
    await _render_admin_signal_center(bot, cb.from_user.id, cb.message.chat.id)

@router.callback_query(F.data.startswith("sigmanage:"))
async def signal_manage(cb: CallbackQuery, bot: Bot):
    """Read-only MT5 signal detail view; Telegram cannot mutate signals."""
    if not is_admin(cb.from_user.id): return
    sid=int(cb.data.split(":",1)[1]); row=db.get_signal(sid); lang=get_lang(cb.from_user.id); await cb.answer()
    if not row or str(row["issuer_type"] or "").upper() != "MT5_ADMIN":
        await screen(bot, cb.from_user.id, cb.message.chat.id, tr(lang,"سیگنال MT5 پیدا نشد.","MT5 signal not found."), kb(nav(lang,"signal_active")))
        return
    targets=db.get_signal_targets(sid)
    tp_text=" / ".join(_format_price(t["price"]) for t in targets) if targets else "—"
    status_map={"ACTIVE":"فعال","CLOSED":"بسته","BREAK_EVEN":"سر به سر","PARTIAL":"بخشی بسته شده","TRAILING":"تریلینگ","REJECTED":"رد شده","CANCELLED":"لغو شده","EXPIRED":"منقضی شده"}
    status=str(row["status"] or "—")
    live = db.mt5_signal_live_state(sid)
    live_rows = db.mt5_live_for_signal(str(row["code"]), str(row["issuer_account"] or ""))
    receipt_status = str(live.get("receipt_status") or "NOT_RECEIVED")
    trade_status = str(live.get("trade_status") or "NO_TRADE")
    ticket = str(live.get("ticket") or "")
    live_error = str(live.get("receipt_error") or "")
    if live_rows:
        lr=live_rows[0]
        trade_status=str(lr.get("status") or trade_status).upper()
        ticket=str(lr.get("ticket") or ticket)
        live_fa=(f"رسید MT5: <b>{escape(receipt_status)}</b>\nوضعیت زنده: <b>{escape(trade_status)}</b>\n"
                  f"Ticket: <code>{escape(ticket)}</code>\nحجم واقعی: <b>{float(lr.get('volume') or 0):g}</b>\n"
                  f"قیمت ورود واقعی: <code>{float(lr.get('entry_price') or 0):g}</code>\n"
                  f"P/L: <b>{float(lr.get('profit') or 0):g}</b>")
        live_en=(f"MT5 Receipt: <b>{escape(receipt_status)}</b>\nLive State: <b>{escape(trade_status)}</b>\n"
                  f"Ticket: <code>{escape(ticket)}</code>\nExecuted Volume: <b>{float(lr.get('volume') or 0):g}</b>\n"
                  f"Executed Entry: <code>{float(lr.get('entry_price') or 0):g}</code>\n"
                  f"P/L: <b>{float(lr.get('profit') or 0):g}</b>")
    else:
        live_fa = f"رسید MT5: <b>{escape(receipt_status)}</b>\nوضعیت زنده: <b>{escape(trade_status)}</b>" + (f"\nخطا: <code>{escape(live_error[:500])}</code>" if live_error else "")
        live_en = f"MT5 Receipt: <b>{escape(receipt_status)}</b>\nLive State: <b>{escape(trade_status)}</b>" + (f"\nError: <code>{escape(live_error[:500])}</code>" if live_error else "")
    if lang == "fa":
        text=(f"<b>📈 {escape(row['code'])}</b>\n\n"
              f"نماد: <b>{escape(row['symbol'])}</b>\nجهت: <b>{escape(row['direction'])}</b>\n"
              f"وضعیت: <b>{escape(status_map.get(status,status))}</b>\n"
              f"نوع سفارش: <b>{escape(str(row['order_type'] or 'MARKET'))}</b>\n"
              f"Entry: <code>{_format_price(row['entry_price'])}</code>\nSL: <code>{_format_price(row['stop_loss'])}</code>\n"
              f"TPها: <code>{escape(tp_text)}</code>\nمقصد: <b>{escape(row['destination'])}</b>\n"
              f"Trailing: <b>{escape(str(row['trailing_code'] or '—'))}</b>\nIssuer: <b>MT5 ADMIN</b>\n\n{live_fa}")
    else:
        text=(f"<b>📈 {escape(row['code'])}</b>\n\n"
              f"Symbol: <b>{escape(row['symbol'])}</b>\nDirection: <b>{escape(row['direction'])}</b>\n"
              f"Status: <b>{escape(status)}</b>\nOrder Type: <b>{escape(str(row['order_type'] or 'MARKET'))}</b>\n"
              f"Entry: <code>{_format_price(row['entry_price'])}</code>\nSL: <code>{_format_price(row['stop_loss'])}</code>\n"
              f"TPs: <code>{escape(tp_text)}</code>\nDestination: <b>{escape(row['destination'])}</b>\n"
              f"Trailing: <b>{escape(str(row['trailing_code'] or '—'))}</b>\nIssuer: <b>MT5 ADMIN</b>\n\n{live_en}")
    await screen(bot,cb.from_user.id,cb.message.chat.id,text,signal_readonly_menu(lang))


@router.callback_query(F.data.startswith("sigact:"))
async def signal_action(cb: CallbackQuery, bot: Bot, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return
    _, action, sid_s = cb.data.split(":", 2)
    sid = int(sid_s)
    row = db.get_signal(sid)
    lang = get_lang(cb.from_user.id)
    channel_lang = get_lang(int(row["created_by"])) if row else lang
    if not row or row["status"] == "CLOSED":
        await cb.answer(tr(lang, "سیگنال بسته شده یا پیدا نشد.", "Signal is closed or not found."), show_alert=True)
        return

    if action == "limitactive":
        if str(row["order_type"] if "order_type" in row.keys() and row["order_type"] else "MARKET").upper() != "LIMIT":
            await cb.answer(tr(lang,"این سیگنال لیمیت نیست.","This signal is not a Limit order."),show_alert=True); return
        if row["limit_activated_at"] if "limit_activated_at" in row.keys() else None:
            await cb.answer(tr(lang,"این لیمیت قبلاً فعال اعلام شده است.","This Limit was already marked activated."),show_alert=True); return
        await cb.answer(tr(lang,"در حال اعلام فعال شدن لیمیت…","Publishing Limit activation…"))
        text=tr(channel_lang,
            f"<b>✅ سفارش Limit فعال شد</b>\n\n{escape(str(row['code']))} — {escape(str(row['symbol']))} {escape(str(row['direction']))}\nقیمت ورود: {_copy_price(row['entry_price'])}\n\nمدیریت معامله طبق Trailing انتخاب‌شده ادامه دارد.",
            f"<b>✅ LIMIT ORDER ACTIVATED</b>\n\n{escape(str(row['code']))} — {escape(str(row['symbol']))} {escape(str(row['direction']))}\nEntry: {_copy_price(row['entry_price'])}\n\nTrade management continues with the selected Trailing profile.")
        fm,vm,errors=await _reply_signal_update(bot,row,text)
        if not fm and not vm:
            await screen(bot,cb.from_user.id,cb.message.chat.id,tr(lang,"❌ پیام فعال شدن لیمیت در کانال ارسال نشد.","❌ Limit activation could not be posted.")+"\n\n"+"\n".join(f"• {escape(e[:300])}" for e in errors),signal_manage_menu(sid,lang)); return
        db.mark_limit_activated(sid)
        db.add_signal_update(sid,"LIMIT_ACTIVATED","سفارش لیمیت فعال شد.","Limit order activated.",None,cb.from_user.id,fm,vm,"ACTIVE")
        db.add_audit(cb.from_user.id,"signal_limit_activated",sid,str(row["code"]))
        await screen(bot,cb.from_user.id,cb.message.chat.id,tr(lang,"✅ فعال شدن لیمیت اعلام شد.","✅ Limit activation announced."),signal_manage_menu(sid,lang))
        return

    if action == "be":
        # Ack before network I/O so Telegram never expires the callback query.
        await cb.answer(tr(lang, "در حال ارسال سر‌به‌سر…", "Publishing Break Even…"))
        text = tr(channel_lang,
            "<b>سر به سر</b>\n\nحد ضرر به نقطه ورود منتقل شد.\nمعامله بدون ریسک ادامه دارد.",
            "<b>BREAK EVEN</b>\n\nStop loss moved to entry.\nThe trade continues risk-free.")
        fm, vm, errors = await _reply_signal_update(bot, row, text)
        if not fm and not vm:
            err = "\n".join(f"• {escape(e[:350])}" for e in errors) or "• Channel reply failed"
            await screen(
                bot, cb.from_user.id, cb.message.chat.id,
                tr(lang, "❌ سر‌به‌سر ثبت نشد چون آپدیت در کانال ارسال نشد.", "❌ Break Even was not applied because the channel update could not be posted.")
                + "\n\n" + err,
                signal_manage_menu(sid, lang),
            )
            return
        db.update_signal_sl(sid, float(row["entry_price"]), status="BREAK_EVEN")
        db.add_signal_update(
            sid, "BREAK_EVEN",
            "حد ضرر به نقطه ورود منتقل شد و معامله بدون ریسک ادامه دارد.",
            "Stop loss moved to entry; the trade continues risk-free.",
            None, cb.from_user.id, fm, vm, "BREAK_EVEN",
        )
        db.add_audit(cb.from_user.id, "signal_break_even", sid, row["code"])
        latest = db.get_signal(sid)
        if lang == "fa":
            dir_text={"BUY":"خرید","SELL":"فروش","LONG":"لانگ","SHORT":"شورت"}.get(str(latest["direction"]).upper(),str(latest["direction"]))
            detail=(f"<b>{escape(latest['code'])}</b>\n\n{escape(latest['symbol'])} — {escape(dir_text)}\n"
                    f"وضعیت: <b>سر به سر</b>\nورود: <code>{_format_price(latest['entry_price'])}</code>\nحد ضرر: <code>{_format_price(latest['stop_loss'])}</code>")
        else:
            detail=(f"<b>{escape(latest['code'])}</b>\n\n{escape(latest['symbol'])} — {escape(latest['direction'])}\n"
                    f"Status: <b>{escape(latest['status'])}</b>\nEntry: <code>{_format_price(latest['entry_price'])}</code>\nSL: <code>{_format_price(latest['stop_loss'])}</code>")
        if errors:
            detail += "\n\n⚠️ " + "\n".join(escape(e[:300]) for e in errors)
        await screen(bot, cb.from_user.id, cb.message.chat.id, detail, signal_manage_menu(sid, lang))
        return

    if action == "trailing":
        await cb.answer(tr(lang, "در حال ارسال حدضرر متحرک…", "Publishing Trailing…"))
        code = str(row["trailing_code"] or "NEXUS_TRAIL_07")
        name = str(row["trailing_name"] or "NEXUS Smart Hybrid")
        text = tr(channel_lang,
            f"<b>تریلینگ فعال شد</b>\n\n<b>{escape(code)}</b>\n{escape(name)}\n\nمدیریت متحرک حد ضرر فعال شد.",
            f"<b>TRAILING ACTIVATED</b>\n\n<b>{escape(code)}</b>\n{escape(name)}\n\nDynamic stop management is active.")
        fm, vm, errors = await _reply_signal_update(bot, row, text)
        if not fm and not vm:
            err = "\n".join(f"• {escape(e[:350])}" for e in errors) or "• Channel reply failed"
            await screen(bot, cb.from_user.id, cb.message.chat.id,
                         tr(lang, "❌ حدضرر متحرک در کانال ارسال نشد.", "❌ Trailing could not be posted to the channel.") + "\n\n" + err,
                         signal_manage_menu(sid, lang))
            return
        db.add_signal_update(sid, "TRAILING", f"{code} - {name} فعال شد.", f"{code} - {name} activated.", code, cb.from_user.id, fm, vm, "TRAILING")
        db.add_audit(cb.from_user.id, "signal_trailing", sid, code)
        msg = tr(lang, f"✅ {escape(code)} فعال شد.", f"✅ {escape(code)} activated.")
        if errors:
            msg += "\n\n⚠️ " + "\n".join(escape(e[:300]) for e in errors)
        await screen(bot, cb.from_user.id, cb.message.chat.id, msg, signal_manage_menu(sid, lang))
        return

    if action == "close":
        # Dedicated close flow: always make the exit-price request visible first.
        await cb.answer(tr(lang, "قیمت خروج را وارد کنید.", "Enter the exit price."))
        await state.clear()
        await state.set_state(Flow.signal_close_exit)
        await state.update_data(signal_target_id=sid)
        prompt = tr(
            lang,
            f"<b>بستن {escape(row['code'])} — مرحله ۱/۲</b>\n\nقیمت خروج نهایی را وارد کنید.\nمثال: <code>2345.50</code>",
            f"<b>Close {escape(row['code'])} — Step 1/2</b>\n\nEnter the final exit price.\nExample: <code>2345.50</code>",
        )
        await screen(bot, cb.from_user.id, cb.message.chat.id, prompt, kb(nav(lang, f"sigmanage:{sid}")))
        return

    target_state = {
        "partial": Flow.signal_partial,
        "tp": Flow.signal_update_tp,
        "sl": Flow.signal_update_sl,
    }.get(action)
    if not target_state:
        await cb.answer()
        return
    await cb.answer()
    await state.clear()
    await state.set_state(target_state)
    await state.update_data(signal_target_id=sid)
    prompts = {
        "partial": ("درصد حجم بسته‌شده را وارد کنید؛ مثال: <code>50</code>", "Enter closed position percentage, e.g. <code>50</code>"),
        "tp": ("تارگت جدید را به شکل <code>TP7=1.0950</code> وارد کنید. شماره TP باید از تارگت‌های همین سیگنال باشد.", "Enter a target like <code>TP7=1.0950</code>. The TP number must already exist on this signal."),
        "sl": ("حد ضرر جدید را وارد کنید.", "Enter new stop loss."),
    }
    fa, en = prompts[action]
    await screen(bot, cb.from_user.id, cb.message.chat.id, tr(lang, fa, en), kb(nav(lang, f"sigmanage:{sid}")))


@router.message(Flow.signal_partial)
async def signal_partial_input(message: Message, bot: Bot, state: FSMContext):
    if not is_admin(message.from_user.id): return
    data = await state.get_data()
    sid = int(data["signal_target_id"])
    row = db.get_signal(sid)
    lang = get_lang(message.from_user.id)
    channel_lang = get_lang(int(row["created_by"])) if row else lang
    try:
        pct = _fnum(message.text or "")
    except Exception:
        await clean_user_message(message)
        await screen(bot, message.from_user.id, message.chat.id,
                     tr(lang, "درصد معتبر وارد کنید؛ مثال: <code>50</code>", "Enter a valid percentage, e.g. <code>50</code>"),
                     kb(nav(lang, f"sigmanage:{sid}")))
        return
    if pct <= 0 or pct > 100:
        await clean_user_message(message)
        await screen(bot, message.from_user.id, message.chat.id,
                     tr(lang, "درصد باید بین 0 و 100 باشد.", "Percentage must be between 0 and 100."),
                     kb(nav(lang, f"sigmanage:{sid}")))
        return
    await clean_user_message(message)
    text = tr(channel_lang, f"<b>بستن بخشی از معامله</b>\n\n<b>{pct:g}%</b> از حجم معامله بسته شد.\nبخش باقی‌مانده فعال است.", f"<b>PARTIAL CLOSE</b>\n\n<b>{pct:g}%</b> of the position was closed.\nThe remainder stays active.")
    fm, vm, errors = await _reply_signal_update(bot, row, text)
    if not fm and not vm:
        err = "\n".join(f"• {escape(e[:350])}" for e in errors) or "• Channel reply failed"
        await state.clear()
        await screen(bot, message.from_user.id, message.chat.id,
                     tr(lang, "❌ بخشی در کانال ارسال نشد.", "❌ Partial update could not be posted.") + "\n\n" + err,
                     signal_manage_menu(sid, lang))
        return
    db.add_signal_update(sid, "PARTIAL", f"{pct:g}% از حجم معامله بسته شد؛ بخش باقی‌مانده فعال است.", f"{pct:g}% of the position was closed; the remainder stays active.", f"{pct:g}", message.from_user.id, fm, vm, "PARTIAL")
    db.add_audit(message.from_user.id, "signal_partial", sid, f"pct={pct:g}")
    await state.clear()
    msg = tr(lang, "✅ آپدیت بخشی منتشر شد.", "✅ Partial update published.")
    if errors:
        msg += "\n\n⚠️ " + "\n".join(escape(e[:300]) for e in errors)
    await screen(bot, message.from_user.id, message.chat.id, msg, signal_manage_menu(sid, lang))


@router.message(Flow.signal_trailing)
async def signal_trailing_input(message: Message, bot: Bot, state: FSMContext):
    if not is_admin(message.from_user.id): return
    data = await state.get_data()
    sid = int(data["signal_target_id"])
    row = db.get_signal(sid)
    value = (message.text or "").strip()[:60]
    lang = get_lang(message.from_user.id)
    channel_lang = get_lang(int(row["created_by"])) if row else lang
    await clean_user_message(message)
    text = tr(channel_lang, f"<b>تریلینگ فعال شد</b>\n\n<b>{escape(value)}</b>\n\nمدیریت متحرک حد ضرر فعال شد.", f"<b>TRAILING ACTIVATED</b>\n\n<b>{escape(value)}</b>\n\nDynamic stop management is active.")
    fm, vm, errors = await _reply_signal_update(bot, row, text)
    if not fm and not vm:
        await state.clear()
        err = "\n".join(f"• {escape(e[:350])}" for e in errors) or "• Channel reply failed"
        await screen(bot, message.from_user.id, message.chat.id,
                     tr(lang, "❌ حدضرر متحرک در کانال ارسال نشد.", "❌ Trailing could not be posted.") + "\n\n" + err,
                     signal_manage_menu(sid, lang))
        return
    db.add_signal_update(sid, "TRAILING", f"Trailing Stop با تنظیم {value} فعال شد.", f"Trailing Stop enabled with setting {value}.", value, message.from_user.id, fm, vm, "TRAILING")
    db.add_audit(message.from_user.id, "signal_trailing", sid, value)
    await state.clear()
    msg = tr(lang, "✅ تریلینگ منتشر شد.", "✅ Trailing update published.")
    if errors:
        msg += "\n\n⚠️ " + "\n".join(escape(e[:300]) for e in errors)
    await screen(bot, message.from_user.id, message.chat.id, msg, signal_manage_menu(sid, lang))


@router.message(Flow.signal_update_tp)
async def signal_tp_update_input(message: Message, bot: Bot, state: FSMContext):
    if not is_admin(message.from_user.id): return
    data = await state.get_data()
    sid = int(data["signal_target_id"])
    row = db.get_signal(sid)
    lang = get_lang(message.from_user.id)
    channel_lang = get_lang(int(row["created_by"])) if row else lang
    raw = (message.text or "").strip().upper()
    m = re.fullmatch(r"TP([1-9][0-9]?)\s*=\s*([0-9]+(?:[.,][0-9]+)?)", raw)
    if not m:
        await clean_user_message(message)
        await screen(bot, message.from_user.id, message.chat.id,
                     tr(lang, "فرمت صحیح: <code>TP2=1.0950</code>", "Correct format: <code>TP2=1.0950</code>"),
                     kb(nav(lang, f"sigmanage:{sid}")))
        return
    target_no = int(m.group(1))
    value = _fnum(m.group(2))
    targets = db.get_signal_targets(sid)
    current = {int(t["target_no"]): float(t["price"]) for t in targets}
    if target_no not in current:
        await clean_user_message(message)
        await screen(bot, message.from_user.id, message.chat.id,
                     tr(lang, f"TP{target_no} برای این سیگنال وجود ندارد.", f"TP{target_no} does not exist on this signal."),
                     kb(nav(lang, f"sigmanage:{sid}")))
        return
    old = current[target_no]
    await clean_user_message(message)
    label = f"TP{target_no}"
    text = tr(channel_lang, f"<b>هدف به‌روزرسانی شد</b>\n\n{label}: <code>{_format_price(value)}</code>\n\nهدف معامله به‌روزرسانی شد.", f"<b>TAKE PROFIT UPDATED</b>\n\n{label}: <code>{_format_price(value)}</code>\n\nTrade target updated.")
    fm, vm, errors = await _reply_signal_update(bot, row, text)
    if not fm and not vm:
        await state.clear()
        err = "\n".join(f"• {escape(e[:350])}" for e in errors) or "• Channel reply failed"
        await screen(bot, message.from_user.id, message.chat.id,
                     tr(lang, "❌ تغییر TP در کانال ارسال نشد و در دیتابیس اعمال نشد.", "❌ TP update was not posted, so the database was not changed.") + "\n\n" + err,
                     signal_manage_menu(sid, lang))
        return
    db.update_signal_tp(sid, target_no, value)
    db.add_signal_update(sid, "TP_UPDATE", f"{label} از {_format_price(old)} به {_format_price(value)} تغییر کرد.", f"{label} changed from {_format_price(old)} to {_format_price(value)}.", f"tp{target_no}={value}", message.from_user.id, fm, vm, None)
    db.add_audit(message.from_user.id, "signal_tp_update", sid, f"tp{target_no}={value}")
    await state.clear()
    msg = tr(lang, "✅ تارگت بروزرسانی شد.", "✅ Target updated.")
    if errors:
        msg += "\n\n⚠️ " + "\n".join(escape(e[:300]) for e in errors)
    await screen(bot, message.from_user.id, message.chat.id, msg, signal_manage_menu(sid, lang))


@router.message(Flow.signal_update_sl)
async def signal_sl_update_input(message: Message, bot: Bot, state: FSMContext):
    if not is_admin(message.from_user.id): return
    data = await state.get_data()
    sid = int(data["signal_target_id"])
    row = db.get_signal(sid)
    lang = get_lang(message.from_user.id)
    channel_lang = get_lang(int(row["created_by"])) if row else lang
    try:
        value = _fnum(message.text or "")
    except Exception:
        await clean_user_message(message)
        await screen(bot, message.from_user.id, message.chat.id,
                     tr(lang, "عدد معتبر برای SL وارد کنید.", "Enter a valid SL price."),
                     kb(nav(lang, f"sigmanage:{sid}")))
        return
    old = row["stop_loss"]
    await clean_user_message(message)
    text = tr(channel_lang, f"<b>حد ضرر به‌روزرسانی شد</b>\n\nحد ضرر: <code>{_format_price(value)}</code>\n\nمدیریت ریسک معامله به‌روزرسانی شد.", f"<b>STOP LOSS UPDATED</b>\n\nSL: <code>{_format_price(value)}</code>\n\nRisk management updated.")
    fm, vm, errors = await _reply_signal_update(bot, row, text)
    if not fm and not vm:
        await state.clear()
        err = "\n".join(f"• {escape(e[:350])}" for e in errors) or "• Channel reply failed"
        await screen(bot, message.from_user.id, message.chat.id,
                     tr(lang, "❌ تغییر SL در کانال ارسال نشد و در دیتابیس اعمال نشد.", "❌ SL update was not posted, so the database was not changed.") + "\n\n" + err,
                     signal_manage_menu(sid, lang))
        return
    db.update_signal_sl(sid, value)
    db.add_signal_update(sid, "SL_UPDATE", f"حد ضرر از {_format_price(old)} به {_format_price(value)} تغییر کرد.", f"Stop loss changed from {_format_price(old)} to {_format_price(value)}.", str(value), message.from_user.id, fm, vm, None)
    db.add_audit(message.from_user.id, "signal_sl_update", sid, str(value))
    await state.clear()
    msg = tr(lang, "✅ حد ضرر بروزرسانی شد.", "✅ Stop loss updated.")
    if errors:
        msg += "\n\n⚠️ " + "\n".join(escape(e[:300]) for e in errors)
    await screen(bot, message.from_user.id, message.chat.id, msg, signal_manage_menu(sid, lang))


def _result_metric(row, exit_price: float) -> tuple[float,str,str]:
    pip_size = settings.forex_pip_size(str(row["symbol"])) if str(row["market_type"]).upper() == "FOREX" else None
    return result_metric(str(row["market_type"]), str(row["symbol"]), str(row["direction"]), float(row["entry_price"]), exit_price, pip_size=pip_size)


async def _publish_result_to_channel(bot: Bot, target, row, parent_message_id: int, caption: str) -> int:
    """Publish a post-issue lifecycle update as TEXT ONLY, replying to the signal."""
    result_msg = await bot.send_message(
        target,
        caption,
        parse_mode=ParseMode.HTML,
        reply_parameters=ReplyParameters(message_id=int(parent_message_id)),
    )
    return result_msg.message_id


async def _publish_result_with_fallback(bot: Bot, target, row, last_message_id, original_message_id, caption: str, label: str) -> tuple[int | None, str | None]:
    """Reply with text only; never render/download/upload a lifecycle screenshot."""
    parents: list[int] = []
    for raw in (last_message_id, original_message_id):
        if raw is None:
            continue
        try:
            mid = int(raw)
        except (TypeError, ValueError):
            continue
        if mid not in parents:
            parents.append(mid)
    if not parents:
        return None, f"{label}: no published signal message is available for result reply"
    last_exc: Exception | None = None
    for parent_id in parents:
        try:
            mid = await _publish_result_to_channel(bot, target, row, parent_id, caption)
            return mid, None
        except Exception as exc:
            last_exc = exc
            log.warning("%s text result reply failed for %s using parent %s: %s", label, row["code"], parent_id, exc)
    return None, f"{label}: {last_exc}"


async def _publish_manual_close_result(bot: Bot, row, exit_price: float, value: float, label: str, actor_id: int) -> tuple[int | None, int | None, list[str]]:
    """Finalize an admin/manual signal close with a text-only reply chain."""
    channel_lang = get_lang(int(row["created_by"]))
    result_type = "WIN" if value > 0 else ("LOSS" if value < 0 else "BREAK EVEN")
    metric_value = "0 Pips" if str(row["market_type"]).upper() == "FOREX" and value == 0 else ("0%" if value == 0 else label)
    if channel_lang == "fa":
        dir_text = {"BUY":"خرید", "SELL":"فروش", "LONG":"لانگ", "SHORT":"شورت"}.get(str(row["direction"]).upper(), str(row["direction"]))
        result_text = {"WIN":"برد", "LOSS":"باخت", "BREAK EVEN":"سر به سر"}[result_type]
        caption = (
            f"<b>📌 نتیجه معامله — {escape(str(row['code']))}</b>\n"
            f"نماد: <b>{escape(str(row['symbol']))}</b>\n"
            f"جهت: <b>{escape(dir_text)}</b>\n\n"
            f"ورود: {_copy_price(row['entry_price'])}\n"
            f"خروج: {_copy_price(exit_price)}\n\n"
            f"نتیجه: <b>{result_text}</b>\n"
            f"سود/زیان: <b>{escape(metric_value)}</b>\n"
            f"نوع خروج: <b>بستن دستی</b>"
        )
    else:
        caption = (
            f"<b>📌 TRADE RESULT — {escape(str(row['code']))}</b>\n"
            f"Symbol: <b>{escape(str(row['symbol']))}</b>\n"
            f"Direction: <b>{escape(str(row['direction']))}</b>\n\n"
            f"Entry: {_copy_price(row['entry_price'])}\n"
            f"Exit: {_copy_price(exit_price)}\n\n"
            f"Result: <b>{escape(result_type)}</b>\n"
            f"P/L: <b>{escape(metric_value)}</b>\n"
            f"Exit type: <b>MANUAL CLOSE</b>"
        )
    free_mid = vip_mid = None
    errors: list[str] = []
    if row["destination"] in {"FREE", "BOTH"}:
        free_mid, err = await _publish_result_with_fallback(bot, settings.free_channel_target, row, row["free_last_message_id"], row["free_message_id"], caption, "FREE")
        if err: errors.append(err)
    if row["destination"] in {"VIP", "BOTH"}:
        vip_mid, err = await _publish_result_with_fallback(bot, settings.vip_channel_id, row, row["vip_last_message_id"], row["vip_message_id"], caption, "VIP")
        if err: errors.append(err)
    return free_mid, vip_mid, errors


@router.message(Flow.signal_close_exit)
async def signal_close_exit_input(message: Message, bot: Bot, state: FSMContext):
    if not is_admin(message.from_user.id): return
    data = await state.get_data()
    sid = int(data["signal_target_id"])
    row = db.get_signal(sid)
    lang = get_lang(message.from_user.id)
    if not row or str(row["status"]).upper() == "CLOSED":
        await state.clear(); await clean_user_message(message)
        await screen(bot, message.from_user.id, message.chat.id, tr(lang, "این سیگنال پیدا نشد یا قبلاً بسته شده است.", "This signal was not found or is already closed."), signal_center_menu(lang))
        return
    try:
        exit_price = _fnum(message.text or "")
    except Exception:
        await clean_user_message(message)
        await screen(bot, message.from_user.id, message.chat.id,
                     tr(lang, f"<b>بستن {escape(row['code'])}</b>\n\nقیمت خروج معتبر وارد کنید.\nمثال: <code>2345.50</code>", f"<b>Close {escape(row['code'])}</b>\n\nEnter a valid exit price.\nExample: <code>2345.50</code>"),
                     kb(nav(lang, f"sigmanage:{sid}")))
        return
    value, unit, label = _result_metric(row, exit_price)
    await clean_user_message(message)
    free_mid, vip_mid, errors = await _publish_manual_close_result(bot, row, exit_price, value, label, message.from_user.id)
    if not free_mid and not vip_mid:
        await state.clear()
        err_text = "\n".join(f"• {escape(e[:350])}" for e in errors) or "• Channel reply failed"
        await screen(bot, message.from_user.id, message.chat.id,
                     tr(lang, "❌ نتیجه در کانال ارسال نشد؛ سیگنال هنوز Active است و می‌توانید دوباره Close را بزنید.", "❌ The result was not posted; the signal remains active and you can retry Close.") + "\n\n" + err_text,
                     signal_manage_menu(sid, lang))
        return
    db.close_signal(sid, exit_price, value, unit, None)
    db.add_signal_update(sid, "CLOSE", f"سیگنال با نتیجه {label} بسته شد.", f"Signal closed with result {label}.", label, message.from_user.id, free_mid, vip_mid, "CLOSED")
    db.add_audit(message.from_user.id, "close_signal", sid, label)
    await state.clear()
    tail = ("\n\n⚠️ " + "\n".join(escape(e[:300]) for e in errors)) if errors else ""
    await screen(bot, message.from_user.id, message.chat.id,
                 tr(lang, f"✅ <b>{row['code']}</b> بسته شد.\nنتیجه: <b>{escape(label)}</b>", f"✅ <b>{row['code']}</b> closed.\nResult: <b>{escape(label)}</b>") + tail,
                 signal_center_menu(lang))


@router.callback_query(F.data == "signal_closed")
async def signal_closed(cb: CallbackQuery, bot: Bot):
    if not is_admin(cb.from_user.id): return
    rows=db.list_mt5_closed_signals(20); lang=get_lang(cb.from_user.id); await cb.answer(); lines=[]
    for r in rows:
        suffix=(f"{float(r['result_value']):+g} Pips" if r['result_unit']=='PIPS' else f"{float(r['result_value']):+g}%") if r['result_value'] is not None else "—"
        lines.append(f"{r['code']} | {r['symbol']} {r['direction']} | <b>{suffix}</b>")
    text=tr(lang,"<b>🏁 نتایج بسته‌شده</b>\n\n","<b>🏁 Closed Results</b>\n\n")+("\n".join(lines) if lines else "—")
    await screen(bot,cb.from_user.id,cb.message.chat.id,text,kb(nav(lang,"admin_signals")))


@router.callback_query(F.data == "signal_stats")
async def signal_stats(cb: CallbackQuery, bot: Bot):
    if not is_admin(cb.from_user.id): return
    s=db.mt5_signal_stats(); lang=get_lang(cb.from_user.id); await cb.answer()
    text=tr(lang,
        f"<b>📊 عملکرد سیگنال‌ها</b>\n\n🟢 فعال: <b>{s['active']}</b>\n🏁 بسته‌شده: <b>{s['total']}</b>\n✅ Win: <b>{s['wins']}</b>\n❌ Loss: <b>{s['losses']}</b>\n⚪ BE: <b>{s['be']}</b>\n🎯 Win Rate: <b>{s['win_rate']}%</b>\n\n🌐 Forex: <b>{s['forex_pips']:+g} Pips</b>\n🪙 Crypto: <b>{s['crypto_pct']:+g}%</b>",
        f"<b>📊 Signal Performance</b>\n\n🟢 Active: <b>{s['active']}</b>\n🏁 Closed: <b>{s['total']}</b>\n✅ Win: <b>{s['wins']}</b>\n❌ Loss: <b>{s['losses']}</b>\n⚪ BE: <b>{s['be']}</b>\n🎯 Win Rate: <b>{s['win_rate']}%</b>\n\n🌐 Forex: <b>{s['forex_pips']:+g} Pips</b>\n🪙 Crypto: <b>{s['crypto_pct']:+g}%</b>")
    await screen(bot,cb.from_user.id,cb.message.chat.id,text,kb(nav(lang,"admin_signals")))


# =========================
# Automatic Trading Reports v6.4
# =========================
_WEEKDAY_NAMES = {"MONDAY":0,"TUESDAY":1,"WEDNESDAY":2,"THURSDAY":3,"FRIDAY":4,"SATURDAY":5,"SUNDAY":6}


def _parse_hm(value: str, fallback: tuple[int,int]=(23,59)) -> tuple[int,int]:
    try:
        hh, mm = value.strip().split(":", 1)
        h, m = int(hh), int(mm)
        if 0 <= h <= 23 and 0 <= m <= 59:
            return h, m
    except Exception:
        pass
    log.warning("Invalid report time %r; fallback to %02d:%02d", value, fallback[0], fallback[1])
    return fallback


def _period_utc(start_local: datetime, end_local: datetime) -> tuple[str,str]:
    return start_local.astimezone(timezone.utc).isoformat(), end_local.astimezone(timezone.utc).isoformat()


def _day_bounds(day: date) -> tuple[datetime,datetime]:
    start = datetime(day.year, day.month, day.day, tzinfo=TZ)
    return start, start + timedelta(days=1)


def _week_bounds(end_day: date) -> tuple[datetime,datetime]:
    start_day = end_day - timedelta(days=6)
    start = datetime(start_day.year, start_day.month, start_day.day, tzinfo=TZ)
    end = datetime(end_day.year, end_day.month, end_day.day, tzinfo=TZ) + timedelta(days=1)
    return start, end


def _admin_report_text(kind: str, start_local: datetime, end_local: datetime, lang: str, *, partial: bool=False) -> str:
    start_iso, end_iso = _period_utc(start_local, end_local)
    st = db.trading_report_stats(start_iso, end_iso)
    if kind == "daily":
        fa_title, en_title = "<b>گزارش روزانه NEXUS</b>", "<b>NEXUS Daily Report</b>"
    else:
        fa_title, en_title = "<b>گزارش هفتگی NEXUS</b>", "<b>NEXUS Weekly Report</b>"
    end_day=(end_local-timedelta(seconds=1)).date()
    fa_period = start_local.date().strftime("%Y/%m/%d") if kind=="daily" else f"{start_local.date().strftime('%Y/%m/%d')} تا {end_day.strftime('%Y/%m/%d')}"
    en_period = start_local.date().isoformat() if kind=="daily" else f"{start_local.date().isoformat()} to {end_day.isoformat()}"
    if partial:
        fa_period += " — تا این لحظه"
        en_period += " — so far"
    fa=(
        f"{fa_title}\n{fa_period}\n\n"
        f"<b>عملکرد معاملات</b>\n"
        f"کل معاملات بسته‌شده: <b>{st['closed']}</b>\n"
        f"برد: <b>{st['wins']}</b>\n"
        f"باخت: <b>{st['losses']}</b>\n"
        f"سر به سر: <b>{st['be']}</b>\n"
        f"نرخ برد: <b>{st['win_rate']}%</b>\n"
        f"نتیجه فارکس: <b>{st['forex_pips']:+g} پیپ</b>\n"
        f"نتیجه کریپتو: <b>{st['crypto_pct']:+g}%</b>\n\n"
        f"<b>کسب‌وکار</b>\n"
        f"کاربران جدید: <b>{st['new_users']}</b>\n"
        f"اشتراک جدید/تمدید: <b>{st['vip_activations']}</b>\n"
        f"پرداخت تأییدشده: <b>{st['approved_payments']}</b>\n"
        f"فروش: <b>{st['revenue_usdt']:g} USDT</b>"
    )
    en=(
        f"{en_title}\n{en_period}\n\n"
        f"<b>Trading Performance</b>\n"
        f"Closed trades: <b>{st['closed']}</b>\n"
        f"Wins: <b>{st['wins']}</b>\n"
        f"Losses: <b>{st['losses']}</b>\n"
        f"Break even: <b>{st['be']}</b>\n"
        f"Win rate: <b>{st['win_rate']}%</b>\n"
        f"Forex result: <b>{st['forex_pips']:+g} pips</b>\n"
        f"Crypto result: <b>{st['crypto_pct']:+g}%</b>\n\n"
        f"<b>Business</b>\n"
        f"New users: <b>{st['new_users']}</b>\n"
        f"New/Renewed subscriptions: <b>{st['vip_activations']}</b>\n"
        f"Approved payments: <b>{st['approved_payments']}</b>\n"
        f"Revenue: <b>{st['revenue_usdt']:g} USDT</b>"
    )
    return tr(lang, fa, en)


def _channel_report_caption(kind: str, start_local: datetime, end_local: datetime, lang: str) -> str:
    start_iso, end_iso = _period_utc(start_local, end_local)
    cf=db.channel_market_performance_stats(start_iso,end_iso,"FREE","CRYPTO")
    cv=db.channel_market_performance_stats(start_iso,end_iso,"VIP","CRYPTO")
    ff=db.channel_market_performance_stats(start_iso,end_iso,"FREE","FOREX")
    fv=db.channel_market_performance_stats(start_iso,end_iso,"VIP","FOREX")
    end_day=(end_local-timedelta(seconds=1)).date()
    if kind == "daily":
        period_fa=start_local.date().strftime("%Y/%m/%d")
        period_en=start_local.date().isoformat()
        title_fa="<b>📊 گزارش روزانه NEXUS</b>"
        title_en="<b>📊 NEXUS Daily Report</b>"
    else:
        period_fa=f"{start_local.date().strftime('%Y/%m/%d')} تا {end_day.strftime('%Y/%m/%d')}"
        period_en=f"{start_local.date().isoformat()} to {end_day.isoformat()}"
        title_fa="<b>📊 گزارش هفتگی NEXUS</b>"
        title_en="<b>📊 NEXUS Weekly Report</b>"
    fa=(
        f"{title_fa}\n{period_fa}\n\n"
        f"<b>🪙 بازار کریپتو</b>\n"
        f"عمومی — معاملات: <b>{cf['total']}</b> | برد: <b>{cf['wins']}</b> | باخت: <b>{cf['losses']}</b> | Win Rate: <b>{cf['win_rate']}%</b> | نتیجه: <b>{cf['result_pct']:+g}%</b>\n"
        f"VIP — معاملات: <b>{cv['total']}</b> | برد: <b>{cv['wins']}</b> | باخت: <b>{cv['losses']}</b> | Win Rate: <b>{cv['win_rate']}%</b> | نتیجه: <b>{cv['result_pct']:+g}%</b>\n\n"
        f"<b>💱 بازار فارکس</b>\n"
        f"عمومی — معاملات: <b>{ff['total']}</b> | برد: <b>{ff['wins']}</b> | باخت: <b>{ff['losses']}</b> | Win Rate: <b>{ff['win_rate']}%</b> | نتیجه: <b>{ff['result_pips']:+g} پیپ</b>\n"
        f"VIP — معاملات: <b>{fv['total']}</b> | برد: <b>{fv['wins']}</b> | باخت: <b>{fv['losses']}</b> | Win Rate: <b>{fv['win_rate']}%</b> | نتیجه: <b>{fv['result_pips']:+g} پیپ</b>"
    )
    en=(
        f"{title_en}\n{period_en}\n\n"
        f"<b>🪙 Crypto Market</b>\n"
        f"Public — Trades: <b>{cf['total']}</b> | Wins: <b>{cf['wins']}</b> | Losses: <b>{cf['losses']}</b> | Win Rate: <b>{cf['win_rate']}%</b> | Result: <b>{cf['result_pct']:+g}%</b>\n"
        f"VIP — Trades: <b>{cv['total']}</b> | Wins: <b>{cv['wins']}</b> | Losses: <b>{cv['losses']}</b> | Win Rate: <b>{cv['win_rate']}%</b> | Result: <b>{cv['result_pct']:+g}%</b>\n\n"
        f"<b>💱 Forex Market</b>\n"
        f"Public — Trades: <b>{ff['total']}</b> | Wins: <b>{ff['wins']}</b> | Losses: <b>{ff['losses']}</b> | Win Rate: <b>{ff['win_rate']}%</b> | Result: <b>{ff['result_pips']:+g} pips</b>\n"
        f"VIP — Trades: <b>{fv['total']}</b> | Wins: <b>{fv['wins']}</b> | Losses: <b>{fv['losses']}</b> | Win Rate: <b>{fv['win_rate']}%</b> | Result: <b>{fv['result_pips']:+g} pips</b>"
    )
    return tr(lang,fa,en)


async def _send_channel_report(bot: Bot, kind: str, period_key: str, start_local: datetime, end_local: datetime) -> None:
    """Send scheduled daily/weekly channel reports as text-only Telegram messages."""
    if not settings.channel_reports_enabled:
        return
    lang=settings.channel_content_language
    start_iso,end_iso=_period_utc(start_local,end_local)
    text=await asyncio.to_thread(_channel_report_caption,kind,start_local,end_local,lang)
    for label,target in (("FREE",settings.free_channel_target),("VIP",settings.vip_channel_id)):
        report_type=f"{kind}_channel"
        recipient_key=str(target)
        if not db.claim_report_dispatch(report_type,period_key,recipient_key,start_iso,end_iso):
            continue
        try:
            await bot.send_message(target,text,parse_mode=ParseMode.HTML,protect_content=True)
            db.mark_report_sent(report_type,period_key,recipient_key,start_iso,end_iso)
        except Exception as exc:
            db.release_report_dispatch(report_type,period_key,recipient_key)
            log.warning("%s %s report failed: %s",label,kind,exc)


async def _send_scheduled_report(bot: Bot, kind: str, period_key: str, start_local: datetime, end_local: datetime) -> None:
    start_iso,end_iso=_period_utc(start_local,end_local)
    for admin_id in settings.report_recipients:
        if not db.claim_report_dispatch(kind,period_key,admin_id,start_iso,end_iso):
            continue
        try:
            lang=get_lang(admin_id)
            report_text = await asyncio.to_thread(_admin_report_text, kind, start_local, end_local, lang)
            await bot.send_message(admin_id, report_text, parse_mode=ParseMode.HTML)
            db.mark_report_sent(kind,period_key,admin_id,start_iso,end_iso)
            db.add_audit(0,f"automatic_{kind}_report",admin_id,period_key)
            await push_home_to_bottom(bot, admin_id)
        except Exception as exc:
            db.release_report_dispatch(kind,period_key,admin_id)
            log.warning("automatic %s report failed for %s: %s",kind,admin_id,exc)
    await _send_channel_report(bot, kind, period_key, start_local, end_local)


async def _send_autotrade_daily_reports(bot: Bot, period_key: str, start_local: datetime, end_local: datetime) -> None:
    start_iso,end_iso=_period_utc(start_local,end_local)
    seen:set[int]=set()
    for lic in db.list_active_licenses():
        try:
            uid=int(lic["telegram_id"])
            if uid in seen or not bool(lic["autotrade_access"]):
                continue
            seen.add(uid)
            if not db.claim_report_dispatch("autotrade_daily",period_key,uid,start_iso,end_iso):
                continue
            st=db.autotrade_user_daily_stats(uid,start_iso,end_iso)
            # Send a daily Auto Trade statement even on zero-trade days so the user can verify service status.
            lang=get_lang(uid)
            mt5=db.mt5_account(uid)
            text=tr(lang,
                f"<b>🤖 گزارش روزانه Auto Trade</b>\n\n📅 {start_local.date().isoformat()}\n🖥 MT5: <b>{'CONNECTED' if mt5 else 'NOT CONNECTED'}</b>\n\nسیگنال دریافت‌شده: <b>{st['total']}</b>\nاجراشده: <b>{st['executed']}</b>\nبسته‌شده: <b>{st['closed']}</b>\n✅ WIN: <b>{st['wins']}</b>\n❌ LOSS: <b>{st['losses']}</b>\n⚪ BREAK EVEN: <b>{st['be']}</b>\n\nبرای جزئیات وارد بخش Auto Trade ربات شوید.",
                f"<b>🤖 Daily Auto Trade Report</b>\n\n📅 {start_local.date().isoformat()}\n🖥 MT5: <b>{'CONNECTED' if mt5 else 'NOT CONNECTED'}</b>\n\nSignals received: <b>{st['total']}</b>\nExecuted: <b>{st['executed']}</b>\nClosed: <b>{st['closed']}</b>\n✅ WIN: <b>{st['wins']}</b>\n❌ LOSS: <b>{st['losses']}</b>\n⚪ BREAK EVEN: <b>{st['be']}</b>\n\nOpen Auto Trade in the bot for details.")
            await bot.send_message(uid,text,parse_mode=ParseMode.HTML)
            db.mark_report_sent("autotrade_daily",period_key,uid,start_iso,end_iso)
            await push_home_to_bottom(bot,uid)
            await asyncio.sleep(0.05)
        except Exception as exc:
            try: db.release_report_dispatch("autotrade_daily",period_key,uid)
            except Exception: pass
            log.warning("Auto Trade daily report failed for %s: %s",uid if 'uid' in locals() else None,exc)


def _daily_target(now_local: datetime) -> tuple[str,datetime,datetime]:
    h,m=_parse_hm(settings.daily_report_time)
    scheduled=datetime(now_local.year,now_local.month,now_local.day,h,m,tzinfo=TZ)
    target=now_local.date() if now_local>=scheduled else now_local.date()-timedelta(days=1)
    start,end=_day_bounds(target)
    return target.isoformat(),start,end


def _weekly_target(now_local: datetime) -> tuple[str,datetime,datetime]:
    wanted=_WEEKDAY_NAMES.get(settings.weekly_report_day,4)
    h,m=_parse_hm(settings.weekly_report_time)
    days_back=(now_local.weekday()-wanted)%7
    end_day=now_local.date()-timedelta(days=days_back)
    scheduled=datetime(end_day.year,end_day.month,end_day.day,h,m,tzinfo=TZ)
    if scheduled>now_local:
        end_day-=timedelta(days=7)
    start,end=_week_bounds(end_day)
    return end_day.isoformat(),start,end


@router.callback_query(F.data == "report_daily_now")
async def report_daily_now(cb: CallbackQuery, bot: Bot):
    if not is_admin(cb.from_user.id): return
    await cb.answer()
    now=datetime.now(TZ); start,_=_day_bounds(now.date())
    text=await asyncio.to_thread(_admin_report_text,"daily",start,now,get_lang(cb.from_user.id),partial=True)
    await bot.send_message(cb.message.chat.id, text, parse_mode=ParseMode.HTML)
    await push_home_to_bottom(bot, cb.from_user.id)


@router.callback_query(F.data == "report_weekly_now")
async def report_weekly_now(cb: CallbackQuery, bot: Bot):
    if not is_admin(cb.from_user.id): return
    await cb.answer()
    now=datetime.now(TZ); start=datetime((now.date()-timedelta(days=6)).year,(now.date()-timedelta(days=6)).month,(now.date()-timedelta(days=6)).day,tzinfo=TZ)
    text=await asyncio.to_thread(_admin_report_text,"weekly",start,now,get_lang(cb.from_user.id),partial=True)
    await bot.send_message(cb.message.chat.id, text, parse_mode=ParseMode.HTML)
    await push_home_to_bottom(bot, cb.from_user.id)


async def report_worker(bot: Bot):
    if not settings.reports_enabled:
        log.info("Automatic reports are disabled")
        return
    log.info("Automatic reports enabled: daily=%s weekly=%s %s recipients=%s",settings.daily_report_time,settings.weekly_report_day,settings.weekly_report_time,settings.report_recipients)
    daily_h,daily_m=_parse_hm(settings.daily_report_time)
    weekly_h,weekly_m=_parse_hm(settings.weekly_report_time)
    weekly_day=_WEEKDAY_NAMES.get(settings.weekly_report_day,4)

    # When catch-up is disabled, reports are emitted only inside a narrow scheduled window.
    # Atomic DB claims prevent duplicate sends even if two bot processes are accidentally started.
    while True:
        try:
            now=datetime.now(TZ)
            if now.hour==daily_h and now.minute==daily_m:
                dkey,dstart,dend=_daily_target(now)
                await _send_scheduled_report(bot,"daily",dkey,dstart,dend)
                await _send_autotrade_daily_reports(bot,dkey,dstart,dend)
            if now.weekday()==weekly_day and now.hour==weekly_h and now.minute==weekly_m:
                wkey,wstart,wend=_weekly_target(now)
                await _send_scheduled_report(bot,"weekly",wkey,wstart,wend)

            if settings.report_catchup_enabled:
                # Optional catch-up: only the most recently due period is attempted. Idempotent claims make it safe.
                if not (now.hour==daily_h and now.minute==daily_m):
                    dkey,dstart,dend=_daily_target(now)
                    await _send_scheduled_report(bot,"daily",dkey,dstart,dend)
                    await _send_autotrade_daily_reports(bot,dkey,dstart,dend)
                if not (now.weekday()==weekly_day and now.hour==weekly_h and now.minute==weekly_m):
                    wkey,wstart,wend=_weekly_target(now)
                    await _send_scheduled_report(bot,"weekly",wkey,wstart,wend)
        except Exception:
            log.exception("report worker error")
        await asyncio.sleep(20)


async def _delete_transient_notification(bot: Bot, chat_id: int, message_id: int, delay: int):
    try:
        await asyncio.sleep(max(3,int(delay)))
        await bot.delete_message(chat_id,message_id)
    except Exception:
        pass



async def _read_mt5_chart_bytes(chart_path: str) -> tuple[bytes, str]:
    """Read an MT5 chart image robustly across project/version moves.

    New MT5 events are written by the API into this project's assets folder.
    Older queued events may still contain an absolute path from a previous
    NEXUS installation; in that case we also try the basename in the current
    mt5_events directory.
    """
    raw_path = str(chart_path or "").strip()
    if not raw_path:
        return b"", ""
    candidates = []
    if raw_path:
        candidates.append(Path(raw_path))
    current_dir = Path(__file__).resolve().parent / "assets" / "autotrade" / "mt5_events"
    try:
        name = Path(raw_path).name
        if name:
            candidates.append(current_dir / name)
    except Exception:
        pass
    seen = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        try:
            if candidate.is_file():
                return await asyncio.to_thread(candidate.read_bytes), key
        except Exception:
            log.exception("MT5 chart read failed: %s", candidate)
    return b"", raw_path


async def _process_mt5_trade_event(bot: Bot, n, payload: dict) -> None:
    """Bridge MT5 trade events into the signal/channel lifecycle.

    The backend owns the screenshot storage path. MT5 sends image bytes as
    base64; queued events may outlive a previous project directory, so stale
    absolute chart paths must never break the notification worker.
    """
    uid = int(n["telegram_id"])
    event = str(payload.get("event") or "").upper()
    ticket = str(payload.get("ticket") or "").strip()
    signal_id = str(payload.get("signal_id") or "").strip()

    # Resolve the lifecycle row before touching a screenshot. This is critical
    # for old queued CLOSE/UPDATE events from a previous installation: they are
    # harmless and must be consumed instead of producing an error loop.
    row = None
    if event in {"UPDATE", "CLOSE", "CANCEL", "EXPIRE"}:
        if signal_id:
            row = db.get_signal_by_autotrade_signal_id(uid, signal_id)
        if not row and ticket:
            row = db.get_signal_by_autotrade_ticket(uid, ticket)
        if not row:
            row = db.get_signal_by_publish_token(signal_id or f"MT5MANUAL-{ticket}")
        if not row:
            log.warning("Ignoring stale/unmatched MT5 %s event: ticket=%s signal_id=%s", event, ticket, signal_id)
            return

    # Lifecycle events never carry or consume screenshots. The only chart image in the
    # channel lifecycle is the original signal publication handled by _publish_signal().
    # Ignoring chart_path here also prevents accidental file reads/retries after CLOSE.

    if event == "PENDING":
        symbol = str(payload.get("symbol") or "").upper()
        direction = str(payload.get("direction") or "").upper()
        entry = float(payload.get("entry_price") or 0)
        sl = float(payload.get("stop_loss") or 0)
        tp = float(payload.get("take_profit") or 0)
        volume = float(payload.get("volume") or 0)
        if not symbol or direction not in {"LONG", "SHORT"} or entry <= 0 or volume <= 0:
            raise ValueError("invalid MT5 pending-order event")
        # PENDING is a lifecycle event, not a new signal publication. It is text/state only;
        # the original signal publication is the sole owner of the chart screenshot.
        if sl <= 0:
            raise ValueError("pending order requires a stop-loss")
        if direction == "LONG" and not sl < entry:
            raise ValueError("LONG pending order has invalid stop-loss")
        if direction == "SHORT" and not sl > entry:
            raise ValueError("SHORT pending order has invalid stop-loss")
        if tp > 0 and ((direction == "LONG" and tp <= entry) or (direction == "SHORT" and tp >= entry)):
            raise ValueError("pending order has invalid take-profit")

        upper = symbol.upper()
        market_type = "CRYPTO" if any(k in upper for k in ("BTC","ETH","SOL","BNB","XRP","DOGE","ADA","AVAX","DOT","LTC")) else ("GOLD" if "XAU" in upper else "FOREX")
        publish_token = signal_id or f"MT5MANUAL-PENDING-{ticket}"
        row = db.get_signal_by_code(signal_id) if signal_id else db.get_signal_by_publish_token(publish_token)
        if not row:
            upper = symbol.upper()
            market_type = "CRYPTO" if any(k in upper for k in ("BTC","ETH","SOL","BNB","XRP","DOGE","ADA","AVAX","DOT","LTC")) else ("GOLD" if "XAU" in upper else "FOREX")
            fallback_tp = tp if tp > 0 else (entry + abs(entry-sl) if direction == "LONG" else entry - abs(entry-sl))
            row = db.issue_mt5_admin_signal(
                market_type=market_type, symbol=symbol, direction=direction, entry_price=entry, stop_loss=sl,
                targets=[fallback_tp], risk_percent=0.0, rr_ratio=None,
                order_type=str(payload.get("order_type") or ("BUY_LIMIT" if direction=="LONG" else "SELL_LIMIT")).upper(),
                volume_mode="FIXED", lot_size=volume, trailing_name="Manual MT5 Pending",
                admin_account=str(payload.get("account_number") or ""), admin_id=uid,
                request_id=str(payload.get("event_id") or f"PENDING:{ticket}"), signal_code=publish_token,
                stop_limit_price=float(payload.get("stop_limit_price") or 0) or None, timeframe="M5",
            )
        # Legacy caption contracts retained only as source markers; v0.6 does not
        # send them to Telegram. _signal_caption(row, get_lang(uid), status="PENDING")
        # _signal_caption(row, get_lang(uid), status="ACTIVE")
        # v0.6.0: MT5 Admin is the sole signal authority. No Telegram channel
        # publication or reply-chain is created. The signal is delivered only
        # through the AutoTrade API to licensed MT5 clients.
        code = str(row["code"])
        destination = str(row["destination"] or "BOTH").upper()
        db.add_signal_event(int(row["id"]), "PENDING", actor_type="MT5_ADMIN", actor_id=uid,
                            account_number=str(payload.get("account_number") or ""), correlation_id=code,
                            payload={"ticket": ticket, "order_type": str(row["order_type"]), "entry": entry, "sl": sl, "tp": tp})
        db.update_trade_execution(uid, ticket, str(payload.get("event_id") or f"PENDING:{ticket}"),
                                   signal_id=int(row["id"]), status="PENDING", destination=destination)
        db.add_audit(uid, "mt5_manual_pending", int(row["id"]),
                     f"{symbol} {direction} limit={entry:g} ticket={ticket} destination={destination}")
        return

    if event == "OPEN":
        symbol = str(payload.get("symbol") or "").upper()
        direction = str(payload.get("direction") or "").upper()
        entry = float(payload.get("entry_price") or 0)
        sl = float(payload.get("stop_loss") or 0)
        tp = float(payload.get("take_profit") or 0)
        volume = float(payload.get("volume") or 0)
        if not symbol or direction not in {"LONG","SHORT"} or entry <= 0 or volume <= 0:
            raise ValueError("invalid MT5 manual-open event")

        # Screenshot is optional. If MT5 cannot provide a chart image, the
        # lifecycle event must still be acknowledged and published. Existing
        # LIMIT activations use the original signal's reply chain and do not
        # require an image at all.

        # A manual LIMIT activation carries the existing NEXUS signal id. Reuse
        # that lifecycle row instead of creating a second signal.
        existing = db.get_signal_by_code(signal_id) if signal_id else None
        if existing and str(existing["order_type"] or "MARKET").upper() != "MARKET":
            event_id = str(payload.get("event_id") or f"OPEN:{ticket}")
            destination = str(existing["destination"] or "BOTH")
            # Idempotent activation: a manual admin announcement and the later
            # broker-confirmed OPEN event must never create two channel posts.
            if existing["limit_activated_at"]:
                db.set_signal_status(int(existing["id"]), "ACTIVE")
                db.update_trade_execution(uid, ticket, event_id, signal_id=int(existing["id"]), status="ACTIVATED", destination=destination)
                return

            requested_entry = float(existing["entry_price"] or 0)
            slippage = entry - requested_entry if requested_entry > 0 else 0.0
            text = (
                f"🟢 <b>TRADE ACTIVATED</b>\n\n"
                f"<b>{escape(str(existing['code']))}</b> — {escape(str(existing['symbol']))} {escape(str(existing['direction']))}\n"
                f"Requested Entry: <code>{requested_entry:g}</code>\n"
                f"Executed Entry: <code>{entry:g}</code>\n"
                f"Slippage: <code>{slippage:+g}</code>\n"
                f"Volume: <code>{volume:g}</code>\n"
                f"Ticket: <code>{escape(ticket)}</code>"
            )
            db.mark_limit_activated(int(existing["id"]))
            db.add_signal_event(int(existing["id"]), "ACTIVATE", actor_type="MT5", actor_id=uid,
                                account_number=str(payload.get("account_number") or ""), correlation_id=str(existing["code"]),
                                payload={"ticket": ticket, "requested_entry": requested_entry, "executed_entry": entry, "slippage": slippage})
            db.mark_signal_opened(int(existing["id"]), _mt5_event_datetime(payload).isoformat())
            db.update_trade_execution(uid, ticket, event_id, signal_id=int(existing["id"]), status="ACTIVATED", destination=destination)
            db.add_signal_update(int(existing["id"]), "MT5_LIMIT_ACTIVATED", text, text, "", uid, None, None, "ACTIVE")
            return

        upper = symbol.upper()
        market_type = "CRYPTO" if any(k in upper for k in ("BTC","ETH","SOL","BNB","XRP","DOGE","ADA","AVAX","DOT","LTC")) else "FOREX"
        targets = [tp if tp > 0 else entry]
        publish_token = signal_id or f"MT5MANUAL-{ticket}"
        row = db.issue_mt5_admin_signal(
            market_type=market_type, symbol=symbol, direction=direction, entry_price=entry,
            stop_loss=sl, targets=targets, risk_percent=0.0, rr_ratio=None, order_type="MARKET",
            volume_mode="FIXED", lot_size=volume, trailing_name="Manual MT5",
            admin_account=str(payload.get("account_number") or ""), admin_id=uid,
            request_id=str(payload.get("event_id") or f"OPEN:{ticket}"), signal_code=publish_token,
        )
        # v0.6.0 idempotency: the canonical issuer identity, not Telegram
        # message IDs, determines whether this OPEN has already been issued.
        if "issuer_type" in row.keys() and str(row["issuer_type"]).upper() == "MT5_ADMIN" and str(row["issuer_account"] or "") == str(payload.get("account_number") or "") and str(row["publish_token"] or "") == publish_token:
            prior = db.has_trade_execution(uid, ticket, str(payload.get("event_id") or f"OPEN:{ticket}"))
            if prior:
                log.warning("[NEXUS][IDEMPOTENCY] duplicate MT5 OPEN ignored: ticket=%s signal=%s", ticket, row["code"])
                return
        code = str(row["code"])
        destination = str(row["destination"] or "BOTH").upper()
        # v0.6.0: do not publish signals or lifecycle updates to Telegram.
        db.add_signal_event(int(row["id"]), "OPEN", actor_type="MT5_ADMIN", actor_id=uid,
                            account_number=str(payload.get("account_number") or ""), correlation_id=code,
                            payload={"ticket": ticket, "entry": entry, "sl": sl, "tp": tp, "volume": volume})
        db.record_signal_delivery(int(row["id"]), str(payload.get("account_number") or ""), status="ISSUED") if str(payload.get("account_number") or "") else None
        db.update_trade_execution(uid, ticket, str(payload.get("event_id") or f"OPEN:{ticket}"), signal_id=int(row["id"]), status="OPEN", destination=destination)
        return

    if event in {"CANCEL", "EXPIRE"}:
        if not row:
            log.warning("Ignoring stale/unmatched MT5 %s event: ticket=%s signal_id=%s", event, ticket, signal_id)
            return
        status = "CANCELLED" if event == "CANCEL" else "EXPIRED"
        if str(row["status"]).upper() in {"CANCELLED","EXPIRED","CLOSED"}:
            db.update_trade_execution(uid, ticket, str(payload.get("event_id") or f"{event}:{ticket}"),
                                       signal_id=int(row["id"]), status=status, destination=str(row["destination"]))
            return
        label = {"BUY_LIMIT":"BUY LIMIT","SELL_LIMIT":"SELL LIMIT","BUY_STOP":"BUY STOP","SELL_STOP":"SELL STOP",
                 "BUY_STOP_LIMIT":"BUY STOP LIMIT","SELL_STOP_LIMIT":"SELL STOP LIMIT"}.get(
            str(row["order_type"] or "").upper(), str(row["order_type"] or "PENDING").upper())
        text = (
            f"ORDER {status} | {row['code']} | {row['symbol']} | {label} | entry={float(row['entry_price']):g}"
        )
        db.set_signal_status(int(row["id"]), status)
        db.add_signal_event(int(row["id"]), event, actor_type="MT5", actor_id=uid,
                            account_number=str(payload.get("account_number") or ""), correlation_id=str(row["code"]),
                            payload={"ticket": ticket, "order_type": label})
        db.add_signal_update(int(row["id"]), f"MT5_{event}", text, text, "", uid, None, None, status)
        db.update_trade_execution(uid, ticket, str(payload.get("event_id") or f"{event}:{ticket}"),
                                   signal_id=int(row["id"]), status=status, destination=str(row["destination"]))
        db.add_audit(uid, f"mt5_{event.lower()}", int(row["id"]), f"ticket={ticket}")
        return

    if event == "UPDATE":
        sl = float(payload.get("stop_loss") or 0)
        tp = float(payload.get("take_profit") or 0)
        old_sl = float(row["stop_loss"] or 0)
        old_tp = float((db.get_signal_targets(int(row["id"]))[0]["price"] if db.get_signal_targets(int(row["id"])) else 0) or 0)
        sl_changed = sl > 0 and abs(sl - old_sl) > 1e-12
        tp_changed = tp > 0 and abs(tp - old_tp) > 1e-12
        if sl_changed:
            try: db.update_signal_sl(int(row["id"]), sl)
            except Exception: log.exception("[NEXUS][DB] MT5 SL sync failed for %s", row["code"])
        if tp_changed:
            try: db.update_signal_tp(int(row["id"]), 1, tp)
            except Exception: log.exception("[NEXUS][DB] MT5 TP sync failed for %s", row["code"])
        if not sl_changed and not tp_changed:
            db.update_trade_execution(uid, ticket, str(payload.get("event_id") or f"UPDATE:{ticket}"), signal_id=int(row["id"]), status="IGNORED")
            return
        parts_fa=[]; parts_en=[]
        if sl_changed:
            label = "🟡 <b>BE ACTIVATED:</b>" if abs(sl - float(row["entry_price"])) <= max(1e-8, abs(float(row["entry_price"]))*1e-7) else "🛑 <b>SL CHANGED:</b>"
            parts_fa.append(f"{label}\nقدیم: {_copy_price(old_sl)}\nجدید: {_copy_price(sl)}")
            parts_en.append(("🟡 <b>BE ACTIVATED:</b>" if abs(sl - float(row["entry_price"])) <= max(1e-8, abs(float(row["entry_price"]))*1e-7) else "🛑 <b>SL CHANGED:</b>") + f"\nOld: {_copy_price(old_sl)}\nNew: {_copy_price(sl)}")
        if tp_changed:
            parts_fa.append(f"🎯 <b>TP CHANGED:</b>\nقدیم: {_copy_price(old_tp)}\nجدید: {_copy_price(tp)}")
            parts_en.append(f"🎯 <b>TP CHANGED:</b>\nOld: {_copy_price(old_tp)}\nNew: {_copy_price(tp)}")
        if not parts_fa: return
        text=tr(get_lang(uid),
                f"<b>{escape(str(row['code']))}</b>\n" + "\n\n".join(parts_fa),
                f"<b>{escape(str(row['code']))}</b>\n" + "\n\n".join(parts_en))
        db.add_signal_event(int(row["id"]), "UPDATE", actor_type="MT5", actor_id=uid,
                            account_number=str(payload.get("account_number") or ""), correlation_id=str(row["code"]),
                            payload={"sl_changed": sl_changed, "tp_changed": tp_changed, "sl": sl, "tp": tp})
        db.add_signal_update(int(row["id"]),"MT5_UPDATE",text,text,"",uid,None,None,"ACTIVE")
        db.update_trade_execution(uid, ticket, str(payload.get("event_id") or f"UPDATE:{ticket}"), signal_id=int(row["id"]), status="UPDATED", destination=str(row["destination"]))
        db.add_audit(uid,"mt5_trade_update",int(row["id"]),f"ticket={ticket} sl={sl:g} tp={tp:g}")
        return

    if event == "CLOSE":
        if str(row["status"]).upper() == "CLOSED":
            return
        # Screenshot is optional for CLOSE. The final lifecycle result is
        # delivered as a reply even when MT5 chart capture is unavailable.
        exit_price = float(payload.get("exit_price") or 0)
        profit = float(payload.get("profit") or 0)
        if exit_price <= 0:
            raise ValueError("invalid MT5 close exit price")

        close_dt = _mt5_event_datetime(payload)
        opened_raw = row["opened_at"] if "opened_at" in row.keys() else None
        if not opened_raw:
            opened_raw = row["limit_activated_at"] if "limit_activated_at" in row.keys() else None
        if not opened_raw:
            opened_raw = row["created_at"]
        try:
            opened_dt = datetime.fromisoformat(str(opened_raw))
            if opened_dt.tzinfo is None:
                opened_dt = opened_dt.replace(tzinfo=timezone.utc)
            holding_seconds = max(0, int((close_dt - opened_dt).total_seconds()))
        except (TypeError, ValueError, OverflowError):
            holding_seconds = None

        market_type = str(row["market_type"] or "").upper()
        try:
            result_pips, result_unit, _ = result_metric(
                market_type, str(row["symbol"]), str(row["direction"]),
                float(row["entry_price"]), exit_price
            )
        except Exception:
            result_pips, result_unit = 0.0, "PERCENT"

        reason = str(payload.get("close_reason") or "OTHER").upper()
        reason_labels = {
            "TAKE_PROFIT": "TAKE PROFIT", "STOP_LOSS": "STOP LOSS",
            "STOP_OUT": "STOP OUT", "MANUAL": "MANUAL CLOSE",
            "MOBILE": "MOBILE CLOSE", "WEB": "WEB CLOSE",
            "EXPERT": "EXPERT CLOSE", "ROLLOVER": "ROLLOVER", "OTHER": "OTHER",
        }
        duration_text = "—"
        if holding_seconds is not None:
            h, rem = divmod(holding_seconds, 3600)
            m, sec = divmod(rem, 60)
            duration_text = f"{h:02d}:{m:02d}:{sec:02d}"

        result_type = "WIN" if profit > 0 else ("LOSS" if profit < 0 else "BREAK EVEN")
        pips_text = f"{result_pips:+g} {result_unit}"
        reply = (
            f"TRADE CLOSED | {row['code']} | {row['symbol']} | direction={row['direction']} | "
            f"exit={exit_price:g} | pnl={profit:+.2f} | result={result_type} | performance={pips_text} | "
            f"duration={duration_text} | reason={reason_labels.get(reason, reason)} | ticket={ticket}"
        )

        # Event-driven MT5 CLOSE must use the same Telegram Reply Chain as
        # manually closed signals. Previously this branch only persisted
        # signal_updates, so no channel message was sent. Publish before
        # marking CLOSED; at least one successful channel is required.
        # Post-signal lifecycle updates are text-only. Never render/capture/upload a chart.
        free_mid = vip_mid = None
        reply_errors: list[str] = []
        # CLOSE can race the background publication queued after the accepted
        # MT5 receipt. If no Telegram anchor exists yet, publish the signal
        # fallback synchronously before attempting the result reply.
        if not row["free_message_id"] and not row["vip_message_id"]:
            try:
                from .autotrade.api import _publish_mt5_admin_signal_async
                await _publish_mt5_admin_signal_async(row, None)
                refreshed = db.get_signal(int(row["id"]))
                if refreshed is not None:
                    row = refreshed
            except Exception as exc:
                reply_errors.append(f"SIGNAL_ANCHOR: {exc}")
        if row["destination"] in {"FREE", "BOTH"}:
            free_mid, err = await _publish_result_with_fallback(
                bot, settings.free_channel_target, row,
                row["free_last_message_id"], row["free_message_id"],
                reply, "FREE",
            )
            if err: reply_errors.append(err)
        if row["destination"] in {"VIP", "BOTH"}:
            vip_mid, err = await _publish_result_with_fallback(
                bot, settings.vip_channel_id, row,
                row["vip_last_message_id"], row["vip_message_id"],
                reply, "VIP",
            )
            if err: reply_errors.append(err)
        if not free_mid and not vip_mid:
            raise RuntimeError("MT5 CLOSE Telegram reply failed: " + " | ".join(reply_errors or ["no channel delivery"]))

        db.close_signal(
            int(row["id"]), exit_price,
            result_pips, result_unit, None, close_dt.isoformat(),
            close_reason=reason, holding_seconds=holding_seconds,
            result_pips=result_pips,
        )
        db.add_signal_event(int(row["id"]), "CLOSE", actor_type="MT5", actor_id=uid,
                            account_number=str(payload.get("account_number") or ""), correlation_id=str(row["code"]),
                            payload={"ticket": ticket, "exit_price": exit_price, "profit": profit, "close_reason": reason, "holding_seconds": holding_seconds})
        db.add_signal_update(
            int(row["id"]), "MT5_CLOSE", reply, reply, str(profit), uid,
            free_mid, vip_mid, "CLOSED"
        )
        event_id = str(payload.get("event_id") or f"CLOSE:{ticket}")
        db.update_trade_execution(
            uid, ticket, event_id, signal_id=int(row["id"]),
            status="CLOSED", destination=str(row["destination"])
        )
        db.add_audit(
            uid, "mt5_trade_close", int(row["id"]),
            f"ticket={ticket} result={profit:+g} USD reason={reason} duration={holding_seconds}"
        )
        return

    raise ValueError(f"unsupported MT5 event: {event}")

async def mt5_publication_retry_worker(bot: Bot):
    """Durably retry Telegram publication for broker-accepted MT5 signals.

    Receipt success and Telegram delivery are separate durable states. A transient
    Telegram/API failure must not require a new MT5 receipt to trigger publication.
    """
    while True:
        try:
            for row in db.list_mt5_publication_retries(50):
                try:
                    result = await _publish_mt5_admin_signal_async(row, None)
                    if result.get("errors"):
                        log.warning("[NEXUS][MT5_PUBLISH] retry incomplete for %s: %s", row["code"], result["errors"])
                except Exception as exc:
                    log.exception("[NEXUS][MT5_PUBLISH] retry failed for %s: %s", row["code"], exc)
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("[NEXUS][MT5_PUBLISH] worker loop failure")
        await asyncio.sleep(5)


async def autotrade_notification_worker(bot: Bot):
    """Send a short transient notification only; detailed state lives in Auto Trade menus."""
    while True:
        try:
            for n in db.pending_autotrade_notifications(100):
                if not db.claim_autotrade_notification(int(n["id"])):
                    continue
                uid=int(n["telegram_id"]); lang=get_lang(uid); sig=db.get_signal(int(n["signal_id"])) if n["signal_id"] else None
                code=str(sig["code"]) if sig else "—"; symbol=str(sig["symbol"]) if sig else "—"
                payload={}
                if n["payload_json"]:
                    try: payload=json.loads(str(n["payload_json"]))
                    except Exception: payload={}

                if str(n["event_type"])=="MT5_TRADE_EVENT":
                    try:
                        await _process_mt5_trade_event(bot, n, payload)
                        db.mark_autotrade_notification_sent(int(n["id"]))
                    except Exception as exc:
                        log.exception("[NEXUS][MT5_EVENT] trade event failed: %s", exc)
                        try:
                            ev_id=str(payload.get("event_id") or "")
                            ticket_id=str(payload.get("ticket") or "")
                            if ev_id and ticket_id:
                                db.update_trade_execution(
                                    int(n["telegram_id"]), ticket_id, ev_id,
                                    status="FAILED", error_text=str(exc),
                                    destination=str(payload.get("destination") or "BOTH"),
                                )
                        except Exception:
                            log.exception("[NEXUS][DB] failed to mark MT5 event as FAILED")
                        db.release_autotrade_notification_claim(int(n["id"]))
                    await asyncio.sleep(0.04)
                    continue

                # Command receipts are tracked in the Auto Trade status/history screens and do not create chat noise.
                if str(n["event_type"])!="SIGNAL_RECEIPT":
                    db.mark_autotrade_notification_sent(int(n["id"])); continue

                status=str(payload.get("status") or "").lower()
                if status=="executed":
                    text=tr(lang,f"✅ Auto Trade: معامله {escape(symbol)} اجرا شد — جزئیات در «وضعیت Auto Trade».",f"✅ Auto Trade: {escape(symbol)} trade executed — details are in Auto Trade Status.")
                elif status=="pending":
                    text=tr(lang,f"⏳ Auto Trade: سفارش Limit {escape(symbol)} ثبت شد — وضعیت را از منوی Auto Trade دنبال کنید.",f"⏳ Auto Trade: {escape(symbol)} Limit order placed — follow it in Auto Trade Status.")
                elif status=="activated":
                    text=tr(lang,f"🔔 Auto Trade: سفارش Limit {escape(symbol)} فعال شد — جزئیات در Auto Trade.",f"🔔 Auto Trade: {escape(symbol)} Limit order activated — details are in Auto Trade.")
                elif status in {"rejected","failed","failed_retryable"}:
                    text=tr(lang,f"⚠️ Auto Trade: سیگنال {escape(code)} اجرا نشد — علت در تاریخچه Auto Trade ثبت شد.",f"⚠️ Auto Trade: signal {escape(code)} was not executed — reason is stored in Auto Trade history.")
                else:
                    db.mark_autotrade_notification_sent(int(n["id"])); continue

                try:
                    msg=await bot.send_message(uid,text)
                    db.mark_autotrade_notification_sent(int(n["id"]))
                    task=asyncio.create_task(_delete_transient_notification(bot,uid,msg.message_id,settings.autotrade_notification_ttl_seconds))
                    BACKGROUND_TASKS.add(task); task.add_done_callback(BACKGROUND_TASKS.discard)
                except Exception as exc:
                    db.release_autotrade_notification_claim(int(n["id"]))
                    log.warning("Auto Trade notification failed for %s: %s",uid,exc)
                await asyncio.sleep(0.04)
        except Exception:
            log.exception("Auto Trade notification worker error")
        await asyncio.sleep(5)


async def backup_worker():
    while True:
        try: await asyncio.to_thread(create_db_backup)
        except Exception: log.exception("automatic backup failed")
        await asyncio.sleep(86400)


async def expiry_worker(bot: Bot):
    while True:
        try:
            now=datetime.now(timezone.utc)
            db.expire_old_invoices()
            for lic in db.list_active_licenses():
                vip_expired,auto_expired=db.deactivate_expired_entitlements(int(lic["id"]))
                uid=int(lic["telegram_id"])
                if vip_expired:
                    await revoke_user_invites(bot,uid)
                    try:
                        await bot.ban_chat_member(settings.vip_channel_id,uid)
                    except Exception as exc:
                        log.warning("VIP entitlement removal failed for %s: %s",uid,exc)
                    try:
                        lang=get_lang(uid); await bot.send_message(uid,tr(lang,"⛔ اعتبار وی‌آی‌پی شما به پایان رسید. معاملات خودکار در صورت داشتن اعتبار مستقل همچنان می‌تواند فعال بماند.","⛔ Your VIP entitlement has expired. Auto Trade may remain active if it has separate validity.")); await push_home_to_bottom(bot,uid)
                    except Exception: pass
                if auto_expired:
                    try:
                        lang=get_lang(uid); await bot.send_message(uid,tr(lang,"⛔ اعتبار معاملات خودکار شما به پایان رسید. معامله جدید باز نمی‌شود و EA وارد SAFE MODE می‌شود تا معاملات باز مدیریت شوند.","⛔ Your Auto Trade entitlement has expired. No new trades will open; the EA enters SAFE MODE to manage existing positions.")); await push_home_to_bottom(bot,uid)
                    except Exception: pass
                # Reminder uses whichever active entitlement expires next.
                expiries=[]
                for key in ("vip_expires_at","autotrade_expires_at"):
                    raw=lic[key] if key in lic.keys() else None
                    if raw:
                        try:
                            dt=datetime.fromisoformat(str(raw))
                            if dt>now: expiries.append(dt)
                        except Exception: pass
                if not expiries: continue
                exp=min(expiries); seconds=(exp-now).total_seconds()
                for days in settings.reminder_days:
                    if 0<seconds<=days*86400 and not db.reminder_sent(lic["id"],days):
                        try:
                            lang=get_lang(uid); text=tr(lang,f"⏳ یادآوری NEXUS: حدود <b>{days} روز</b> تا پایان نزدیک‌ترین سرویس فعال شما باقی مانده است. برای مشاهده جزئیات وارد حساب شوید.",f"⏳ NEXUS reminder: about <b>{days} days</b> remain on your next expiring service. Open your account for details.")
                            await bot.send_message(uid,text,parse_mode=ParseMode.HTML); db.mark_reminder_sent(lic["id"],days); await push_home_to_bottom(bot,uid)
                        except Exception as exc: log.warning("reminder failed: %s",exc)
            for lic in db.list_expired_active():
                user_id=lic["telegram_id"]; await revoke_user_invites(bot,user_id)
                try: await bot.ban_chat_member(settings.vip_channel_id,user_id)
                except Exception as exc: log.warning("VIP removal failed for %s: %s",user_id,exc)
                db.expire_license(lic["id"])
                try:
                    lang=get_lang(user_id); await bot.send_message(user_id,tr(lang,"⛔ اشتراک وی‌آی‌پی شما به پایان رسید و دسترسی کانال غیرفعال شد. برای تمدید وارد ربات شوید.","⛔ Your VIP subscription has expired and channel access has been disabled. Open the bot to renew.")); await push_home_to_bottom(bot, int(user_id))
                except Exception: pass
        except Exception:
            log.exception("expiry worker error")
        await asyncio.sleep(3600)


@router.message()
async def clean_unhandled_message(message: Message, bot: Bot):
    """Keep private bot chats clean: remove unsupported user messages and restore the dashboard last."""
    if message.chat.type != "private" or not message.from_user:
        return
    await clean_user_message(message)
    if db.get_user(message.from_user.id):
        try:
            await push_home_to_bottom(bot, message.from_user.id)
        except Exception:
            pass


def _disable_telegram_signal_authority() -> None:
    """v0.6 policy: Telegram is reporting/subscription only; no signal CRUD.

    We deliberately leave the legacy handlers in source for migration/audit
    traceability, but they are not registered with the Dispatcher. This makes
    the cutover reversible while enforcing the new authority at runtime.
    """
    blocked_callback = {
        name for name in (
            "signal_create", "signal_market", "signal_chart",
            "signal_chart_invalid", "signal_symbol_pick", "signal_symbol",
            "signal_direction", "signal_timeframe_pick", "signal_order_type_pick",
            "signal_entry", "signal_stop_limit", "signal_sl", "signal_tp_count",
            "signal_tp_value", "signal_volume_mode_pick", "signal_position_input",
            "signal_risk", "signal_trailing_pick", "signal_destination",
            "signal_publish", "signal_retry_publish",
            "signal_action",
        )
    }
    router.callback_query.handlers[:] = [h for h in router.callback_query.handlers if getattr(h.callback, "__name__", "") not in blocked_callback]
    router.message.handlers[:] = [h for h in router.message.handlers if not getattr(h.callback, "__name__", "").startswith("signal_") and getattr(h.callback, "__name__", "") not in {"_publish_result_to_channel", "_publish_result_with_fallback"}]


async def main():
    global BOT_USERNAME
    db.init_db()
    db.ensure_default_plans(settings.plans)
    # Some local networks return an incorrect internal address for Telegram's
    # API through the default Windows resolver. Use public DNS and IPv4 for the
    # Telegram client while keeping the rest of the application unchanged.
    telegram_session = AiohttpSession()
    if os.getenv("TELEGRAM_PUBLIC_DNS", "true").strip().lower() in {"1", "true", "yes", "on"}:
        telegram_session._connector_init["resolver"] = AsyncResolver(
            nameservers=["8.8.8.8", "1.1.1.1"]
        )
        telegram_session._connector_init["family"] = socket.AF_INET
    bot = Bot(settings.bot_token, session=telegram_session)
    fsm_path = Path(__file__).resolve().parent.parent / "nexus_fsm.db"
    dp = Dispatcher(storage=SQLiteStorage(fsm_path))
    # v0.6.0: Telegram has no signal authority. Legacy signal handlers remain
    # in source for migration traceability but are removed from the Dispatcher.
    _disable_telegram_signal_authority()
    dp.include_router(analytics_router)
    dp.include_router(subscriptions_router)
    dp.include_router(router)
    me=await bot.get_me(); BOT_USERNAME=me.username or ""; log.info("Starting NEXUS CORE v0.6.5 @%s",me.username)
    if not any(_usdt_plan_ready(p) for p in _plans().values()):
        log.warning("USDT payment is not active for any plan; configure wallet/network and a plan USDT price")
    worker=asyncio.create_task(expiry_worker(bot)); backup_task=asyncio.create_task(backup_worker()); report_task=asyncio.create_task(report_worker(bot)); autotrade_notify_task=asyncio.create_task(autotrade_notification_worker(bot)); mt5_publish_task=asyncio.create_task(mt5_publication_retry_worker(bot))
    try:
        await dp.start_polling(bot,allowed_updates=dp.resolve_used_update_types())
    finally:
        worker.cancel(); backup_task.cancel(); report_task.cancel(); autotrade_notify_task.cancel(); mt5_publish_task.cancel()
        for task in list(BACKGROUND_TASKS):
            task.cancel()
        if BACKGROUND_TASKS:
            await asyncio.gather(*list(BACKGROUND_TASKS), return_exceptions=True)
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
