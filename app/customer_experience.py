from __future__ import annotations

import logging
import os
from html import escape
from pathlib import Path
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot, Router
from aiogram.enums import ChatMemberStatus, ParseMode
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from . import db
from .config import settings
from .services import license_service
from .states import Flow

log = logging.getLogger("nexus.customer-experience")
router = Router(name="nexus-customer-experience")

NEXUS_FOLDER_URL = os.getenv("NEXUS_FOLDER_URL", "https://t.me/+UZgLQ-uYwn5jNGE0").strip()
AUTOTRADE_PUBLIC_API_URL = os.getenv("AUTOTRADE_PUBLIC_API_URL", "https://api.nexustrade.ir").strip()
EXPECTED_VIP_CHANNEL_ID = -1003900670697

FAQS: dict[str, dict[str, tuple[str, str]]] = {
    "subscription": {
        "q": ("اشتراک NEXUS را از کجا بخرم؟", "Where can I buy a NEXUS subscription?"),
        "a": (
            "خرید و تمدید فقط از منوی «💎 خرید اشتراک» در صفحه اصلی ربات انجام می‌شود. پس از تأیید پرداخت، دسترسی سرویس خریداری‌شده به‌صورت خودکار فعال می‌شود.",
            "Purchase and renewal are available only from the “💎 Buy Subscription” button on the main bot menu. Access is activated automatically after payment approval.",
        ),
    },
    "vip": {
        "q": ("چطور وارد کانال سیگنال VIP شوم؟", "How do I enter the VIP signal channel?"),
        "a": (
            "اگر اشتراک VIP فعال داشته باشید، از صفحه اصلی «کانال سیگنال VIP» را بزنید. ربات اشتراک شما را بررسی و یک لینک امن مخصوص همان حساب تلگرام ایجاد می‌کند.",
            "If your VIP subscription is active, tap “VIP Signal Channel” on the main menu. The bot validates your entitlement and creates a secure invite for that Telegram account.",
        ),
    },
    "autotrade": {
        "q": ("بعد از خرید AutoTrade چه چیزی دریافت می‌کنم؟", "What do I receive after buying AutoTrade?"),
        "a": (
            "پس از تأیید خرید، شماره حساب MT5 را ثبت می‌کنید. سپس لایسنس اختصاصی، فایل اکسپرت MT5 و فلش‌کارت فعال‌سازی شامل آدرس سرور NEXUS برای شما ارسال می‌شود.",
            "After payment approval, register your MT5 account. You will then receive your dedicated license, the MT5 Expert file, and an activation flash card containing the NEXUS server address.",
        ),
    },
    "license": {
        "q": ("لایسنس AutoTrade به چه چیزی متصل می‌شود؟", "What is the AutoTrade license bound to?"),
        "a": (
            "لایسنس AutoTrade به شماره حساب MetaTrader 5 ثبت‌شده شما متصل می‌شود. تغییر حساب باید از مسیر درخواست تغییر حساب MT5 انجام و تأیید شود.",
            "The AutoTrade license is bound to your registered MetaTrader 5 account. Account changes must go through the MT5 account-change request flow.",
        ),
    },
    "server": {
        "q": ("آدرس سرور NEXUS برای متاتریدر چیست؟", "What is the NEXUS server address for MetaTrader?"),
        "a": (
            f"آدرس رسمی سرویس AutoTrade: <code>{escape(AUTOTRADE_PUBLIC_API_URL)}</code>",
            f"Official AutoTrade service address: <code>{escape(AUTOTRADE_PUBLIC_API_URL)}</code>",
        ),
    },
    "support": {
        "q": ("اگر در فعال‌سازی مشکل داشتم چه کار کنم؟", "What if I have an activation problem?"),
        "a": (
            "از منوی «🛟 پشتیبانی» در صفحه اصلی استفاده کنید. برای بررسی سریع‌تر، شماره حساب MT5 و شرح خطا را همراه پیام ارسال کنید؛ لایسنس یا اطلاعات حساس دیگران را ارسال نکنید.",
            "Use “🛟 Support” on the main menu. For faster troubleshooting, include your MT5 account number and the error description; do not share another person’s license or sensitive credentials.",
        ),
    },
}


