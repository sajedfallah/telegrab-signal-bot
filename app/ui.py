from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from .config import settings
from . import db


def kb(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=text, callback_data=data) for text, data in row] for row in rows
    ])


def language_menu() -> InlineKeyboardMarkup:
    return kb([[('🇮🇷 فارسی', 'lang:fa'), ('🇬🇧 English', 'lang:en')]])


def join_gate(lang: str) -> InlineKeyboardMarkup:
    join = "📢 عضویت در کانال عمومی NEXUS" if lang == "fa" else "📢 Join NEXUS Public Channel"
    check = "✅ بررسی عضویت" if lang == "fa" else "✅ Check Membership"
    lang_button = "🌐 تغییر زبان" if lang == "fa" else "🌐 Change Language"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=join, url=settings.public_channel_url)],
        [InlineKeyboardButton(text=check, callback_data="check_public")],
        [InlineKeyboardButton(text=lang_button, callback_data="change_language")],
    ])


def nav(lang: str, back: str = "main") -> list[list[tuple[str, str]]]:
    if lang == "fa":
        return [[("⬅️ بازگشت", back), ("🏠 منوی اصلی", "main")]]
    return [[("⬅️ Back", back), ("🏠 Main Menu", "main")]]


def main_menu(lang: str, is_admin: bool = False) -> InlineKeyboardMarkup:
    """Primary customer dashboard: compact, task-oriented 2-column grid."""
    if lang == "fa":
        rows = [
            [("📊 سیگنال", "client_signals"), ("💎 خرید اشتراک", "vip")],
            [("👤 حساب من", "account"), ("🎓 راهنما", "guide_hub")],
            [("🛟 پشتیبانی", "support")],
            [("🌐 تغییر زبان", "change_language")],
        ]
        if is_admin:
            rows.append([("🛠 پنل مدیریت", "admin")])
    else:
        rows = [
            [("📊 Signals", "client_signals"), ("💎 Buy Subscription", "vip")],
            [("👤 My Account", "account"), ("🎓 Guide", "guide_hub")],
            [("🛟 Support", "support")],
            [("🌐 Change Language", "change_language")],
        ]
        if is_admin:
            rows.append([("🛠 Admin Panel", "admin")])
    return kb(rows)


def guide_hub_menu(lang: str) -> InlineKeyboardMarkup:
    """Guide entry point; reachable from the main menu only."""
    if lang == "fa":
        rows = [
            [("🎬 معرفی NEXUS", "guide_intro")],
            [("🖥 راهنمای نصب اکسپرت", "guide_mt5")],
        ]
    else:
        rows = [
            [("🎬 About NEXUS", "guide_intro")],
            [("🖥 Expert Installation Guide", "guide_mt5")],
        ]
    rows += nav(lang, "main")
    return kb(rows)


def guide_back_menu(lang: str) -> InlineKeyboardMarkup:
    return kb(nav(lang, "guide_hub"))


def client_signal_menu(lang: str, has_vip: bool, has_autotrade: bool = False) -> InlineKeyboardMarkup:
    if lang == "fa":
        rows = [
            [("🎯 سیگنال عمومی", "public")],
            [(("🔓" if has_vip else "🔒") + " سیگنال VIP", "client_vip_access"),
             (("🔓" if has_autotrade else "🔒") + " سیگنال + AutoTrade", "client_autotrade_access")],
        ]
    else:
        rows = [
            [("🎯 Public Signals", "public")],
            [(("🔓" if has_vip else "🔒") + " VIP Signals", "client_vip_access"),
             (("🔓" if has_autotrade else "🔒") + " Signals + AutoTrade", "client_autotrade_access")],
        ]
    rows += nav(lang, "main")
    return kb(rows)


def autotrade_user_menu(lang: str, *, mt5_connected: bool = False, exchange_connected: bool = False) -> InlineKeyboardMarkup:
    if lang == "fa":
        rows = [
            [("📊 وضعیت معاملات خودکار", "autotrade_status"), ("🖥 معاملات باز", "autotrade_open")],
            [("📜 تاریخچه معاملات", "autotrade_history"), ("📅 گزارش امروز", "autotrade_today")],
            [("🔑 مجوز من", "autotrade_license"), ("📥 دریافت اکسپرت MT5", "autotrade_download_mt5")],
            [("🔄 درخواست تغییر حساب MT5", "autotrade_account_change")],
            [("₿ اتصال صرافی", "autotrade_exchange"), ("🆘 راهنمای AutoTrade", "autotrade_help")],
        ]
    else:
        rows = [
            [("📊 Auto Trade Status", "autotrade_status"), ("🖥 Open Trades", "autotrade_open")],
            [("📜 Trade History", "autotrade_history"), ("📅 Today's Report", "autotrade_today")],
            [("🔑 My License", "autotrade_license"), ("📥 Download MT5 EA", "autotrade_download_mt5")],
            [("🔄 Change MT5 Account", "autotrade_account_change")],
            [("₿ Connect Exchange", "autotrade_exchange"), ("🆘 AutoTrade Help", "autotrade_help")],
        ]
    rows += nav(lang, "main")
    return kb(rows)


