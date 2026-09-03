from __future__ import annotations

"""NEXUS v0.6.5 customer UX hardening layer.

This module intentionally patches the already-imported ``app.main`` module before
polling starts. It lets the feature branch isolate customer-facing changes from
live MT5 execution code while the NX-0001 production-correctness test is running.
The legacy exchange connector/database code remains available for rollback, but
its Telegram runtime routes are unregistered and no exchange UI is rendered.
"""

import asyncio
import logging
from html import escape
from pathlib import Path

from aiogram import F
from aiogram.enums import ParseMode

from .services.autotrade_delivery_service import AutoTradeDeliveryError, deliver_mt5_package
from .services.license_view import render_autotrade_license
from .services.message_lifecycle import DEFAULT_INFO_TTL_SECONDS, delete_after, delete_message_logged
from .services.usdt_rate_monitor import usdt_rate_worker


log = logging.getLogger(__name__)
_INSTALLED = False


EXCHANGE_CALLBACK_HANDLER_NAMES = {
    "autotrade_exchange",
    "exchange_select",
    "exchange_disconnect",
    "exchange_retest",
}
EXCHANGE_MESSAGE_HANDLER_NAMES = {
    "exchange_api_key_input",
    "exchange_api_secret_input",
    "exchange_api_passphrase_input",
}
REPLACED_CALLBACK_HANDLER_NAMES = {
    "client_autotrade_access",
    "autotrade_status",
    "autotrade_license",
    "guide_hub",
    "guide_video",
    "guide_text",
    "autotrade_video_guide",
    "pricing_settings",
    "pricing_source_input",
}
REPLACED_MESSAGE_HANDLER_NAMES = {
    "pricing_source_save",
}


def _remove_handlers(observer, names: set[str]) -> None:
    observer.handlers[:] = [
        h for h in observer.handlers
        if getattr(h.callback, "__name__", "") not in names
    ]


def _autotrade_user_menu(main, lang: str, *, mt5_connected: bool = False, **_ignored):
    if lang == "fa":
        rows = [
            [("📊 وضعیت معاملات خودکار", "autotrade_status"), ("🖥 معاملات باز", "autotrade_open")],
            [("📜 تاریخچه معاملات", "autotrade_history"), ("📅 گزارش امروز", "autotrade_today")],
            [("🔑 مجوز من", "autotrade_license"), ("📥 دریافت اکسپرت MT5", "autotrade_download_mt5")],
            [("🔄 درخواست تغییر حساب MT5", "autotrade_account_change")],
            [("🆘 راهنمای AutoTrade", "autotrade_help")],
        ]
    else:
        rows = [
            [("📊 Auto Trade Status", "autotrade_status"), ("🖥 Open Trades", "autotrade_open")],
            [("📜 Trade History", "autotrade_history"), ("📅 Today's Report", "autotrade_today")],
            [("🔑 My License", "autotrade_license"), ("📥 Download MT5 EA", "autotrade_download_mt5")],
            [("🔄 Change MT5 Account", "autotrade_account_change")],
            [("🆘 AutoTrade Help", "autotrade_help")],
        ]
    rows += main.nav(lang, "main")
    return main.kb(rows)


async def _screen(main, bot, user_id: int, chat_id: int, text: str, markup=None) -> None:
    """Single-dashboard rendering with observable delete outcomes."""
    if isinstance(text, (tuple, list)):
        text = "".join(str(x) for x in text)
    elif not isinstance(text, str):
        text = str(text)

    user = main.db.get_user(user_id)
    old_id = user["last_menu_message_id"] if user else None
    if old_id:
        await delete_message_logged(bot, chat_id, int(old_id), reason="dashboard_replaced")

    msg = await bot.send_message(
        chat_id,
        text,
        reply_markup=markup,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )
    main.db.set_last_menu_message(user_id, msg.message_id)