def _nav_buttons(lang: str, back: str = "main") -> list[InlineKeyboardButton]:
    if lang == "fa":
        return [
            InlineKeyboardButton(text="⬅️ بازگشت", callback_data=back),
            InlineKeyboardButton(text="🏠 منوی اصلی", callback_data="main"),
        ]
    return [
        InlineKeyboardButton(text="⬅️ Back", callback_data=back),
        InlineKeyboardButton(text="🏠 Main Menu", callback_data="main"),
    ]


def customer_main_menu(lang: str, *, is_admin: bool, has_vip: bool) -> InlineKeyboardMarkup:
    vip_icon = "🔓" if has_vip else "🔒"
    if lang == "fa":
        rows = [
            [
                InlineKeyboardButton(text="📊 سیگنال", callback_data="client_signals"),
                InlineKeyboardButton(text="💎 خرید اشتراک", callback_data="vip"),
            ],
            [
                InlineKeyboardButton(text="👤 حساب من", callback_data="account"),
                InlineKeyboardButton(text="🎓 راهنما", callback_data="guide_hub"),
            ],
            [InlineKeyboardButton(text="🚪 ورود به نکسوس", url=NEXUS_FOLDER_URL)],
            [InlineKeyboardButton(text=f"{vip_icon} کانال سیگنال VIP", callback_data="vip_channel_access")],
            [
                InlineKeyboardButton(text="❓ سوالات متداول", callback_data="faq"),
                InlineKeyboardButton(text="🛟 پشتیبانی", callback_data="support"),
            ],
            [InlineKeyboardButton(text="🌐 تغییر زبان", callback_data="change_language")],
        ]
        if is_admin:
            rows.append([InlineKeyboardButton(text="🛠 پنل مدیریت", callback_data="admin")])
    else:
        rows = [
            [
                InlineKeyboardButton(text="📊 Signals", callback_data="client_signals"),
                InlineKeyboardButton(text="💎 Buy Subscription", callback_data="vip"),
            ],
            [
                InlineKeyboardButton(text="👤 My Account", callback_data="account"),
                InlineKeyboardButton(text="🎓 Guide", callback_data="guide_hub"),
            ],
            [InlineKeyboardButton(text="🚪 Enter NEXUS", url=NEXUS_FOLDER_URL)],
            [InlineKeyboardButton(text=f"{vip_icon} VIP Signal Channel", callback_data="vip_channel_access")],
            [
                InlineKeyboardButton(text="❓ FAQ", callback_data="faq"),
                InlineKeyboardButton(text="🛟 Support", callback_data="support"),
            ],
            [InlineKeyboardButton(text="🌐 Change Language", callback_data="change_language")],
        ]
        if is_admin:
            rows.append([InlineKeyboardButton(text="🛠 Admin Panel", callback_data="admin")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def customer_account_menu(lang: str, has_vip: bool, has_autotrade: bool = False) -> InlineKeyboardMarkup:
    """Account menu without a second purchase entry point.

    Purchasing is intentionally available only from the main-menu Buy Subscription
    button. Status/access pages never initiate a purchase.
    """
    if lang == "fa":
        rows = [
            [
                InlineKeyboardButton(
                    text=("🔓 وضعیت VIP" if has_vip else "🔒 وضعیت VIP"),
                    callback_data=("client_vip_access" if has_vip else "vip_locked_info"),
                ),
                InlineKeyboardButton(
                    text=("🔓 وضعیت AutoTrade" if has_autotrade else "🔒 وضعیت AutoTrade"),
                    callback_data=("client_autotrade_access" if has_autotrade else "autotrade_locked_info"),
                ),
            ],
            [
                InlineKeyboardButton(text="💳 پرداخت‌های من", callback_data="my_payments"),
                InlineKeyboardButton(text="🎁 دعوت دوستان", callback_data="referral"),
            ],
        ]
        if has_vip:
            rows.append([InlineKeyboardButton(text="🔐 کانال سیگنال VIP", callback_data="vip_channel_access")])
        rows.append([InlineKeyboardButton(text="🌐 تغییر زبان", callback_data="change_language")])
    else:
        rows = [
            [
                InlineKeyboardButton(
                    text=("🔓 VIP Status" if has_vip else "🔒 VIP Status"),
                    callback_data=("client_vip_access" if has_vip else "vip_locked_info"),
                ),
                InlineKeyboardButton(
                    text=("🔓 AutoTrade Status" if has_autotrade else "🔒 AutoTrade Status"),
                    callback_data=("client_autotrade_access" if has_autotrade else "autotrade_locked_info"),
                ),
            ],
            [
                InlineKeyboardButton(text="💳 My Payments", callback_data="my_payments"),
                InlineKeyboardButton(text="🎁 Invite Friends", callback_data="referral"),
            ],
        ]
        if has_vip:
            rows.append([InlineKeyboardButton(text="🔐 VIP Signal Channel", callback_data="vip_channel_access")])
        rows.append([InlineKeyboardButton(text="🌐 Change Language", callback_data="change_language")])
    rows.append(_nav_buttons(lang, "main"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def customer_signal_menu(lang: str, has_vip: bool, has_autotrade: bool = False) -> InlineKeyboardMarkup:
    if lang == "fa":
        rows = [
            [InlineKeyboardButton(text="🎯 سیگنال عمومی", callback_data="public")],
            [
                InlineKeyboardButton(
                    text=("🔓 سیگنال VIP" if has_vip else "🔒 سیگنال VIP"),
                    callback_data=("client_vip_access" if has_vip else "vip_locked_info"),
                ),
                InlineKeyboardButton(
                    text=("🔓 سیگنال + AutoTrade" if has_autotrade else "🔒 سیگنال + AutoTrade"),
                    callback_data=("client_autotrade_access" if has_autotrade else "autotrade_locked_info"),
                ),
            ],
        ]
    else:
        rows = [
            [InlineKeyboardButton(text="🎯 Public Signals", callback_data="public")],
            [
                InlineKeyboardButton(
                    text=("🔓 VIP Signals" if has_vip else "🔒 VIP Signals"),
                    callback_data=("client_vip_access" if has_vip else "vip_locked_info"),
                ),
                InlineKeyboardButton(
                    text=("🔓 Signals + AutoTrade" if has_autotrade else "🔒 Signals + AutoTrade"),
                    callback_data=("client_autotrade_access" if has_autotrade else "autotrade_locked_info"),
                ),
            ],
        ]
    rows.append(_nav_buttons(lang, "main"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def faq_menu(lang: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    index = 0 if lang == "fa" else 1
    for key, item in FAQS.items():
        rows.append([InlineKeyboardButton(text=f"❔ {item['q'][index]}", callback_data=f"faq:{key}")])
    rows.append(_nav_buttons(lang, "main"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(lambda cb: cb.data == "faq")
async def faq_home(cb: CallbackQuery, bot: Bot) -> None:
    from . import main as core

    if not await core.gated(cb, bot):
        return
    lang = core.get_lang(cb.from_user.id)
    await cb.answer()
    text = core.tr(
        lang,
        "<b>❓ سوالات متداول NEXUS</b>\n\nیکی از سوالات زیر را انتخاب کنید:",
        "<b>❓ NEXUS FAQ</b>\n\nChoose a question below:",
    )
    await core.screen(bot, cb.from_user.id, cb.message.chat.id, text, faq_menu(lang))


@router.callback_query(lambda cb: bool(cb.data and cb.data.startswith("faq:")))
async def faq_answer(cb: CallbackQuery, bot: Bot) -> None:
    from . import main as core

    if not await core.gated(cb, bot):
        return
    lang = core.get_lang(cb.from_user.id)
    key = str(cb.data).split(":", 1)[1]
    item = FAQS.get(key)
    if not item:
        await cb.answer(core.tr(lang, "سوال پیدا نشد.", "Question not found."), show_alert=True)
        return
    index = 0 if lang == "fa" else 1
    await cb.answer()
    text = f"<b>❔ {escape(item['q'][index])}</b>\n\n{item['a'][index]}"
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=("📚 همه سوالات" if lang == "fa" else "📚 All Questions"), callback_data="faq")],
        _nav_buttons(lang, "faq"),
    ])
    await core.screen(bot, cb.from_user.id, cb.message.chat.id, text, markup)


@router.callback_query(lambda cb: cb.data == "vip_locked_info")
async def vip_locked_info(cb: CallbackQuery, bot: Bot) -> None:
    from . import main as core

    lang = core.get_lang(cb.from_user.id)
    message = core.tr(
        lang,
        "برای ورود به کانال سیگنال VIP باید اشتراک تهیه کنید",
        "You need a VIP subscription to enter the VIP signal channel.",
    )
    await cb.answer(message, show_alert=True)


@router.callback_query(lambda cb: cb.data == "autotrade_locked_info")
async def autotrade_locked_info(cb: CallbackQuery, bot: Bot) -> None:
    from . import main as core

    lang = core.get_lang(cb.from_user.id)
    await cb.answer(
        core.tr(
            lang,
            "AutoTrade برای حساب شما فعال نیست. خرید فقط از منوی «خرید اشتراک» در صفحه اصلی انجام می‌شود.",
            "AutoTrade is not active for your account. Purchase is available only from “Buy Subscription” on the main menu.",
        ),
        show_alert=True,
    )


@router.callback_query(lambda cb: cb.data == "vip_channel_access")
async def vip_channel_access(cb: CallbackQuery, bot: Bot) -> None:
    from . import main as core

    if not await core.gated(cb, bot):
        return
    user_id = int(cb.from_user.id)
    lang = core.get_lang(user_id)
    lic = db.active_license(user_id)
    access = license_service.snapshot(user_id)
    if not (lic and access.vip and license_service.has_vip(user_id)):
        await cb.answer(
            core.tr(
                lang,
                "برای ورود به کانال سیگنال VIP باید اشتراک تهیه کنید",
                "You need a VIP subscription to enter the VIP signal channel.",
            ),
            show_alert=True,
        )
        return

    if int(settings.vip_channel_id) != EXPECTED_VIP_CHANNEL_ID:
        log.warning(
            "VIP_CHANNEL_ID=%s differs from requested production channel %s",
            settings.vip_channel_id,
            EXPECTED_VIP_CHANNEL_ID,
        )

    member_active = False
    try:
        member = await bot.get_chat_member(settings.vip_channel_id, user_id)
        member_active = member.status not in {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED}
    except Exception as exc:
        log.warning("VIP membership check failed for %s: %s", user_id, exc)

    try:
        link = await core.make_secure_invite(bot, user_id, int(lic["id"]))
    except Exception as exc:
        log.exception("VIP secure invite creation failed for user=%s", user_id)
        await cb.answer(
            core.tr(
                lang,
                "اشتراک شما فعال است اما لینک ورود فعلاً ساخته نشد. با پشتیبانی تماس بگیرید.",
                "Your subscription is active, but the invite could not be created. Contact support.",
            ),
            show_alert=True,
        )
        return

    vip_exp = lic["vip_expires_at"] if "vip_expires_at" in lic.keys() and lic["vip_expires_at"] else lic["expires_at"]
    status_line = core.tr(lang, "عضویت کانال: <b>فعال</b>" if member_active else "عضویت کانال: <b>در انتظار ورود</b>", "Channel membership: <b>Active</b>" if member_active else "Channel membership: <b>Ready to join</b>")
    text = core.tr(
        lang,
        f"<b>💎 کانال سیگنال VIP</b>\n\n✅ اشتراک شما فعال است.\n{status_line}\n📅 اعتبار تا: <b>{core.fmt_dt(vip_exp)}</b>\n\nلینک زیر مخصوص حساب تلگرام شماست و درخواست حساب دیگر تأیید نمی‌شود.",
        f"<b>💎 VIP Signal Channel</b>\n\n✅ Your subscription is active.\n{status_line}\n📅 Valid until: <b>{core.fmt_dt(vip_exp)}</b>\n\nThe link below is tied to your Telegram account; another account will not be approved.",
    )
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=("🚪 ورود به کانال VIP" if lang == "fa" else "🚪 Enter VIP Channel"), url=link)],
        _nav_buttons(lang, "main"),
    ])
    await cb.answer()
    await core.screen(bot, user_id, cb.message.chat.id, text, markup)


async def send_autotrade_purchase_bundle(core: Any, bot: Bot, user_id: int) -> bool:
    """Deliver the post-purchase AutoTrade flash card and EX5 after MT5 binding."""
    lic = db.active_license(user_id)
    if not lic or not license_service.has_autotrade(user_id):
        return False
    key = str(lic["license_key"] or "").strip()
    account = db.mt5_account(user_id)
    if not key or not account:
        return False

    lang = core.get_lang(user_id)
    auto_exp = lic["autotrade_expires_at"] if "autotrade_expires_at" in lic.keys() and lic["autotrade_expires_at"] else lic["expires_at"]
    card = core.tr(
        lang,
        (
            "<b>🤖 NEXUS AutoTrade — فلش کارت فعال‌سازی</b>\n\n"
            "✅ وضعیت: <b>فعال</b>\n"
            f"🔑 <b>مجوز من:</b> <code>{escape(key)}</code>\n"
            f"🖥 <b>حساب MT5:</b> <code>{escape(str(account['account_number']))}</code>\n"
            f"🌐 <b>آدرس سرور:</b> <code>{escape(AUTOTRADE_PUBLIC_API_URL)}</code>\n"
            f"📅 <b>اعتبار تا:</b> {core.fmt_dt(auto_exp)}\n\n"
            "فایل اکسپرت را در MT5 نصب کنید و همین License Key را در پنل NEXUS وارد کنید."
        ),
        (
            "<b>🤖 NEXUS AutoTrade — Activation Flash Card</b>\n\n"
            "✅ Status: <b>Active</b>\n"
            f"🔑 <b>My License:</b> <code>{escape(key)}</code>\n"
            f"🖥 <b>MT5 Account:</b> <code>{escape(str(account['account_number']))}</code>\n"
            f"🌐 <b>Server:</b> <code>{escape(AUTOTRADE_PUBLIC_API_URL)}</code>\n"
            f"📅 <b>Valid until:</b> {core.fmt_dt(auto_exp)}\n\n"
            "Install the Expert in MT5 and enter this License Key in the NEXUS panel."
        ),
    )

    repo_root = Path(__file__).resolve().parents[1]
    candidates = [
        repo_root / "assets" / "autotrade" / "NEXUS_AutoTrade.ex5",
        repo_root / "app" / "assets" / "autotrade" / "NEXUS_AutoTrade.ex5",
    ]
    ea_path = next((path for path in candidates if path.is_file()), None)
    if ea_path is not None:
        await bot.send_document(
            user_id,
            BufferedInputFile(ea_path.read_bytes(), filename="NEXUS_AutoTrade.ex5"),
            caption=card,
            parse_mode=ParseMode.HTML,
            protect_content=True,
        )
    else:
        await bot.send_message(user_id, card, parse_mode=ParseMode.HTML)
        await bot.send_message(
            user_id,
            core.tr(
                lang,
                "⚠️ لایسنس صادر شد اما فایل NEXUS_AutoTrade.ex5 روی سرور پیدا نشد. پشتیبانی باید فایل Release را روی VPS قرار دهد.",
                "⚠️ Your license was issued, but NEXUS_AutoTrade.ex5 was not found on the server. Support must place the release file on the VPS.",
            ),
        )
        log.error("AutoTrade EX5 missing for post-purchase delivery; checked: %s", candidates)

    await bot.send_message(
        user_id,
        core.tr(
            lang,
            f"📌 آدرس سرور NEXUS برای تنظیمات MetaTrader 5:\n<code>{escape(AUTOTRADE_PUBLIC_API_URL)}</code>",
            f"📌 NEXUS server address for MetaTrader 5:\n<code>{escape(AUTOTRADE_PUBLIC_API_URL)}</code>",
        ),
        parse_mode=ParseMode.HTML,
    )
    return True


class AccessShortcutGuardMiddleware(BaseMiddleware):
    """Prevent locked status pages from becoming alternate purchase entry points."""

    async def __call__(
        self,
        handler: Callable[[CallbackQuery, dict[str, Any]], Awaitable[Any]],
        event: CallbackQuery,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, CallbackQuery) and event.from_user and event.data:
            uid = int(event.from_user.id)
            access = license_service.snapshot(uid)
            if event.data == "client_vip_access" and not access.vip:
                from . import main as core

                await event.answer(
                    core.tr(
                        core.get_lang(uid),
                        "برای ورود به کانال سیگنال VIP باید اشتراک تهیه کنید",
                        "You need a VIP subscription to enter the VIP signal channel.",
                    ),
                    show_alert=True,
                )
                return None
            if event.data == "client_autotrade_access" and not access.autotrade:
                from . import main as core

                await event.answer(
                    core.tr(
                        core.get_lang(uid),
                        "AutoTrade برای حساب شما فعال نیست. خرید فقط از منوی «خرید اشتراک» در صفحه اصلی انجام می‌شود.",
                        "AutoTrade is not active. Purchase is available only from “Buy Subscription” on the main menu.",
                    ),
                    show_alert=True,
                )
                return None
        return await handler(event, data)


class AutoTradePostLicenseDeliveryMiddleware(BaseMiddleware):
    """Send the AutoTrade bundle immediately after a successful initial MT5 bind."""

    def __init__(self, core: Any):
        self.core = core

    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        state = data.get("state")
        before_state = await state.get_state() if state is not None else None
        initial_state = Flow.autotrade_initial_account.state
        should_watch = bool(
            isinstance(event, Message)
            and event.from_user
            and before_state == initial_state
        )

        result = await handler(event, data)
        if not should_watch:
            return result

        try:
            after_state = await state.get_state() if state is not None else None
            if after_state == initial_state:
                # Validation failed; the core handler intentionally kept the state active.
                return result
            user_id = int(event.from_user.id)
            delivered = await send_autotrade_purchase_bundle(self.core, data["bot"], user_id)
            if delivered:
                await self.core.push_home_to_bottom(data["bot"], user_id)
        except Exception:
            log.exception("post-purchase AutoTrade bundle delivery failed")
        return result


def install_customer_experience(core: Any) -> None:
    """Attach the customer UX without rewriting the large core module.

    The core remains the authority for subscriptions, payment approval, secure
    join requests and MT5 license issuance. This extension changes only customer
    navigation/delivery and runs on top of those authoritative states.
    """
    if getattr(core.router, "__nexus_customer_experience_installed__", False):
        return

    # Replace only UI builders referenced by core handlers. This removes alternate
    # purchase shortcuts while preserving all existing callback contracts.
    core.account_menu = customer_account_menu
    core.client_signal_menu = customer_signal_menu

    async def dynamic_show_main(bot: Bot, user_id: int, chat_id: int) -> None:
        lang = core.get_lang(user_id)
        access = license_service.snapshot(user_id)
        await core.screen(
            bot,
            user_id,
            chat_id,
            core.tr(
                lang,
                "<b>⚡ NEXUS</b>\n\nاز این بخش می‌توانید سیگنال‌ها، معاملات خودکار و حساب کاربری خود را مدیریت کنید.\n\nسرویس موردنظر را انتخاب کنید:",
                "<b>⚡ NEXUS</b>\n\nManage signals, Auto Trade and your account from here.\n\nSelect a service:",
            ),
            customer_main_menu(lang, is_admin=core.is_admin(user_id), has_vip=bool(access.vip)),
        )

    async def dynamic_push_home_to_bottom(bot: Bot, user_id: int) -> None:
        user = db.get_user(user_id)
        if not user:
            return
        old_id = user["last_menu_message_id"]
        if old_id:
            try:
                await bot.delete_message(user_id, int(old_id))
            except Exception:
                pass
        lang = core.get_lang(user_id)
        if core.is_admin(user_id):
            text = core.tr(lang, "<b>🛠 پنل ادمین NEXUS</b>", "<b>🛠 NEXUS Admin Panel</b>")
            markup = core.admin_menu(lang)
        else:
            access = license_service.snapshot(user_id)
            text = core.tr(lang, "<b>⚡ NEXUS</b>\n\nمنوی اصلی", "<b>⚡ NEXUS</b>\n\nMain Menu")
            markup = customer_main_menu(lang, is_admin=False, has_vip=bool(access.vip))
        msg = await bot.send_message(user_id, text, reply_markup=markup, parse_mode=ParseMode.HTML)
        db.set_last_menu_message(user_id, msg.message_id)

    core.show_main = dynamic_show_main
    core.push_home_to_bottom = dynamic_push_home_to_bottom

    core.router.callback_query.middleware(AccessShortcutGuardMiddleware())
    core.router.message.middleware(AutoTradePostLicenseDeliveryMiddleware(core))
    core.router.include_router(router)
    core.router.__nexus_customer_experience_installed__ = True

    if int(settings.vip_channel_id) != EXPECTED_VIP_CHANNEL_ID:
        log.warning(
            "Production requirement expects VIP_CHANNEL_ID=%s, current configuration is %s",
            EXPECTED_VIP_CHANNEL_ID,
            settings.vip_channel_id,
        )