def exchange_select_menu(lang: str) -> InlineKeyboardMarkup:
    names = [("Binance", "binance"), ("Bybit", "bybit"), ("LBank", "lbank"), ("KuCoin", "kucoin"), ("OKX", "okx"), ("Gate.io", "gateio"), ("Bitget", "bitget")]
    rows = []
    for i in range(0, len(names), 2):
        row=[]
        for label, code in names[i:i+2]:
            row.append((label, f"exchange_select:{code}"))
        rows.append(row)
    rows += nav(lang, "client_autotrade_access")
    return kb(rows)


def exchange_connected_menu(lang: str) -> InlineKeyboardMarkup:
    if lang == "fa":
        rows=[[('🔄 تست مجدد اتصال', 'exchange_retest')], [('🔌 قطع اتصال صرافی', 'exchange_disconnect')]]
    else:
        rows=[[('🔄 Retest Connection', 'exchange_retest')], [('🔌 Disconnect Exchange', 'exchange_disconnect')]]
    rows += nav(lang, "client_autotrade_access")
    return kb(rows)

def signal_volume_mode_menu(lang: str) -> InlineKeyboardMarkup:
    if lang == "fa":
        rows = [[("⚖️ مدیریت ریسک (%)", "sigvol:RISK"), ("📦 حجم ثابت (لات)", "sigvol:FIXED")]]
    else:
        rows = [[("⚖️ Risk Management (%)", "sigvol:RISK"), ("📦 Fixed Lot", "sigvol:FIXED")]]
    rows += nav(lang, "admin_signals")
    return kb(rows)


def trailing_guide_menu(lang: str) -> InlineKeyboardMarkup:
    rows = [[(f"{code} — {name}", f"trailguide:{code}")] for code, name in TRAILING_PRESETS]
    rows += nav(lang, "admin_signals")
    return kb(rows)


def trailing_guide_detail_menu(lang: str) -> InlineKeyboardMarkup:
    return kb([[(("📚 مدل‌های دیگر" if lang == "fa" else "📚 Other Models"), "trailing_guide")]] + nav(lang, "admin_signals"))


def subscription_service_menu(lang: str, has_vip: bool, has_autotrade: bool) -> InlineKeyboardMarkup:
    """Exactly three purchase products; entitlement state is shown on the next page.

    Labels intentionally stay short and LTR so Telegram never duplicates/reorders
    the price or mixes Persian/English BiDi runs. ``has_vip``/``has_autotrade`` are
    retained for call-site compatibility but do not change the product count.
    """
    rows = [
        [("VIP", "buyservice:VIP")],
        [("AutoTrade", "buyservice:AUTO")],
        [("VIP + AutoTrade", "buyservice:BUNDLE")],
    ]
    return kb(rows + nav(lang, "main"))


def plans_for_service(lang: str, service: str) -> InlineKeyboardMarkup:
    """Render each plan exactly once as ``Service | Duration | Price USDT``."""
    service = service.upper().strip()
    service_label = {"VIP": "VIP", "AUTO": "AutoTrade", "BUNDLE": "VIP + AutoTrade"}.get(service)
    if not service_label:
        return kb(nav(lang, "vip"))
    rows: list[list[tuple[str, str]]] = []
    for code, plan in (db.plan_map(active_only=True) or {}).items():
        vip = bool(plan.get("vip_access", True))
        auto = bool(plan.get("autotrade_access", True))
        ok = ((service == "VIP" and vip and not auto)
              or (service == "AUTO" and auto and not vip)
              or (service == "BUNDLE" and vip and auto))
        if not ok:
            continue
        raw_price = str(plan.get("usdt", plan.get("price_usdt", "0"))).strip()
        try:
            if float(raw_price) <= 0:
                continue
        except (TypeError, ValueError):
            continue
        days = int(plan.get("days") or plan.get("duration_days") or 0)
        duration = {30: "1 Month", 90: "3 Months", 180: "6 Months", 365: "1 Year"}.get(days, f"{days} Days")
        rows.append([(f"{service_label} | {duration} | {raw_price} USDT", f"plan:{code}")])
    return kb(rows + nav(lang, "vip"))


