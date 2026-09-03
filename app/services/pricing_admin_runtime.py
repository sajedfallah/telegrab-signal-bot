from __future__ import annotations

from html import escape

from aiogram import F


_HANDLER_NAMES = {"pricing_settings", "pricing_provider", "pricing_refresh"}
_MESSAGE_NAMES = {"pricing_source_save"}


def _remove_handlers(observer, names: set[str]) -> None:
    observer.handlers[:] = [
        handler
        for handler in observer.handlers
        if getattr(handler.callback, "__name__", "") not in names
    ]


async def _show(main, cb, bot) -> None:
    lang = main.get_lang(cb.from_user.id)
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

    await main.screen(
        bot,
        cb.from_user.id,
        cb.message.chat.id,
        text,
        main.kb(rows + main.nav(lang, "admin_group_system")),
    )


def install(main) -> None:
    """Install one-answer-per-callback pricing admin routes."""
    _remove_handlers(main.router.callback_query, _HANDLER_NAMES)
    _remove_handlers(main.router.message, _MESSAGE_NAMES)

    async def pricing_settings(cb, bot):
        if not main.is_admin(cb.from_user.id):
            return
        await cb.answer()
        await _show(main, cb, bot)

    async def pricing_provider(cb, bot, state):
        if not main.is_admin(cb.from_user.id):
            return
        lang = main.get_lang(cb.from_user.id)
        provider = cb.data.split(":", 1)[1].strip().lower()

        if provider == "custom":
            await cb.answer()
            await state.set_state(main.Flow.admin_rate_source)
            await main.screen(
                bot,
                cb.from_user.id,
                cb.message.chat.id,
                main.tr(
                    lang,
                    "URL منبع سفارشی نرخ USDT/IRR را وارد کنید.",
                    "Enter the custom USDT/IRR provider URL.",
                ),
                main.kb(main.nav(lang, "pricing_settings")),
            )
            return

        try:
            main.pricing_service.configure_rate_provider(provider)
            main.db.add_audit(cb.from_user.id, "usdt_rate_provider", None, provider)
        except Exception as exc:
            await cb.answer(
                main.tr(lang, f"خطا: {exc}", f"Error: {exc}"),
                show_alert=True,
            )
            return

        await cb.answer(
            main.tr(lang, "منبع نرخ تغییر کرد ✅", "Rate provider updated ✅"),
            show_alert=True,
        )
        await _show(main, cb, bot)

    async def pricing_refresh(cb, bot):
        if not main.is_admin(cb.from_user.id):
            return
        lang = main.get_lang(cb.from_user.id)
        try:
            quote = await main.pricing_service.refresh_usdt_rial_rate()
        except Exception as exc:
            await cb.answer(
                main.tr(lang, f"بروزرسانی ناموفق: {exc}", f"Refresh failed: {exc}"),
                show_alert=True,
            )
            await _show(main, cb, bot)
            return

        await cb.answer(
            main.tr(lang, f"نرخ بروزرسانی شد: {quote.rate} ✅", f"Rate refreshed: {quote.rate} ✅"),
            show_alert=True,
        )
        await _show(main, cb, bot)

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
                main.tr(
                    lang,
                    f"❌ URL نامعتبر است: {escape(str(exc))}",
                    f"❌ Invalid URL: {escape(str(exc))}",
                ),
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

    main.router.callback_query.register(pricing_settings, F.data == "pricing_settings")
    main.router.callback_query.register(pricing_provider, F.data.startswith("pricing_provider:"))
    main.router.callback_query.register(pricing_refresh, F.data == "pricing_refresh")
    main.router.message.register(pricing_source_save, main.Flow.admin_rate_source)