async def _show_autotrade_home(main, bot, user_id: int, chat_id: int) -> None:
    lang = main.get_lang(user_id)
    access = main.license_service.snapshot(user_id)
    if not access.autotrade:
        markup = main.kb([
            [("💎 خرید / تمدید اشتراک" if lang == "fa" else "💎 Buy / Renew", "vip")]
        ] + main.nav(lang, "client_signals"))
        await main.screen(
            bot,
            user_id,
            chat_id,
            main.tr(
                lang,
                "<b>🤖 NEXUS AutoTrade</b>\n\n🔴 وضعیت سرویس: <b>غیرفعال</b>\n\nبرای استفاده از معاملات خودکار، سرویس AutoTrade یا پکیج VIP + AutoTrade را تهیه/تمدید کنید.",
                "<b>🤖 NEXUS AutoTrade</b>\n\n🔴 Service: <b>INACTIVE</b>\n\nPurchase or renew AutoTrade / VIP + AutoTrade to use automatic execution.",
            ),
            markup,
        )
        return

    mt5 = main.db.mt5_account(user_id)
    await main.screen(
        bot,
        user_id,
        chat_id,
        main.tr(
            lang,
            "<b>🤖 NEXUS AutoTrade</b>\n\n🟢 وضعیت سرویس: <b>فعال</b>\n"
            f"🖥 اتصال MT5: <b>{'متصل' if mt5 else 'متصل نیست'}</b>\n\n"
            "جزئیات لایسنس، تاریخ شروع/پایان و زمان باقی‌مانده فقط از بخش «🔑 مجوز من» نمایش داده می‌شود.",
            "<b>🤖 NEXUS AutoTrade</b>\n\n🟢 Service: <b>ACTIVE</b>\n"
            f"🖥 MT5: <b>{'CONNECTED' if mt5 else 'NOT CONNECTED'}</b>\n\n"
            "License key, start/expiry and remaining validity are shown only under “🔑 My License”.",
        ),
        main.autotrade_user_menu(lang, mt5_connected=bool(mt5)),
    )


def _register_customer_handlers(main) -> None:
    async def client_autotrade_access(cb, bot):
        if not await main.gated(cb, bot):
            return
        await cb.answer()
        await main._show_autotrade_home(bot, cb.from_user.id, cb.message.chat.id)

    async def autotrade_status(cb, bot):
        if not await main.gated(cb, bot):
            return
        uid = int(cb.from_user.id)
        lang = main.get_lang(uid)
        access = main.license_service.snapshot(uid)
        await cb.answer()
        if not access.autotrade:
            await main._show_autotrade_home(bot, uid, cb.message.chat.id)
            return
        mt5 = main.db.mt5_account(uid)
        mt5_line = (
            f"{escape(str(mt5['account_number']))} / {escape(str(mt5['broker'] or '—'))}"
            if mt5 else ("متصل نیست" if lang == "fa" else "NOT CONNECTED")
        )
        text = main.tr(
            lang,
            "<b>📊 وضعیت معاملات خودکار</b>\n\n"
            "🟢 سرویس: <b>فعال</b>\n"
            f"🖥 MT5: <b>{mt5_line}</b>\n\n"
            "برای مشاهده License Key، نوع اشتراک، تاریخ شروع/پایان و زمان باقی‌مانده وارد «🔑 مجوز من» شوید.",
            "<b>📊 Auto Trade Status</b>\n\n"
            "🟢 Service: <b>ACTIVE</b>\n"
            f"🖥 MT5: <b>{mt5_line}</b>\n\n"
            "Open “🔑 My License” for the key, subscription type, start/expiry and precise remaining validity.",
        )
        await main.screen(bot, uid, cb.message.chat.id, text, main.autotrade_user_menu(lang, mt5_connected=bool(mt5)))

    async def autotrade_license(cb, bot):
        if not await main.gated(cb, bot):
            return
        uid = int(cb.from_user.id)
        lang = main.get_lang(uid)
        await cb.answer()
        snapshot = main.license_service.snapshot(uid)
        lic = main.db.active_license(uid)
        account = main.db.mt5_account(uid)
        plan = main.db.get_plan(snapshot.plan_code) if snapshot.plan_code else None
        text, needs_cta = render_autotrade_license(
            snapshot,
            license_key=(str(lic["license_key"] or "") if lic else None),
            mt5_account=(str(account["account_number"]) if account else None),
            plan=plan,
            timezone_obj=main.TZ,
            lang=lang,
        )
        if needs_cta:
            markup = main.kb([
                [("💎 خرید / تمدید اشتراک" if lang == "fa" else "💎 Buy / Renew", "vip")]
            ] + main.nav(lang, "client_autotrade_access"))
        else:
            markup = main.autotrade_user_menu(lang, mt5_connected=bool(account))
        await main.screen(bot, uid, cb.message.chat.id, text, markup)

    main.router.callback_query.register(client_autotrade_access, F.data == "client_autotrade_access")
    main.router.callback_query.register(autotrade_status, F.data == "autotrade_status")
    main.router.callback_query.register(autotrade_license, F.data == "autotrade_license")