def plans(lang: str) -> InlineKeyboardMarkup:
    rows = []
    catalog = db.plan_map(active_only=True) or settings.plans
    for code, plan in catalog.items():
        title = str(plan.get(lang) or plan.get("en") or code)
        price = str(plan.get("usdt", plan.get("price_usdt", "0"))).strip()
        # Catalog titles may already contain a price. Strip the trailing price/unit
        # before composing the button so the price is rendered exactly once.
        import re
        title = re.sub(r"\s*[—|\-]\s*[0-9]+(?:\.[0-9]+)?\s*USDT\s*$", "", title, flags=re.IGNORECASE)
        rows.append([(f"{title} | {price} USDT", f"plan:{code}")])
    rows += nav(lang, "main")
    return kb(rows)


def plan_options(lang: str, plan_code: str, has_points: bool, renewal_percent: float = 0) -> InlineKeyboardMarkup:
    rows: list[list[tuple[str, str]]] = []
    if lang == "fa":
        if renewal_percent > 0:
            rows.append([(f"🔁 تخفیف تمدید {renewal_percent:g}٪", f"discount:renewal:{plan_code}")])
        rows.append([("💳 ادامه بدون تخفیف", f"discount:none:{plan_code}")])
        rows.append([("🎟 استفاده از کد تخفیف", f"discount:promo:{plan_code}")])
        if has_points:
            rows.append([("⭐ استفاده از NEXUS امتیاز", f"discount:points:{plan_code}")])
    else:
        if renewal_percent > 0:
            rows.append([(f"🔁 {renewal_percent:g}% Renewal Discount", f"discount:renewal:{plan_code}")])
        rows.append([("💳 Continue without discount", f"discount:none:{plan_code}")])
        rows.append([("🎟 Use Promo Code", f"discount:promo:{plan_code}")])
        if has_points:
            rows.append([("⭐ Use NEXUS Points", f"discount:points:{plan_code}")])
    rows += nav(lang, "vip")
    return kb(rows)


def payment_method(lang: str, plan_code: str) -> InlineKeyboardMarkup:
    if lang == "fa":
        rows = [[("💳 پرداخت ریالی", f"method:{plan_code}:irr"), ("₮ پرداخت تتر", f"method:{plan_code}:usdt")]]
    else:
        rows = [[("💳 Pay in IRR", f"method:{plan_code}:irr"), ("₮ Pay with USDT", f"method:{plan_code}:usdt")]]
    rows += nav(lang, "vip")
    return kb(rows)


def payment_actions(lang: str, plan_code: str, method: str) -> InlineKeyboardMarkup:
    text = "📤 ارسال رسید پرداخت" if lang == "fa" else "📤 Send Payment Receipt"
    rows = [[(text, f"receipt:{plan_code}:{method}")]] + nav(lang, "vip")
    return kb(rows)


def admin_payment(payment_id: int, lang: str = "fa") -> InlineKeyboardMarkup:
    if lang == "fa":
        rows = [[("✅ تأیید", f"payok:{payment_id}"), ("❌ رد", f"payno:{payment_id}")]]
    else:
        rows = [[("✅ Approve", f"payok:{payment_id}"), ("❌ Reject", f"payno:{payment_id}")]]
    return kb(rows)


def account_menu(lang: str, has_license: bool, has_autotrade: bool = False) -> InlineKeyboardMarkup:
    """Account hub. Payments and referrals intentionally live under this menu."""
    if lang == "fa":
        rows = [
            [("📊 وضعیت VIP", "client_vip_access"), ("🤖 وضعیت AutoTrade", "client_autotrade_access")],
            [("💳 پرداخت‌های من", "my_payments"), ("🎁 دعوت دوستان", "referral")],
            [("💎 خرید / تمدید اشتراک", "vip")],
        ]
        if has_license:
            rows.append([("🔐 لینک دسترسی VIP", "new_vip_link")])
        rows.append([("🌐 تغییر زبان", "change_language")])
    else:
        rows = [
            [("📊 VIP Status", "client_vip_access"), ("🤖 AutoTrade Status", "client_autotrade_access")],
            [("💳 My Payments", "my_payments"), ("🎁 Invite Friends", "referral")],
            [("💎 Buy / Renew Subscription", "vip")],
        ]
        if has_license:
            rows.append([("🔐 VIP Access Link", "new_vip_link")])
        rows.append([("🌐 Change Language", "change_language")])
    rows += nav(lang, "main")
    return kb(rows)


