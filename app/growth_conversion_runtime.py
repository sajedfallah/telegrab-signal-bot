from __future__ import annotations

"""Growth, conversion and retention runtime for the approved NEXUS bot.

Production goals implemented here:
- verified referral milestone: 3 successful referrals -> 7 days VIP;
- scalable ambassador ladder (3/10/25 verified referrals);
- smart first-run onboarding by user intent;
- one-time VIP-only trial (AutoTrade is never trial-enabled);
- lifecycle/lead scoring and an admin conversion dashboard;
- low-frequency, deduplicated abandoned-checkout/renewal/reactivation nudges.
"""

import asyncio
from datetime import datetime, timezone, timedelta
from html import escape

from aiogram import F
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from . import db

TRIAL_DAYS_DEFAULT = 3
REFERRAL_MILESTONES: tuple[tuple[int, int, str], ...] = (
    (3, 7, "BRONZE"),
    (10, 15, "SILVER"),
    (25, 30, "GOLD"),
)

_INSTALLED = False
_TASKS: set[asyncio.Task] = set()


def ensure_schema() -> None:
    with db.conn() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS growth_user_state (
                telegram_id INTEGER PRIMARY KEY,
                intent TEXT,
                onboarding_completed INTEGER NOT NULL DEFAULT 0,
                lead_score INTEGER NOT NULL DEFAULT 0,
                lifecycle_stage TEXT NOT NULL DEFAULT 'NEW',
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
            );

            CREATE TABLE IF NOT EXISTS growth_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                value TEXT,
                score_delta INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
            );
            CREATE INDEX IF NOT EXISTS idx_growth_events_user_time
                ON growth_events(telegram_id, created_at);

            CREATE TABLE IF NOT EXISTS growth_referral_milestones (
                referrer_id INTEGER NOT NULL,
                milestone INTEGER NOT NULL,
                reward_days INTEGER NOT NULL,
                tier TEXT NOT NULL,
                awarded_at TEXT NOT NULL,
                PRIMARY KEY(referrer_id, milestone),
                FOREIGN KEY (referrer_id) REFERENCES users(telegram_id)
            );

            CREATE TABLE IF NOT EXISTS growth_message_log (
                telegram_id INTEGER NOT NULL,
                message_key TEXT NOT NULL,
                message_type TEXT NOT NULL,
                sent_at TEXT NOT NULL,
                PRIMARY KEY(telegram_id, message_key),
                FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
            );
            """
        )


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _touch_state(telegram_id: int) -> dict:
    ensure_schema()
    now = _now().isoformat()
    with db.conn() as con:
        con.execute(
            """
            INSERT OR IGNORE INTO growth_user_state(
                telegram_id,intent,onboarding_completed,lead_score,lifecycle_stage,first_seen_at,last_seen_at
            ) VALUES(?,NULL,0,0,'NEW',?,?)
            """,
            (int(telegram_id), now, now),
        )
        con.execute(
            "UPDATE growth_user_state SET last_seen_at=? WHERE telegram_id=?",
            (now, int(telegram_id)),
        )
        row = con.execute(
            "SELECT * FROM growth_user_state WHERE telegram_id=?", (int(telegram_id),)
        ).fetchone()
    return dict(row) if row else {}


def record_event(telegram_id: int, event_type: str, *, value: str | None = None, score: int = 0) -> None:
    _touch_state(int(telegram_id))
    now = _now().isoformat()
    with db.conn() as con:
        con.execute(
            "INSERT INTO growth_events(telegram_id,event_type,value,score_delta,created_at) VALUES(?,?,?,?,?)",
            (int(telegram_id), str(event_type), value, int(score), now),
        )
        if score:
            con.execute(
                "UPDATE growth_user_state SET lead_score=MAX(0,lead_score+?),last_seen_at=? WHERE telegram_id=?",
                (int(score), now, int(telegram_id)),
            )


def _set_intent(telegram_id: int, intent: str) -> None:
    _touch_state(int(telegram_id))
    with db.conn() as con:
        con.execute(
            "UPDATE growth_user_state SET intent=?,lifecycle_stage='INTERESTED',last_seen_at=? WHERE telegram_id=?",
            (str(intent).upper(), _now().isoformat(), int(telegram_id)),
        )
    record_event(int(telegram_id), "ONBOARDING_INTENT", value=str(intent).upper(), score=10)


def _complete_onboarding(telegram_id: int, stage: str = "ACTIVATED") -> None:
    _touch_state(int(telegram_id))
    with db.conn() as con:
        con.execute(
            "UPDATE growth_user_state SET onboarding_completed=1,lifecycle_stage=?,last_seen_at=? WHERE telegram_id=?",
            (str(stage), _now().isoformat(), int(telegram_id)),
        )


def _has_active_access(telegram_id: int) -> bool:
    now = _now().isoformat()
    with db.conn() as con:
        row = con.execute(
            "SELECT 1 FROM licenses WHERE telegram_id=? AND status='active' AND expires_at>? LIMIT 1",
            (int(telegram_id), now),
        ).fetchone()
    return row is not None


def _has_approved_purchase(telegram_id: int) -> bool:
    with db.conn() as con:
        row = con.execute(
            "SELECT 1 FROM payments WHERE telegram_id=? AND status='approved' LIMIT 1",
            (int(telegram_id),),
        ).fetchone()
    return row is not None


def should_show_onboarding(telegram_id: int, *, is_admin: bool = False) -> bool:
    if is_admin:
        return False
    state = _touch_state(int(telegram_id))
    if bool(state.get("onboarding_completed")):
        return False
    if _has_active_access(int(telegram_id)) or _has_approved_purchase(int(telegram_id)):
        _complete_onboarding(int(telegram_id), "CUSTOMER")
        return False
    return True


def referral_tier_for_count(successful: int) -> str:
    tier = "STARTER"
    for milestone, _days, name in REFERRAL_MILESTONES:
        if int(successful) >= milestone:
            tier = name
    return tier


def pending_referral_milestones(successful: int, awarded: set[int]) -> list[tuple[int, int, str]]:
    return [item for item in REFERRAL_MILESTONES if successful >= item[0] and item[0] not in awarded]


def _parse_dt(value: object) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _grant_vip_days_preserving_autotrade(telegram_id: int, days: int, *, source: str, granted_by: int | None) -> None:
    """Extend VIP without rotating an existing AutoTrade license key."""
    now = _now()
    active = None
    with db.conn() as con:
        active = con.execute(
            """
            SELECT * FROM licenses
            WHERE telegram_id=? AND status='active' AND expires_at>?
            ORDER BY id DESC LIMIT 1
            """,
            (int(telegram_id), now.isoformat()),
        ).fetchone()
        if active:
            vip_current = _parse_dt(active["vip_expires_at"])
            if vip_current is None and bool(active["vip_access"]):
                vip_current = _parse_dt(active["expires_at"])
            base = vip_current if vip_current and vip_current > now else now
            vip_new = base + timedelta(days=int(days))
            overall_candidates = [vip_new, _parse_dt(active["expires_at"]), _parse_dt(active["autotrade_expires_at"])]
            overall = max(dt for dt in overall_candidates if dt is not None)
            con.execute(
                """
                UPDATE licenses
                SET vip_access=1,vip_expires_at=?,expires_at=?,status='active'
                WHERE id=?
                """,
                (vip_new.isoformat(), overall.isoformat(), int(active["id"])),
            )
            return

    # No active entitlement exists; use the canonical entitlement creator.
    db.create_or_extend_license(
        int(telegram_id),
        None,
        int(days),
        source=str(source),
        granted_by=granted_by,
        vip_access=True,
        autotrade_access=False,
    )


def _award_referral_milestones(referrer_id: int, *, granted_by: int | None) -> list[tuple[int, int, str]]:
    ensure_schema()
    successful = int(db.referral_stats(int(referrer_id))["successful"])
    with db.conn() as con:
        awarded = {
            int(row[0])
            for row in con.execute(
                "SELECT milestone FROM growth_referral_milestones WHERE referrer_id=?",
                (int(referrer_id),),
            ).fetchall()
        }
    newly_awarded: list[tuple[int, int, str]] = []
    for milestone, days, tier in pending_referral_milestones(successful, awarded):
        _grant_vip_days_preserving_autotrade(
            int(referrer_id), days, source=f"referral_{tier.lower()}", granted_by=granted_by
        )
        with db.conn() as con:
            con.execute(
                """
                INSERT OR IGNORE INTO growth_referral_milestones(
                    referrer_id,milestone,reward_days,tier,awarded_at
                ) VALUES(?,?,?,?,?)
                """,
                (int(referrer_id), milestone, days, tier, _now().isoformat()),
            )
        newly_awarded.append((milestone, days, tier))
    return newly_awarded


def _onboarding_markup(lang: str) -> InlineKeyboardMarkup:
    if lang == "fa":
        rows = [
            [InlineKeyboardButton(text="📊 دریافت سیگنال", callback_data="growth_onboard:signals")],
            [InlineKeyboardButton(text="🤖 اجرای خودکار AutoTrade", callback_data="growth_onboard:autotrade")],
            [InlineKeyboardButton(text="🎓 آشنایی با NEXUS", callback_data="growth_onboard:learn")],
            [InlineKeyboardButton(text="ادامه به منوی اصلی", callback_data="growth_onboard_done")],
        ]
    else:
        rows = [
            [InlineKeyboardButton(text="📊 Receive Signals", callback_data="growth_onboard:signals")],
            [InlineKeyboardButton(text="🤖 AutoTrade", callback_data="growth_onboard:autotrade")],
            [InlineKeyboardButton(text="🎓 Learn about NEXUS", callback_data="growth_onboard:learn")],
            [InlineKeyboardButton(text="Continue to Main Menu", callback_data="growth_onboard_done")],
        ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _intent_markup(lang: str) -> InlineKeyboardMarkup:
    trial = "🎁 فعال‌سازی تست VIP" if lang == "fa" else "🎁 Activate VIP Trial"
    done = "ادامه" if lang == "fa" else "Continue"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=trial, callback_data="growth_trial_claim")],
            [InlineKeyboardButton(text=done, callback_data="growth_onboard_done")],
        ]
    )


def _message_sent(telegram_id: int, message_key: str) -> bool:
    ensure_schema()
    with db.conn() as con:
        return con.execute(
            "SELECT 1 FROM growth_message_log WHERE telegram_id=? AND message_key=?",
            (int(telegram_id), str(message_key)),
        ).fetchone() is not None


def _mark_message(telegram_id: int, message_key: str, message_type: str) -> None:
    with db.conn() as con:
        con.execute(
            "INSERT OR IGNORE INTO growth_message_log(telegram_id,message_key,message_type,sent_at) VALUES(?,?,?,?)",
            (int(telegram_id), str(message_key), str(message_type), _now().isoformat()),
        )


async def _send_retention_message(main_module, bot, telegram_id: int, *, key: str, kind: str, text_fa: str, text_en: str) -> None:
    if _message_sent(int(telegram_id), key) or main_module.is_admin(int(telegram_id)):
        return
    lang = main_module.get_lang(int(telegram_id))
    text = text_fa if lang == "fa" else text_en
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💎 خرید / تمدید اشتراک" if lang == "fa" else "💎 Buy / Renew", callback_data="vip")],
            [InlineKeyboardButton(text="🛟 پشتیبانی" if lang == "fa" else "🛟 Support", callback_data="customer_support")],
        ]
    )
    try:
        await bot.send_message(int(telegram_id), text, reply_markup=markup)
        _mark_message(int(telegram_id), key, kind)
    except Exception:
        main_module.log.exception("growth retention message failed user=%s kind=%s", telegram_id, kind)


async def run_retention_cycle(main_module, bot) -> None:
    ensure_schema()
    now = _now()
    two_hours_ago = (now - timedelta(hours=2)).isoformat()
    tomorrow = (now + timedelta(days=1)).isoformat()
    three_days = (now + timedelta(days=3)).isoformat()
    one_day_ago = (now - timedelta(days=1)).isoformat()

    with db.conn() as con:
        pending = con.execute(
            """
            SELECT id,telegram_id FROM payments
            WHERE status='pending' AND created_at<=?
            ORDER BY created_at ASC LIMIT 50
            """,
            (two_hours_ago,),
        ).fetchall()
        trials = con.execute(
            """
            SELECT id,telegram_id,expires_at FROM licenses
            WHERE status='active' AND source='trial' AND expires_at>? AND expires_at<=?
            ORDER BY expires_at ASC LIMIT 50
            """,
            (now.isoformat(), tomorrow),
        ).fetchall()
        renewals = con.execute(
            """
            SELECT id,telegram_id,expires_at FROM licenses
            WHERE status='active' AND source!='trial' AND expires_at>? AND expires_at<=?
            ORDER BY expires_at ASC LIMIT 50
            """,
            (now.isoformat(), three_days),
        ).fetchall()
        expired = con.execute(
            """
            SELECT l.id,l.telegram_id,l.expires_at
            FROM licenses l
            WHERE l.expires_at<=? AND l.expires_at>=?
              AND NOT EXISTS(
                  SELECT 1 FROM licenses a
                  WHERE a.telegram_id=l.telegram_id AND a.status='active' AND a.expires_at>?
              )
            ORDER BY l.expires_at DESC LIMIT 50
            """,
            (now.isoformat(), one_day_ago, now.isoformat()),
        ).fetchall()

    for row in pending:
        await _send_retention_message(
            main_module, bot, int(row["telegram_id"]), key=f"pending_payment:{row['id']}", kind="ABANDONED_CHECKOUT",
            text_fa="خرید شما هنوز تکمیل نشده است. اگر درباره VIP یا AutoTrade سوالی دارید، پشتیبانی NEXUS در دسترس است.",
            text_en="Your purchase is not complete yet. If you have a question about VIP or AutoTrade, NEXUS Support is available.",
        )
    for row in trials:
        await _send_retention_message(
            main_module, bot, int(row["telegram_id"]), key=f"trial_expiring:{row['id']}", kind="TRIAL_EXPIRING",
            text_fa="🎁 تست VIP شما رو به پایان است. برای ادامه دسترسی می‌توانید پلن مناسب را فعال کنید.",
            text_en="🎁 Your VIP trial is ending soon. Activate a plan to keep access.",
        )
    for row in renewals:
        await _send_retention_message(
            main_module, bot, int(row["telegram_id"]), key=f"renewal:{row['id']}", kind="RENEWAL",
            text_fa="⏳ اشتراک NEXUS شما تا چند روز آینده پایان می‌یابد. برای جلوگیری از قطع دسترسی می‌توانید همین حالا تمدید کنید.",
            text_en="⏳ Your NEXUS subscription expires within a few days. Renew now to avoid an interruption.",
        )
    for row in expired:
        await _send_retention_message(
            main_module, bot, int(row["telegram_id"]), key=f"reactivation:{row['id']}", kind="REACTIVATION",
            text_fa="اشتراک NEXUS شما پایان یافته است. هر زمان آماده بودید می‌توانید دسترسی VIP یا AutoTrade را دوباره فعال کنید.",
            text_en="Your NEXUS subscription has expired. You can reactivate VIP or AutoTrade whenever you are ready.",
        )


async def _retention_worker(main_module, bot) -> None:
    while True:
        try:
            await run_retention_cycle(main_module, bot)
        except asyncio.CancelledError:
            raise
        except Exception:
            main_module.log.exception("growth retention cycle failed")
        await asyncio.sleep(6 * 60 * 60)


def install(main_module) -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    original_show_main = main_module.show_main
    original_referral_reward = main_module.maybe_reward_referral
    original_referral_menu = main_module.referral_menu
    original_rewards_menu = main_module.admin_rewards_group
    original_marketing_menu = main_module.admin_marketing_group

    async def _smart_show_main(bot, user_id: int, chat_id: int) -> None:
        if should_show_onboarding(int(user_id), is_admin=main_module.is_admin(int(user_id))):
            lang = main_module.get_lang(int(user_id))
            text = (
                "<b>⚡ به NEXUS خوش آمدید</b>\n\nبرای اینکه فقط بخش‌های مرتبط را ببینید، هدف اصلی خود را انتخاب کنید:"
                if lang == "fa"
                else "<b>⚡ Welcome to NEXUS</b>\n\nChoose your main goal so we can show the most relevant path:"
            )
            record_event(int(user_id), "ONBOARDING_VIEW", score=5)
            await main_module.screen(bot, int(user_id), int(chat_id), text, _onboarding_markup(lang))
            return
        await original_show_main(bot, int(user_id), int(chat_id))

    main_module.show_main = _smart_show_main

    async def _reward_and_milestones(bot, referred_id: int) -> None:
        await original_referral_reward(bot, int(referred_id))
        with db.conn() as con:
            row = con.execute("SELECT referred_by FROM users WHERE telegram_id=?", (int(referred_id),)).fetchone()
        if not row or row[0] is None:
            return
        referrer_id = int(row[0])
        granted_by = int(main_module.settings.admin_ids[0]) if main_module.settings.admin_ids else None
        awards = _award_referral_milestones(referrer_id, granted_by=granted_by)
        for milestone, days, tier in awards:
            lang = main_module.get_lang(referrer_id)
            text = (
                f"🎁 تبریک! با <b>{milestone}</b> دعوت موفق، <b>{days} روز VIP</b> به حساب شما اضافه شد.\nسطح: <b>{tier}</b>"
                if lang == "fa"
                else f"🎁 Congratulations! <b>{days} VIP days</b> were added for <b>{milestone}</b> successful referrals.\nTier: <b>{tier}</b>"
            )
            try:
                await bot.send_message(referrer_id, text, parse_mode="HTML")
            except Exception:
                main_module.log.exception("referral milestone notification failed user=%s", referrer_id)

    main_module.maybe_reward_referral = _reward_and_milestones

    def _referral_menu_with_reward(lang: str, share_url: str) -> InlineKeyboardMarkup:
        base = original_referral_menu(lang, share_url)
        rows = [list(row) for row in base.inline_keyboard]
        label = "🎁 3 دعوت موفق = 7 روز VIP" if lang == "fa" else "🎁 3 Successful Referrals = 7 VIP Days"
        rows.insert(0, [InlineKeyboardButton(text=label, callback_data="growth_referral_progress")])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    main_module.referral_menu = _referral_menu_with_reward

    def _rewards_menu_with_ambassador(lang: str) -> InlineKeyboardMarkup:
        base = original_rewards_menu(lang)
        rows = [list(row) for row in base.inline_keyboard]
        label = "🌱 رشد و سفیران NEXUS" if lang == "fa" else "🌱 NEXUS Ambassadors"
        rows.insert(1 if rows else 0, [InlineKeyboardButton(text=label, callback_data="admin_growth_ambassadors")])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    main_module.admin_rewards_group = _rewards_menu_with_ambassador

    def _marketing_menu_with_retention(lang: str) -> InlineKeyboardMarkup:
        base = original_marketing_menu(lang)
        rows = [list(row) for row in base.inline_keyboard]
        label = "♻️ Retention و Conversion" if lang == "fa" else "♻️ Retention & Conversion"
        rows.insert(0, [InlineKeyboardButton(text=label, callback_data="admin_growth_lifecycle")])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    main_module.admin_marketing_group = _marketing_menu_with_retention

    @main_module.router.callback_query(F.data.startswith("growth_onboard:"))
    async def growth_onboarding_intent(cb, bot):
        uid = int(cb.from_user.id)
        lang = main_module.get_lang(uid)
        intent = str(cb.data).split(":", 1)[1].upper()
        _set_intent(uid, intent)
        await cb.answer()
        if intent == "SIGNALS":
            text = (
                "<b>🎯 مسیر سیگنال</b>\n\nابتدا کیفیت سرویس VIP را در یک تست کوتاه تجربه کنید. تست فقط VIP است و AutoTrade را فعال نمی‌کند."
                if lang == "fa" else
                "<b>🎯 Signals Path</b>\n\nStart with a short VIP trial. The trial is VIP-only and never enables AutoTrade."
            )
        elif intent == "AUTOTRADE":
            text = (
                "<b>🤖 مسیر AutoTrade</b>\n\nAutoTrade اجرای سیگنال را روی MT5 خودکار می‌کند و فقط با اشتراک و لایسنس فعال می‌شود. برای آشنایی با کیفیت سیگنال‌ها می‌توانید تست VIP را فعال کنید."
                if lang == "fa" else
                "<b>🤖 AutoTrade Path</b>\n\nAutoTrade automates MT5 signal execution and requires a paid license. You may use the VIP trial to evaluate signal quality first."
            )
        else:
            text = (
                "<b>🎓 آشنایی با NEXUS</b>\n\nNEXUS سیگنال، مدیریت دسترسی و AutoTrade را یکپارچه می‌کند. می‌توانید قبل از خرید، تست VIP را فعال کنید."
                if lang == "fa" else
                "<b>🎓 About NEXUS</b>\n\nNEXUS integrates signals, access management and AutoTrade. You may activate the VIP trial before purchasing."
            )
        await main_module.screen(bot, uid, cb.message.chat.id, text, _intent_markup(lang))

    @main_module.router.callback_query(F.data == "growth_trial_claim")
    async def growth_trial_claim(cb, bot):
        uid = int(cb.from_user.id)
        lang = main_module.get_lang(uid)
        await cb.answer()
        if _has_active_access(uid):
            _complete_onboarding(uid, "CUSTOMER")
            text = "اشتراک فعال دارید؛ نیازی به تست نیست." if lang == "fa" else "You already have active access; a trial is not needed."
        elif db.trial_used(uid):
            _complete_onboarding(uid, "ACTIVATED")
            text = "تست یک‌باره این حساب قبلاً استفاده شده است." if lang == "fa" else "The one-time trial for this account has already been used."
        else:
            try:
                days = int(db.get_setting("growth_trial_days", str(TRIAL_DAYS_DEFAULT)))
            except Exception:
                days = TRIAL_DAYS_DEFAULT
            days = max(1, min(days, 7))
            admin_id = int(main_module.settings.admin_ids[0]) if main_module.settings.admin_ids else uid
            lic = db.grant_trial(uid, days, admin_id)
            if lic:
                _complete_onboarding(uid, "TRIAL")
                record_event(uid, "TRIAL_ACTIVATED", value=str(days), score=25)
                text = (
                    f"🎁 تست <b>{days} روزه VIP</b> فعال شد. AutoTrade در تست فعال نیست."
                    if lang == "fa" else
                    f"🎁 Your <b>{days}-day VIP trial</b> is active. AutoTrade is not enabled by the trial."
                )
            else:
                _complete_onboarding(uid, "ACTIVATED")
                text = "تست قابل فعال‌سازی نیست." if lang == "fa" else "The trial could not be activated."
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 منوی اصلی" if lang == "fa" else "🏠 Main Menu", callback_data="main")],
            [InlineKeyboardButton(text="💎 مشاهده پلن‌ها" if lang == "fa" else "💎 View Plans", callback_data="vip")],
        ])
        await main_module.screen(bot, uid, cb.message.chat.id, text, markup)

    @main_module.router.callback_query(F.data == "growth_onboard_done")
    async def growth_onboarding_done(cb, bot):
        uid = int(cb.from_user.id)
        _complete_onboarding(uid, "ACTIVATED")
        record_event(uid, "ONBOARDING_COMPLETED", score=10)
        await cb.answer()
        await original_show_main(bot, uid, cb.message.chat.id)

    @main_module.router.callback_query(F.data == "growth_referral_progress")
    async def growth_referral_progress(cb, bot):
        uid = int(cb.from_user.id)
        lang = main_module.get_lang(uid)
        stats = db.referral_stats(uid)
        successful = int(stats["successful"])
        with db.conn() as con:
            awarded = {int(r[0]) for r in con.execute(
                "SELECT milestone FROM growth_referral_milestones WHERE referrer_id=?", (uid,)
            ).fetchall()}
        lines = []
        for milestone, days, tier in REFERRAL_MILESTONES:
            mark = "✅" if milestone in awarded else ("🟡" if successful >= milestone else "▫️")
            lines.append(f"{mark} {milestone} → {days} VIP days ({tier})")
        if lang == "fa":
            text = f"<b>🎁 مسیر پاداش دعوت</b>\n\nدعوت موفق: <b>{successful}</b>\nسطح فعلی: <b>{referral_tier_for_count(successful)}</b>\n\n" + "\n".join(lines)
            back = "⬅️ بازگشت"
        else:
            text = f"<b>🎁 Referral Reward Path</b>\n\nSuccessful referrals: <b>{successful}</b>\nCurrent tier: <b>{referral_tier_for_count(successful)}</b>\n\n" + "\n".join(lines)
            back = "⬅️ Back"
        await cb.answer()
        await main_module.screen(bot, uid, cb.message.chat.id, text,
            InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=back, callback_data="referral")]]))

    @main_module.router.callback_query(F.data == "admin_growth_ambassadors")
    async def admin_growth_ambassadors(cb, bot):
        if not main_module.is_admin(cb.from_user.id):
            await cb.answer(); return
        ensure_schema()
        with db.conn() as con:
            rows = con.execute(
                "SELECT referrer_id,COUNT(*) c FROM referral_events WHERE status='rewarded' GROUP BY referrer_id"
            ).fetchall()
            total = int(con.execute("SELECT COUNT(*) FROM referral_events WHERE status='rewarded'").fetchone()[0])
        counts = {"BRONZE": 0, "SILVER": 0, "GOLD": 0}
        for row in rows:
            c = int(row["c"])
            tier = referral_tier_for_count(c)
            if tier in counts:
                counts[tier] += 1
        lang = main_module.get_lang(cb.from_user.id)
        text = (
            "<b>🌱 رشد و سفیران NEXUS</b>\n\n"
            f"دعوت موفق کل: <b>{total}</b>\n"
            f"BRONZE (3+): <b>{counts['BRONZE']}</b>\n"
            f"SILVER (10+): <b>{counts['SILVER']}</b>\n"
            f"GOLD (25+): <b>{counts['GOLD']}</b>\n\n"
            "پاداش‌ها: 3→7 روز VIP | 10→15 روز | 25→30 روز"
            if lang == "fa" else
            "<b>🌱 NEXUS Ambassador Growth</b>\n\n"
            f"Total successful referrals: <b>{total}</b>\n"
            f"BRONZE (3+): <b>{counts['BRONZE']}</b>\n"
            f"SILVER (10+): <b>{counts['SILVER']}</b>\n"
            f"GOLD (25+): <b>{counts['GOLD']}</b>\n\n"
            "Rewards: 3→7 VIP days | 10→15 days | 25→30 days"
        )
        await cb.answer()
        await main_module.screen(bot, cb.from_user.id, cb.message.chat.id, text,
            InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
                text="⬅️ بازگشت" if lang == "fa" else "⬅️ Back", callback_data="admin_group_rewards")]]))

    @main_module.router.callback_query(F.data == "admin_growth_lifecycle")
    async def admin_growth_lifecycle(cb, bot):
        if not main_module.is_admin(cb.from_user.id):
            await cb.answer(); return
        ensure_schema()
        now = _now()
        week = (now + timedelta(days=7)).isoformat()
        with db.conn() as con:
            total_users = int(con.execute("SELECT COUNT(*) FROM users").fetchone()[0])
            pending = int(con.execute("SELECT COUNT(*) FROM payments WHERE status='pending'").fetchone()[0])
            trials = int(con.execute("SELECT COUNT(*) FROM licenses WHERE status='active' AND source='trial' AND expires_at>?", (now.isoformat(),)).fetchone()[0])
            paid_active = int(con.execute("SELECT COUNT(DISTINCT telegram_id) FROM licenses WHERE status='active' AND source!='trial' AND expires_at>?", (now.isoformat(),)).fetchone()[0])
            expiring = int(con.execute("SELECT COUNT(DISTINCT telegram_id) FROM licenses WHERE status='active' AND expires_at>? AND expires_at<=?", (now.isoformat(), week)).fetchone()[0])
            expired = int(con.execute("""
                SELECT COUNT(*) FROM users u
                WHERE EXISTS(SELECT 1 FROM licenses l WHERE l.telegram_id=u.telegram_id AND l.expires_at<=?)
                  AND NOT EXISTS(SELECT 1 FROM licenses a WHERE a.telegram_id=u.telegram_id AND a.status='active' AND a.expires_at>?)
            """, (now.isoformat(), now.isoformat())).fetchone()[0])
            hot = int(con.execute("SELECT COUNT(*) FROM growth_user_state WHERE lead_score>=30 AND lifecycle_stage!='CUSTOMER'").fetchone()[0])
            new_leads = int(con.execute("""
                SELECT COUNT(*) FROM users u
                WHERE NOT EXISTS(SELECT 1 FROM payments p WHERE p.telegram_id=u.telegram_id AND p.status='approved')
                  AND NOT EXISTS(SELECT 1 FROM licenses l WHERE l.telegram_id=u.telegram_id AND l.status='active' AND l.expires_at>?)
            """, (now.isoformat(),)).fetchone()[0])
        lang = main_module.get_lang(cb.from_user.id)
        if lang == "fa":
            text = (
                "<b>♻️ Retention & Conversion</b>\n\n"
                f"کل کاربران: <b>{total_users}</b>\n"
                f"لید جدید: <b>{new_leads}</b>\n"
                f"Hot Lead: <b>{hot}</b>\n"
                f"خرید نیمه‌تمام: <b>{pending}</b>\n"
                f"Trial فعال: <b>{trials}</b>\n"
                f"مشتری فعال: <b>{paid_active}</b>\n"
                f"منقضی‌شونده تا 7 روز: <b>{expiring}</b>\n"
                f"نیازمند بازگشت: <b>{expired}</b>\n\n"
                "پیام‌های Checkout، پایان Trial، تمدید و Reactivation به‌صورت محدود و بدون تکرار ارسال می‌شوند."
            )
            back = "⬅️ بازگشت"
        else:
            text = (
                "<b>♻️ Retention & Conversion</b>\n\n"
                f"Total users: <b>{total_users}</b>\n"
                f"New leads: <b>{new_leads}</b>\n"
                f"Hot leads: <b>{hot}</b>\n"
                f"Abandoned checkout: <b>{pending}</b>\n"
                f"Active trials: <b>{trials}</b>\n"
                f"Active customers: <b>{paid_active}</b>\n"
                f"Expiring within 7 days: <b>{expiring}</b>\n"
                f"Reactivation segment: <b>{expired}</b>\n\n"
                "Checkout, trial-expiry, renewal and reactivation messages are deduplicated and rate-limited."
            )
            back = "⬅️ Back"
        await cb.answer()
        await main_module.screen(bot, cb.from_user.id, cb.message.chat.id, text,
            InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=back, callback_data="admin_group_marketing")]]))

    async def _on_startup(bot):
        ensure_schema()
        task = asyncio.create_task(_retention_worker(main_module, bot), name="nexus-growth-retention")
        _TASKS.add(task)
        task.add_done_callback(_TASKS.discard)

    async def _on_shutdown():
        for task in list(_TASKS):
            task.cancel()
        if _TASKS:
            await asyncio.gather(*list(_TASKS), return_exceptions=True)

    main_module.router.startup.register(_on_startup)
    main_module.router.shutdown.register(_on_shutdown)
    _INSTALLED = True