def _register_guide_handlers(main) -> None:
    async def guide_hub(cb, bot):
        if not await main.gated(cb, bot):
            return
        lang = main.get_lang(cb.from_user.id)
        await cb.answer()
        text = main.tr(
            lang,
            "<b>🎓 معرفی و راهنمای NEXUS</b>\n\n"
            "• معرفی NEXUS و خدمات\n"
            "• خرید و فعال‌سازی اشتراک\n"
            "• نصب و فعال‌سازی NEXUS AutoTrade روی MT5\n"
            "• راهنمای متنی\n\n"
            "یکی از گزینه‌های زیر را انتخاب کنید.",
            "<b>🎓 NEXUS Introduction & Guides</b>\n\n"
            "• NEXUS services overview\n"
            "• Purchase and subscription activation\n"
            "• NEXUS AutoTrade installation and activation on MT5\n"
            "• Text guide\n\n"
            "Choose a section below.",
        )
        await main.screen(bot, cb.from_user.id, cb.message.chat.id, text, main.guide_hub_menu(lang))

    async def guide_video(cb, bot):
        if not await main.gated(cb, bot):
            return
        kind = cb.data.split("_", 1)[1]
        if kind not in {"intro", "purchase", "mt5"}:
            await cb.answer()
            return
        lang = main.get_lang(cb.from_user.id)
        await cb.answer()
        ok = await main._send_guide_video(bot, cb.from_user.id, kind)
        if not ok:
            path, _, fa_title, en_title = main._guide_video_spec(kind)
            await bot.send_message(
                cb.from_user.id,
                main.tr(
                    lang,
                    f"🎥 <b>{escape(fa_title)}</b>\n\nکلیپ هنوز روی سرور قرار نگرفته است.\nنام فایل مورد انتظار: <code>{escape(path.name)}</code>",
                    f"🎥 <b>{escape(en_title)}</b>\n\nThe video has not been uploaded yet.\nExpected filename: <code>{escape(path.name)}</code>",
                ),
                parse_mode=ParseMode.HTML,
            )
        await main.push_home_to_bottom(bot, int(cb.from_user.id))

    async def guide_text(cb, bot):
        if not await main.gated(cb, bot):
            return
        lang = main.get_lang(cb.from_user.id)
        await cb.answer()
        text = main.tr(
            lang,
            "<b>📘 راهنمای سریع NEXUS</b>\n\n"
            "<b>سیگنال‌ها:</b> دسترسی عمومی یا VIP را از بخش سیگنال انتخاب کنید.\n\n"
            "<b>خرید:</b> پلن را انتخاب، پرداخت را انجام و رسید را ارسال کنید.\n\n"
            "<b>AutoTrade MT5:</b> پس از فعال‌سازی، حساب MT5 را ثبت کنید؛ سپس EX5 و راهنمای نصب را دریافت و EA را روی MT5 فعال کنید.\n\n"
            "<b>امنیت:</b> License Key و فایل اختصاصی خود را در اختیار دیگران قرار ندهید. AutoTrade تضمین سودآوری نیست.",
            "<b>📘 NEXUS Quick Guide</b>\n\n"
            "<b>Signals:</b> Choose Public or VIP access under Signals.\n\n"
            "<b>Purchase:</b> Choose a plan, pay, and submit the receipt.\n\n"
            "<b>MT5 AutoTrade:</b> After activation, register your MT5 account, receive the EX5 and installation guide, and activate the EA on MT5.\n\n"
            "<b>Security:</b> Do not share your License Key or installer. AutoTrade does not guarantee profitability.",
        )
        await main.screen(bot, cb.from_user.id, cb.message.chat.id, text, main.guide_back_menu(lang))

    main.router.callback_query.register(guide_hub, F.data == "guide_hub")
    main.router.callback_query.register(
        guide_video,
        F.data.in_({"guide_intro", "guide_purchase", "guide_mt5"}),
    )
    main.router.callback_query.register(guide_text, F.data == "guide_text")