def referral_menu(lang: str, share_url: str) -> InlineKeyboardMarkup:
    share_text = "دعوت به NEXUS" if lang == "fa" else "Join NEXUS"
    if lang == "fa":
        rows = [
            [("📤 اشتراک‌گذاری لینک دعوت", f"noop")],
            [("🏆 رتبه‌بندی دعوت‌ها", "ref_leaderboard")],
        ]
        # The share button is a URL button; replace the temporary tuple below.
        markup = [
            [InlineKeyboardButton(text="📤 اشتراک‌گذاری لینک دعوت", url=f"https://t.me/share/url?url={share_url}&text={share_text}")],
            [InlineKeyboardButton(text="🏆 رتبه‌بندی دعوت‌ها", callback_data="ref_leaderboard")],
            [InlineKeyboardButton(text="⬅️ حساب من", callback_data="account"), InlineKeyboardButton(text="🏠 منوی اصلی", callback_data="main")],
        ]
    else:
        markup = [
            [InlineKeyboardButton(text="📤 Share Referral Link", url=f"https://t.me/share/url?url={share_url}&text={share_text}")],
            [InlineKeyboardButton(text="🏆 Referral Leaderboard", callback_data="ref_leaderboard")],
            [InlineKeyboardButton(text="⬅️ My Account", callback_data="account"), InlineKeyboardButton(text="🏠 Main Menu", callback_data="main")],
        ]
    return InlineKeyboardMarkup(inline_keyboard=markup)


def my_payments_menu(lang: str) -> InlineKeyboardMarkup:
    if lang == "fa":
        rows = [
            [("🟢 موفق", "my_payments:approved"), ("🟡 در انتظار", "my_payments:pending")],
            [("🔴 ناموفق", "my_payments:failed"), ("📜 همه پرداخت‌ها", "my_payments:all")],
        ]
    else:
        rows = [
            [("🟢 Successful", "my_payments:approved"), ("🟡 Pending", "my_payments:pending")],
            [("🔴 Failed", "my_payments:failed"), ("📜 All Payments", "my_payments:all")],
        ]
    rows += nav(lang, "account")
    return kb(rows)


def admin_menu(lang: str) -> InlineKeyboardMarkup:
    if lang == "fa":
        rows = [
            [("👥 کاربران و اشتراک‌ها", "admin_group_users"), ("💳 مالی و پرداخت", "admin_group_finance")],
            [("🎁 رفرال و وفاداری", "admin_group_rewards"), ("📈 مرکز سیگنال", "admin_signals")],
            [("📣 کمپین و پیام‌رسانی", "admin_group_marketing"), ("📊 گزارشات", "admin_group_reports")],
            [("⚙️ تنظیمات سیستم", "admin_group_system")],
            [("🌐 تغییر زبان", "change_language"), ("🏠 منوی اصلی", "main")],
        ]
    else:
        rows = [
            [("👥 Users & Subscriptions", "admin_group_users"), ("💳 Finance & Payments", "admin_group_finance")],
            [("🎁 Referral & Loyalty", "admin_group_rewards"), ("📈 Signal Center", "admin_signals")],
            [("📣 Campaigns & Messaging", "admin_group_marketing"), ("📊 Reports", "admin_group_reports")],
            [("⚙️ System Settings", "admin_group_system")],
            [("🌐 Change Language", "change_language"), ("🏠 Main Menu", "main")],
        ]
    return kb(rows)


def admin_users_group(lang: str) -> InlineKeyboardMarkup:
    if lang == "fa":
        rows = [
            [("👥 کاربران", "admin_users"), ("💎 اشتراک‌ها", "admin_subs")],
            [("🏅 سطح کاربران", "admin_levels"), ("⏳ تمدید و انقضا", "admin_retention")],
        ]
    else:
        rows = [
            [("👥 Users", "admin_users"), ("💎 Subscriptions", "admin_subs")],
            [("🏅 User Levels", "admin_levels"), ("⏳ Renewal & Expiry", "admin_retention")],
        ]
    rows += nav(lang, "admin")
    return kb(rows)


def admin_finance_group(lang: str) -> InlineKeyboardMarkup:
    if lang == "fa":
        rows = [
            [("🧾 پرداخت‌های در انتظار", "admin_pending"), ("🎟 پلن‌ها و قیمت‌ها", "admin_plans")],
            [("🏷 تخفیف‌ها", "admin_discounts"), ("💱 نرخ تتر/ریال", "pricing_settings")],
        ]
    else:
        rows = [
            [("🧾 Pending Payments", "admin_pending"), ("🎟 Plans & Pricing", "admin_plans")],
            [("🏷 Discounts", "admin_discounts"), ("💱 USDT/IRR Rate", "pricing_settings")],
        ]
    rows += nav(lang, "admin")
    return kb(rows)