def _install_delivery(main) -> None:
    async def send_mt5_package(bot, user_id: int) -> None:
        lang = main.get_lang(user_id)
        root = Path(main.__file__).resolve().parents[1]
        await deliver_mt5_package(
            bot,
            int(user_id),
            ex5_path=root / "assets" / "autotrade" / "NEXUS_AutoTrade.ex5",
            guide_video_path=root / "assets" / "guides" / "NEXUS_AutoTrade_MT5_Guide.mp4",
            admin_ids=main.settings.admin_ids,
            lang=lang,
            attempts=3,
            base_delay_seconds=1.0,
        )

    async def send_autotrade_license(bot, user_id: int, lic) -> None:
        if not main.license_service.has_autotrade(user_id):
            return
        lang = main.get_lang(user_id)
        key = str(lic["license_key"] or "").strip()
        if not key:
            raise RuntimeError("AutoTrade license key was not generated")
        auto_exp = (
            lic["autotrade_expires_at"]
            if "autotrade_expires_at" in lic.keys() and lic["autotrade_expires_at"]
            else lic["expires_at"]
        )
        await bot.send_message(
            int(user_id),
            main.tr(
                lang,
                "🤖 <b>NEXUS AutoTrade فعال شد</b>\n\n"
                f"🔑 License Key:\n<code>{escape(key)}</code>\n"
                f"📅 اعتبار تا: <b>{main.fmt_dt(auto_exp)}</b>\n\n"
                "جزئیات کامل اعتبار همیشه از «🔑 مجوز من» قابل مشاهده است.",
                "🤖 <b>NEXUS AutoTrade activated</b>\n\n"
                f"🔑 License Key:\n<code>{escape(key)}</code>\n"
                f"📅 Valid until: <b>{main.fmt_dt(auto_exp)}</b>\n\n"
                "Full validity details are always available under “🔑 My License”.",
            ),
            parse_mode=ParseMode.HTML,
        )
        try:
            await send_mt5_package(bot, int(user_id))
        except AutoTradeDeliveryError:
            log.exception("AutoTrade package delivery failed after license issuance: user_id=%s", user_id)
            await bot.send_message(
                int(user_id),
                main.tr(
                    lang,
                    "⚠️ لایسنس شما فعال است، اما ارسال فایل نصب/ویدئو کامل نشد. از «دریافت اکسپرت MT5» دوباره تلاش کنید.",
                    "⚠️ Your license is active, but installer/video delivery did not complete. Retry from “Download MT5 EA”.",
                ),
            )
        await main.push_home_to_bottom(bot, int(user_id))

    main._send_mt5_installer_and_help = send_mt5_package
    main.send_autotrade_license = send_autotrade_license


async def _send_mt5_video_guide(main, cb, bot) -> None:
    if not await main.gated(cb, bot):
        return
    lang = main.get_lang(cb.from_user.id)
    await cb.answer()
    local_video = Path(main.__file__).resolve().parents[1] / "assets" / "guides" / "NEXUS_AutoTrade_MT5_Guide.mp4"
    if local_video.is_file():
        from aiogram.types import FSInputFile
        await bot.send_video(
            cb.from_user.id,
            video=FSInputFile(local_video),
            caption=main.tr(
                lang,
                "🎥 راهنمای تصویری نصب و فعال‌سازی NEXUS AutoTrade",
                "🎥 NEXUS AutoTrade installation and activation guide",
            ),
            supports_streaming=True,
            protect_content=True,
        )
    elif main.settings.guide_mt5_video_url:
        await bot.send_message(
            cb.from_user.id,
            main.tr(lang, "راهنمای ویدئویی از لینک رسمی در دسترس است.", "The video guide is available from the official link."),
            reply_markup=main.InlineKeyboardMarkup(inline_keyboard=[[
                main.InlineKeyboardButton(
                    text=main.tr(lang, "▶️ مشاهده کلیپ", "▶️ Watch Video"),
                    url=main.settings.guide_mt5_video_url,
                )
            ]]),
        )
    else:
        await bot.send_message(
            cb.from_user.id,
            main.tr(lang, "⚠️ فایل راهنمای ویدئویی فعلاً در دسترس نیست.", "⚠️ The video guide is temporarily unavailable."),
        )
    await main.push_home_to_bottom(bot, int(cb.from_user.id))


def _register_pricing_handlers(main) -> None:
    async def pricing_settings(cb, bot):
        if not main.is_admin(cb.from_user.id):
            return
        lang = main.get_lang(cb.from_user.id)
        await cb.answer()
        health = main.pricing_service.rate_health()
        manual = health.get("manual_override") or "—"
        last_rate = health.get("last_rate") or "—"
        last_at = health.get("last_rate_at") or "—"
        last_source = health.get("last_rate_source") or "—"
        failures = int(health.get("consecutive_failures") or 0)
        ttl = int(main.db.get_setting("rial_invoice_ttl_minutes", str(main.settings.rial_invoice_ttl_minutes)))
        text = main.tr(
            lang,
            "<b>💱 نرخ مرجع تتر NEXUS / منبع نرخ پرداخت</b>\n\n"
            f"منبع اصلی: <b>{escape(str(health.get('primary_title') or '—'))}</b>\n"
            f"منبع پشتیبان: <b>{escape(str(health.get('secondary_title') or '—'))}</b>\n"
            f"آخرین نرخ معتبر: <b>{escape(str(last_rate))}</b> ریال/USDT\n"
            f"منبع آخرین نرخ: <b>{escape(str(last_source))}</b>\n"
            f"آخرین بروزرسانی: <code>{escape(str(last_at))}</code>\n"
            f"نرخ دستی: <b>{escape(str(manual))}</b>\n"
            f"خطاهای متوالی: <b>{failures}</b>\n"
            f"اعتبار فاکتور ریالی: <b>{ttl} دقیقه</b>\n\n"
            "منبع نرخ را انتخاب کنید یا بروزرسانی فوری انجام دهید.",
            "<b>💱 NEXUS Reference USDT Rate / Payment Rate Source</b>\n\n"
            f"Primary: <b>{escape(str(health.get('primary_title') or '—'))}</b>\n"
            f"Secondary: <b>{escape(str(health.get('secondary_title') or '—'))}</b>\n"
            f"Last valid rate: <b>{escape(str(last_rate))}</b> IRR/USDT\n"
            f"Last source: <b>{escape(str(last_source))}</b>\n"
            f"Last update: <code>{escape(str(last_at))}</code>\n"
            f"Manual override: <b>{escape(str(manual))}</b>\n"
            f"Consecutive failures: <b>{failures}</b>\n"
            f"IRR invoice TTL: <b>{ttl} minutes</b>\n\n"
            "Choose a provider or refresh now.",
        )
        if lang == "fa":
            rows = [
                [("🇮🇷 Nobitex", "pricing_provider:nobitex"), ("🇮🇷 Wallex", "pricing_provider:wallex")],
                [("🌍 International", "pricing_provider:international"), ("🔗 Custom URL", "pricing_provider:custom")],
                [("🔄 بروزرسانی نرخ الآن", "pricing_refresh")],
                [("💱 نرخ دستی", "pricing_rate"), ("🧹 حذف نرخ دستی", "pricing_clear_rate")],
                [("⏱ اعتبار فاکتور", "pricing_ttl"), ("🧮 محاسبه Upgrade", "pricing_proration")],
            ]
        else:
            rows = [
                [("🇮🇷 Nobitex", "pricing_provider:nobitex"), ("🇮🇷 Wallex", "pricing_provider:wallex")],
                [("🌍 International", "pricing_provider:international"), ("🔗 Custom URL", "pricing_provider:custom")],
                [("🔄 Refresh Rate Now", "pricing_refresh")],
                [("💱 Manual Rate", "pricing_rate"), ("🧹 Clear Manual", "pricing_clear_rate")],
                [("⏱ Invoice TTL", "pricing_ttl"), ("🧮 Upgrade Proration", "pricing_proration")],
            ]
        await main.screen(bot, cb.from_user.id, cb.message.chat.id, text, main.kb(rows + main.nav(lang, "admin_group_system")))

    async def pricing_provider(cb, bot, state):
        if not main.is_admin(cb.from_user.id):
            return
        lang = main.get_lang(cb.from_user.id)
        provider = cb.data.split(":", 1)[1].strip().lower()
        if provider == "custom":
            await state.set_state(main.Flow.admin_rate_source)
            await cb.answer()
            await main.screen(
                bot,
                cb.from_user.id,
                cb.message.chat.id,
                main.tr(lang, "URL منبع سفارشی نرخ USDT/IRR را وارد کنید.", "Enter the custom USDT/IRR provider URL."),
                main.kb(main.nav(lang, "pricing_settings")),
            )
            return
        try:
            main.pricing_service.configure_rate_provider(provider)
            main.db.add_audit(cb.from_user.id, "usdt_rate_provider", None, provider)
            await cb.answer(main.tr(lang, "منبع نرخ تغییر کرد ✅", "Rate provider updated ✅"), show_alert=True)
        except Exception as exc:
            await cb.answer(main.tr(lang, f"خطا: {exc}", f"Error: {exc}"), show_alert=True)
            return
        await pricing_settings(cb, bot)

    async def pricing_source_save(message, bot, state):
        if not main.is_admin(message.from_user.id):
            return
        raw = (message.text or "").strip()
        lang = main.get_lang(message.from_user.id)
        await main.clean_user_message(message)
        try:
            main.pricing_service.configure_rate_provider("custom", custom_url=raw)
            main.db.add_audit(message.from_user.id, "usdt_rate_provider", None, "custom")
        except Exception as exc:
            await main.screen(
                bot,
                message.from_user.id,
                message.chat.id,
                main.tr(lang, f"❌ URL نامعتبر است: {escape(str(exc))}", f"❌ Invalid URL: {escape(str(exc))}"),
                main.kb(main.nav(lang, "pricing_settings")),
            )
            return
        await state.clear()
        await main.screen(
            bot,
            message.from_user.id,
            message.chat.id,
            main.tr(lang, "✅ منبع سفارشی نرخ ذخیره شد.", "✅ Custom rate provider saved."),
            main.kb(main.nav(lang, "pricing_settings")),
        )

    async def pricing_refresh(cb, bot):
        if not main.is_admin(cb.from_user.id):
            return
        lang = main.get_lang(cb.from_user.id)
        try:
            quote = await main.pricing_service.refresh_usdt_rial_rate()
            await cb.answer(
                main.tr(lang, f"نرخ بروزرسانی شد: {quote.rate} ✅", f"Rate refreshed: {quote.rate} ✅"),
                show_alert=True,
            )
        except Exception as exc:
            await cb.answer(main.tr(lang, f"بروزرسانی ناموفق: {exc}", f"Refresh failed: {exc}"), show_alert=True)
        await pricing_settings(cb, bot)

    main.router.callback_query.register(pricing_settings, F.data == "pricing_settings")
    main.router.callback_query.register(pricing_provider, F.data.startswith("pricing_provider:"))
    main.router.callback_query.register(pricing_refresh, F.data == "pricing_refresh")
    main.router.message.register(pricing_source_save, main.Flow.admin_rate_source)