def admin_rewards_group(lang: str) -> InlineKeyboardMarkup:
    if lang == "fa":
        rows = [
            [("🎁 تنظیمات رفرال و امتیاز", "admin_rewards")],
            [("🏆 رتبه‌بندی دعوت‌ها", "ref_leaderboard")],
        ]
    else:
        rows = [
            [("🎁 Referral & Points Settings", "admin_rewards")],
            [("🏆 Referral Leaderboard", "ref_leaderboard")],
        ]
    rows += nav(lang, "admin")
    return kb(rows)


def admin_content_group(lang: str) -> InlineKeyboardMarkup:
    if lang == "fa":
        rows = [
            [("📡 وضعیت کانال‌ها", "admin_channels_status"), ("🤖 معاملات خودکار", "admin_autotrade")],
        ]
    else:
        rows = [
            [("📡 Channel Status", "admin_channels_status"), ("🤖 Auto Trade", "admin_autotrade")],
        ]
    rows += nav(lang, "admin")
    return kb(rows)


def admin_marketing_group(lang: str) -> InlineKeyboardMarkup:
    if lang == "fa":
        rows = [
            [("🎯 کمپین‌ها", "admin_campaigns"), ("📣 ارسال پیام", "admin_broadcast")],
            [("🏷 تخفیف‌های مناسبتی", "admin_discounts")],
        ]
    else:
        rows = [
            [("🎯 Campaigns", "admin_campaigns"), ("📣 Broadcast", "admin_broadcast")],
            [("🏷 Promotional Discounts", "admin_discounts")],
        ]
    rows += nav(lang, "admin")
    return kb(rows)


def admin_reports_group(lang: str) -> InlineKeyboardMarkup:
    if lang == "fa":
        rows = [
            [("📅 گزارش امروز", "report_daily_now"), ("🗓 گزارش هفتگی", "report_weekly_now")],
            [("📊 آمار کلی", "admin_stats"), ("📈 داشبورد مشتری", "admin_dashboard")],
            [("🧾 گزارش رویدادها", "admin_audit"), ("📈 آمار سیگنال", "signal_stats")],
        ]
    else:
        rows = [
            [("📅 Today's Report", "report_daily_now"), ("🗓 Weekly Report", "report_weekly_now")],
            [("📊 General Stats", "admin_stats"), ("📈 CRM Dashboard", "admin_dashboard")],
            [("🧾 Audit Log", "admin_audit"), ("📈 Signal Stats", "signal_stats")],
        ]
    rows += nav(lang, "admin")
    return kb(rows)


def admin_system_group(lang: str) -> InlineKeyboardMarkup:
    if lang == "fa":
        rows = [
            [("💾 بکاپ دیتابیس", "admin_backup"), ("💱 نرخ تتر/ریال", "pricing_settings")],
            [("🚀 مدیریت مشتری و تمدید", "admin_crm"), ("🌐 تغییر زبان", "change_language")],
        ]
    else:
        rows = [
            [("💾 Database Backup", "admin_backup"), ("💱 USDT/IRR Rate", "pricing_settings")],
            [("🚀 CRM & Retention", "admin_crm"), ("🌐 Change Language", "change_language")],
        ]
    rows += nav(lang, "admin")
    return kb(rows)


def signal_center_menu(lang: str) -> InlineKeyboardMarkup:
    """Read-only MT5 signal reporting for admins."""
    if lang == "fa":
        rows = [
            [("📋 سیگنال‌های فعال", "signal_active"), ("🏁 نتایج بسته‌شده", "signal_closed")],
            [("🔄 همگام‌سازی زنده", "signal_refresh"), ("📊 آمار سیگنال", "signal_stats")],
            [("🧠 داشبورد تحلیلی", "admin_dashboard")],
        ]
    else:
        rows = [
            [("📋 Active Signals", "signal_active"), ("🏁 Closed Results", "signal_closed")],
            [("🔄 Live Sync", "signal_refresh"), ("📊 Signal Stats", "signal_stats")],
            [("🧠 Analytics Dashboard", "signal_analytics")],
        ]
    rows += nav(lang, "admin")
    return kb(rows)


def signal_readonly_menu(lang: str) -> InlineKeyboardMarkup:
    return kb(nav(lang, "signal_active"))


def signal_market_menu(lang: str) -> InlineKeyboardMarkup:
    rows = [[("🌐 فارکس", "sigmarket:FOREX"), ("🪙 رمزارز", "sigmarket:CRYPTO")]]
    rows += nav(lang, "admin_signals")
    return kb(rows)