def _install_rate_worker(main) -> None:
    original_report_worker = main.report_worker

    async def report_and_rate_worker(bot):
        report_task = asyncio.create_task(original_report_worker(bot))
        rate_task = asyncio.create_task(usdt_rate_worker(bot, main.settings.admin_ids))
        try:
            await asyncio.gather(report_task, rate_task)
        finally:
            report_task.cancel()
            rate_task.cancel()
            await asyncio.gather(report_task, rate_task, return_exceptions=True)

    main.report_worker = report_and_rate_worker


def _install_message_lifecycle(main) -> None:
    async def transient_delete(bot, chat_id: int, message_id: int, delay: int):
        # No read receipts are claimed: guarantee enough deterministic observation time.
        return await delete_after(
            bot,
            chat_id,
            message_id,
            delay_seconds=max(DEFAULT_INFO_TTL_SECONDS, int(delay)),
            reason="autotrade_notification",
        )

    main._delete_transient_notification = transient_delete
    main.screen = lambda bot, user_id, chat_id, text, markup=None: _screen(main, bot, user_id, chat_id, text, markup)


def install(main_module) -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    main = main_module

    # Remove every Telegram exchange route before the router reaches Dispatcher.
    _remove_handlers(
        main.router.callback_query,
        EXCHANGE_CALLBACK_HANDLER_NAMES | REPLACED_CALLBACK_HANDLER_NAMES,
    )
    _remove_handlers(
        main.router.message,
        EXCHANGE_MESSAGE_HANDLER_NAMES | REPLACED_MESSAGE_HANDLER_NAMES,
    )

    # Replace the globally resolved menu/helper references used by legacy handlers.
    main.autotrade_user_menu = lambda lang, mt5_connected=False, **kwargs: _autotrade_user_menu(
        main, lang, mt5_connected=mt5_connected, **kwargs
    )
    main._show_autotrade_home = lambda bot, user_id, chat_id: _show_autotrade_home(main, bot, user_id, chat_id)

    _install_message_lifecycle(main)
    _install_delivery(main)
    _install_rate_worker(main)
    _register_customer_handlers(main)
    _register_guide_handlers(main)
    _register_pricing_handlers(main)

    async def autotrade_video_guide(cb, bot):
        await _send_mt5_video_guide(main, cb, bot)

    main.router.callback_query.register(autotrade_video_guide, F.data == "autotrade_video_guide")

    _INSTALLED = True
    log.info(
        "NEXUS customer UX hardening installed: exchange routes removed, license view centralized, "
        "reliable MT5 delivery enabled, 30s lifecycle enabled, USDT monitor enabled"
    )