def signal_symbol_menu(lang: str, market: str) -> InlineKeyboardMarkup:
    if market == "FOREX":
        symbols = ["XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "DOWJONES", "NASDAQ"]
    else:
        symbols = ["BTCUSD", "SOLUSD", "ETHUSD", "BNBUSD"]
    rows: list[list[tuple[str, str]]] = []
    for i in range(0, len(symbols), 2):
        rows.append([(sym, f"sigsymbol:{sym}") for sym in symbols[i:i+2]])
    rows.append([("✍️ ورود دستی" if lang == "fa" else "✍️ Manual Symbol", "sigsymbol:MANUAL")])
    rows += nav(lang, "admin_signals")
    return kb(rows)


TRAILING_PRESETS = [
    ("NEXUS_TRAIL_01", "Safe Scalping"),
    ("NEXUS_TRAIL_02", "Step Profit Lock"),
    ("NEXUS_TRAIL_03", "Dynamic ATR"),
    ("NEXUS_TRAIL_04", "Market Structure"),
    ("NEXUS_TRAIL_05", "VIP Runner"),
    ("NEXUS_TRAIL_06", "Fast Scalping"),
    ("NEXUS_TRAIL_07", "NEXUS Smart Hybrid"),
]


def signal_trailing_preset_menu(lang: str) -> InlineKeyboardMarkup:
    fa_names = {"NEXUS_TRAIL_01":"اسکالپینگ محافظه‌کارانه","NEXUS_TRAIL_02":"قفل مرحله‌ای سود","NEXUS_TRAIL_03":"ATR پویا","NEXUS_TRAIL_04":"ساختار بازار","NEXUS_TRAIL_05":"دونده وی‌آی‌پی","NEXUS_TRAIL_06":"اسکالپینگ سریع","NEXUS_TRAIL_07":"هیبرید هوشمند NEXUS"}
    rows = [[(f"{code} — {fa_names.get(code, name) if lang == 'fa' else name}", f"sigtrail:{code}")] for code, name in TRAILING_PRESETS]
    rows += nav(lang, "admin_signals")
    return kb(rows)


def signal_direction_menu(lang: str, market: str) -> InlineKeyboardMarkup:
    # Market selection is reporting-only. Execution always uses the same
    # BUY/SELL direction contract for Forex, Gold, indices and crypto symbols.
    rows = [[("🟢 خرید", "sigdir:BUY"), ("🔴 فروش", "sigdir:SELL")]] if lang == "fa" else [
        [("🟢 BUY", "sigdir:BUY"), ("🔴 SELL", "sigdir:SELL")]
    ]
    rows += nav(lang, "admin_signals")
    return kb(rows)


def signal_timeframe_menu(lang: str) -> InlineKeyboardMarkup:
    labels = ["M1", "M3", "M5", "M15", "M30", "H1", "H4", "D1", "W1"]
    rows = []
    for i in range(0, len(labels), 3):
        rows.append([(label, f"sigtf:{label}") for label in labels[i:i+3]])
    rows += nav(lang, "admin_signals")
    return kb(rows)


def signal_order_type_menu(lang: str) -> InlineKeyboardMarkup:
    if lang == "fa":
        rows = [
            [("⚡ ورود لحظه‌ای", "sigorder:MARKET")],
            [("🟠 لیمیت خرید", "sigorder:BUY_LIMIT"), ("🔴 لیمیت فروش", "sigorder:SELL_LIMIT")], # sigorder:LIMIT legacy alias

            [("🔵 استاپ خرید", "sigorder:BUY_STOP"), ("🟣 استاپ فروش", "sigorder:SELL_STOP")],
            [("🟣 استاپ‌لیمیت خرید", "sigorder:BUY_STOP_LIMIT"), ("🟪 استاپ‌لیمیت فروش", "sigorder:SELL_STOP_LIMIT")],
        ]
    else:
        rows = [
            [("⚡ Market Entry", "sigorder:MARKET")],
            [("🟠 Buy Limit", "sigorder:BUY_LIMIT"), ("🔴 Sell Limit", "sigorder:SELL_LIMIT")],
            [("🔵 Buy Stop", "sigorder:BUY_STOP"), ("🟣 Sell Stop", "sigorder:SELL_STOP")],
            [("🟣 Buy Stop Limit", "sigorder:BUY_STOP_LIMIT"), ("🟪 Sell Stop Limit", "sigorder:SELL_STOP_LIMIT")],
        ]
    rows += nav(lang, "admin_signals")
    return kb(rows)


def signal_destination_menu(lang: str) -> InlineKeyboardMarkup:
    if lang == "fa":
        rows = [[("🆓 کانال رایگان", "sigdest:FREE")], [("💎 کانال وی‌آی‌پی", "sigdest:VIP")], [("🆓 + 💎 هر دو", "sigdest:BOTH")]]
    else:
        rows = [[("🆓 Free Channel", "sigdest:FREE")], [("💎 VIP Channel", "sigdest:VIP")], [("🆓 + 💎 Both", "sigdest:BOTH")]]
    rows += nav(lang, "admin_signals")
    return kb(rows)


def signal_confirm_menu(lang: str) -> InlineKeyboardMarkup:
    return kb([[ ("✅ تأیید و انتشار" if lang=="fa" else "✅ Confirm & Publish", "sigpublish"),
                 ("❌ لغو" if lang=="fa" else "❌ Cancel", "admin_signals") ]])


def signal_manage_menu(signal_id: int, lang: str) -> InlineKeyboardMarkup:
    """Compatibility name: Telegram signal details are read-only in v0.6.0."""
    return signal_readonly_menu(lang)


def admin_user_actions(target_id: int, lang: str) -> InlineKeyboardMarkup:
    if lang == "fa":
        rows = [
            [("➕ ۳۰ روز اعتبار", f"admextend:{target_id}:30"), ("🔐 لینک وی‌آی‌پی", f"admlink:{target_id}")],
            [("⭐ +100 امتیاز", f"admpoints:{target_id}:100"), ("🚫 لغو وی‌آی‌پی", f"admcancel:{target_id}")],
            [("🎁 Trial سه‌روزه", f"admtrial:{target_id}:3")],
        ]
    else:
        rows = [
            [("➕ Add 30 Days", f"admextend:{target_id}:30"), ("🔐 VIP Link", f"admlink:{target_id}")],
            [("⭐ +100 Points", f"admpoints:{target_id}:100"), ("🚫 Cancel VIP", f"admcancel:{target_id}")],
            [("🎁 3-Day Trial", f"admtrial:{target_id}:3")],
        ]
    rows += nav(lang, "admin_users")
    return kb(rows)


def admin_plan_list_menu(lang: str) -> InlineKeyboardMarkup:
    rows: list[list[tuple[str, str]]] = []
    for p in db.list_plans(active_only=False):
        status = "✅" if p["active"] else "⛔"
        rows.append([(f"{status} {p['duration_days'] or p['days']}d | {p['code']} | {p['price_usdt'] or p['usdt_price']} USDT | Setup {p['setup_fee_usdt'] or 0}", f"planadm:{p['code']}")])
    rows.append([("➕ تعریف پلن جدید" if lang == "fa" else "➕ New Plan", "planadm:new")])
    rows += nav(lang, "admin_group_finance")
    return kb(rows)


def admin_plan_edit_menu(lang: str, code: str, active: bool) -> InlineKeyboardMarkup:
    toggle = "⛔ غیرفعال کردن" if active and lang == "fa" else "✅ فعال کردن" if lang == "fa" else "⛔ غیرفعال کردن" if active else "✅ فعال کردن"
    return kb([
        [("₮ تغییر قیمت تتر" if lang == "fa" else "₮ Edit USDT Price", f"planedit:usdt:{code}")],
        [("⚙️ تغییر هزینه راه‌اندازی" if lang == "fa" else "⚙️ Edit Setup Fee", f"planedit:setup:{code}")],
        [("🔐 دسترسی و تمدید" if lang == "fa" else "🔐 Access & Renewal", f"planaccess:{code}")],
        [(toggle, f"plantoggle:{code}")],
        *nav(lang, "admin_plans"),
    ])


def discounts_menu(lang: str) -> InlineKeyboardMarkup:
    if lang == "fa":
        rows = [[("➕ ساخت تخفیف جدید", "discount_create")], [("📋 تخفیف‌های فعال", "discount_list")]]
    else:
        rows = [[("➕ Create Discount", "discount_create")], [("📋 Active Discounts", "discount_list")]]
    rows += nav(lang, "admin")
    return kb(rows)


def reward_settings_menu(lang: str) -> InlineKeyboardMarkup:
    if lang == "fa":
        rows = [
            [("🎁 تغییر پاداش هر دعوت", "reward_set_ref")],
            [("📐 تغییر نرخ امتیاز/تخفیف", "reward_set_rate")],
            [("🛡 تغییر سقف تخفیف امتیازی", "reward_set_cap")],
        ]
    else:
        rows = [
            [("🎁 Set Referral Reward", "reward_set_ref")],
            [("📐 Set Points/Discount Rate", "reward_set_rate")],
            [("🛡 Set Points Discount Cap", "reward_set_cap")],
        ]
    rows += nav(lang, "admin")
    return kb(rows)


def campaign_menu(lang: str) -> InlineKeyboardMarkup:
    if lang == "fa":
        rows = [[("➕ ساخت کمپین", "campaign_create")], [("📋 کمپین‌های فعال", "campaign_list")]]
    else:
        rows = [[("➕ Create Campaign", "campaign_create")], [("📋 Active Campaigns", "campaign_list")]]
    rows += nav(lang, "admin")
    return kb(rows)


def campaign_plan_menu(lang: str) -> InlineKeyboardMarkup:
    labels = [("همه پلن‌ها" if lang == "fa" else "All Plans", "all")]
    for p in db.list_plans(active_only=True):
        labels.append((f"{p['days']}d", str(p['code'])))
    rows=[]
    for i in range(0,len(labels),2):
        rows.append([(t,f"campaign_plan:{v}") for t,v in labels[i:i+2]])
    return kb(rows + nav(lang, "admin_campaigns"))


def campaign_audience_menu(lang: str) -> InlineKeyboardMarkup:
    if lang == "fa":
        rows=[[ ("همه کاربران","campaign_aud:all"), ("بدون وی‌آی‌پی","campaign_aud:nonvip")],[("وی‌آی‌پی فعال","campaign_aud:vip"),("منقضی‌شده","campaign_aud:expired")]]
    else:
        rows=[[ ("All Users","campaign_aud:all"), ("No VIP","campaign_aud:nonvip")],[("Active VIP","campaign_aud:vip"),("Expired","campaign_aud:expired")]]
    return kb(rows + nav(lang, "admin_campaigns"))


def broadcast_target_menu(lang: str) -> InlineKeyboardMarkup:
    if lang == "fa":
        rows=[[ ("👥 همه","broadcast_target:all"), ("💎 وی‌آی‌پی فعال","broadcast_target:vip")],[("🆓 بدون وی‌آی‌پی","broadcast_target:nonvip"),("⌛ منقضی‌شده","broadcast_target:expired")],[("⭐ امتیاز بالا","broadcast_target:highpoints")]]
    else:
        rows=[[ ("👥 All","broadcast_target:all"), ("💎 Active VIP","broadcast_target:vip")],[("🆓 No VIP","broadcast_target:nonvip"),("⌛ Expired","broadcast_target:expired")],[("⭐ High Points","broadcast_target:highpoints")]]
    return kb(rows + nav(lang, "admin"))


def broadcast_confirm_menu(lang: str) -> InlineKeyboardMarkup:
    return kb([[ ("✅ تأیید ارسال" if lang=="fa" else "✅ Confirm Send", "broadcast_confirm"), ("❌ لغو" if lang=="fa" else "❌ Cancel", "admin") ]])


# ---- v5 UI ----
def autotrade_waitlist_menu(lang: str, joined: bool) -> InlineKeyboardMarkup:
    if joined:
        label = "✅ عضو لیست انتظار هستید" if lang == "fa" else "✅ You are on the waitlist"
        action = "🔕 خروج از لیست انتظار" if lang == "fa" else "🔕 Leave Waitlist"
        rows = [[(label, "noop")], [(action, "autotrade_waitlist_leave")]]
    else:
        action = "🔔 من را هنگام انتشار مطلع کن" if lang == "fa" else "🔔 Notify Me at Launch"
        rows = [[(action, "autotrade_waitlist_join")]]
    rows += nav(lang, "main")
    return kb(rows)


def admin_crm_menu(lang: str) -> InlineKeyboardMarkup:
    if lang == "fa":
        rows = [
            [("📈 داشبورد مدیریت مشتری", "admin_dashboard")],
            [("⏳ تمدید و انقضا", "admin_retention"), ("🎁 دوره آزمایشی وی‌آی‌پی" if lang=="fa" else "🎁 VIP Trial", "admin_users")],
            [("🏅 سطح کاربران", "admin_levels"), ("🤖 لیست انتظار" if lang=="fa" else "🤖 Waiting List", "admin_autotrade")],
            [("🧾 گزارش رویدادها" if lang=="fa" else "🧾 Audit Log", "admin_audit"), ("💾 بکاپ", "admin_backup")],
        ]
    else:
        rows = [
            [("📈 CRM Dashboard", "admin_dashboard")],
            [("⏳ Renewal & Expiry", "admin_retention"), ("🎁 VIP Trial", "admin_users")],
            [("🏅 User Levels", "admin_levels"), ("🤖 لیست انتظار" if lang=="fa" else "🤖 Waiting List", "admin_autotrade")],
            [("🧾 گزارش رویدادها" if lang=="fa" else "🧾 Audit Log", "admin_audit"), ("💾 Backup", "admin_backup")],
        ]
    rows += nav(lang, "admin")
    return kb(rows)
