from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from html import escape
from typing import Any

from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


_OPEN_CACHE: dict[int, tuple[float, list[dict[str, Any]]]] = {}


def _cache_ttl() -> float:
    try:
        return max(0.5, min(30.0, float(os.getenv("AUTOTRADE_OPEN_TRADES_CACHE_SECONDS", "2"))))
    except Exception:
        return 2.0


def _poll_seconds() -> float:
    try:
        return max(0.2, min(5.0, float(os.getenv("AUTOTRADE_NOTIFICATION_POLL_SECONDS", "0.5"))))
    except Exception:
        return 0.5


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return default


def _fmt_price(value: Any) -> str:
    x = _float(value)
    if x == 0:
        return "—"
    raw = f"{x:.8f}".rstrip("0").rstrip(".")
    return raw or "0"


def _fmt_pnl(value: Any) -> str:
    x = _float(value)
    sign = "+" if x > 0 else ""
    return f"{sign}{x:,.2f}"


def _duration_fa(seconds: int) -> str:
    seconds = max(0, int(seconds))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    if days:
        return f"{days} روز و {hours} ساعت"
    if hours:
        return f"{hours} ساعت و {minutes} دقیقه"
    return f"{minutes} دقیقه"


def _duration_en(seconds: int) -> str:
    seconds = max(0, int(seconds))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def _parse_dt(raw: Any) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _ensure_delivery_table(core) -> None:
    with core.db.conn() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS autotrade_user_event_deliveries (
                event_key TEXT PRIMARY KEY,
                telegram_id INTEGER NOT NULL,
                notification_id INTEGER,
                claimed_at TEXT,
                sent_at TEXT,
                telegram_message_id INTEGER,
                error_text TEXT
            )
            """
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_autotrade_user_event_delivery_user "
            "ON autotrade_user_event_deliveries(telegram_id, sent_at)"
        )


def _claim_delivery(core, event_key: str, user_id: int, notification_id: int) -> bool:
    now = datetime.now(timezone.utc)
    cutoff = (now.timestamp() - 300.0)
    with core.db.conn() as con:
        row = con.execute(
            "SELECT claimed_at,sent_at FROM autotrade_user_event_deliveries WHERE event_key=?",
            (event_key,),
        ).fetchone()
        if row and row["sent_at"]:
            return False
        if row and row["claimed_at"]:
            claimed = _parse_dt(row["claimed_at"])
            if claimed and claimed.timestamp() >= cutoff:
                return False
        if row:
            con.execute(
                "UPDATE autotrade_user_event_deliveries SET telegram_id=?,notification_id=?,claimed_at=?,error_text=NULL "
                "WHERE event_key=? AND sent_at IS NULL",
                (int(user_id), int(notification_id), now.isoformat(), event_key),
            )
        else:
            con.execute(
                "INSERT INTO autotrade_user_event_deliveries(event_key,telegram_id,notification_id,claimed_at) "
                "VALUES(?,?,?,?)",
                (event_key, int(user_id), int(notification_id), now.isoformat()),
            )
        return True


def _finish_delivery(core, event_key: str, message_id: int | None, error: str | None = None) -> None:
    with core.db.conn() as con:
        if error:
            con.execute(
                "UPDATE autotrade_user_event_deliveries SET claimed_at=NULL,error_text=? WHERE event_key=? AND sent_at IS NULL",
                (str(error)[:1000], event_key),
            )
        else:
            con.execute(
                "UPDATE autotrade_user_event_deliveries SET sent_at=?,telegram_message_id=?,error_text=NULL WHERE event_key=?",
                (datetime.now(timezone.utc).isoformat(), int(message_id or 0), event_key),
            )


def _previous_trade_event(core, user_id: int, ticket: str, current_event_id: str) -> dict[str, Any] | None:
    try:
        with core.db.conn() as con:
            row = con.execute(
                "SELECT * FROM autotrade_trade_executions "
                "WHERE telegram_id=? AND ticket=? AND event_id<>? "
                "ORDER BY id DESC LIMIT 1",
                (int(user_id), str(ticket), str(current_event_id or "")),
            ).fetchone()
            return dict(row) if row else None
    except Exception:
        return None


def _trade_opened_at(core, user_id: int, ticket: str, signal_code: str = "") -> datetime | None:
    try:
        with core.db.conn() as con:
            row = con.execute(
                "SELECT created_at FROM autotrade_trade_executions "
                "WHERE telegram_id=? AND ticket=? AND event_type='OPEN' "
                "ORDER BY id ASC LIMIT 1",
                (int(user_id), str(ticket)),
            ).fetchone()
            if row:
                dt = _parse_dt(row["created_at"])
                if dt:
                    return dt
    except Exception:
        pass
    if signal_code:
        try:
            sig = core.db.get_signal_by_code(signal_code)
            if sig:
                for key in ("opened_at", "created_at"):
                    if key in sig.keys() and sig[key]:
                        dt = _parse_dt(sig[key])
                        if dt:
                            return dt
        except Exception:
            pass
    return None


def _signal_for_live(core, row: dict[str, Any]):
    code = str(row.get("signal_code") or "").strip()
    if not code:
        return None
    try:
        return core.db.get_signal_by_code(code)
    except Exception:
        return None


def _live_positions(core, user_id: int, *, refresh: bool = False) -> list[dict[str, Any]]:
    now = time.monotonic()
    cached = _OPEN_CACHE.get(int(user_id))
    if not refresh and cached and now - cached[0] <= _cache_ttl():
        return cached[1]

    mt5 = core.db.mt5_account(int(user_id))
    if not mt5:
        rows: list[dict[str, Any]] = []
    else:
        account = str(mt5["account_number"])
        rows = [dict(x) for x in core.db.mt5_live_positions(account, nexus_only=True)]
        rows.sort(key=lambda r: (str(r.get("symbol") or ""), str(r.get("ticket") or "")))
    _OPEN_CACHE[int(user_id)] = (now, rows)
    return rows


def _open_menu(core, user_id: int, lang: str, *, refresh: bool = False) -> tuple[str, InlineKeyboardMarkup]:
    rows = _live_positions(core, user_id, refresh=refresh)
    if not rows:
        text = core.tr(
            lang,
            "<b>🖥 معاملات باز AutoTrade</b>\n\nدر حال حاضر هیچ پوزیشن باز NEXUS روی حساب متصل شما وجود ندارد.",
            "<b>🖥 Open AutoTrade Positions</b>\n\nThere are currently no open NEXUS positions on your connected account.",
        )
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=core.tr(lang, "🔄 بروزرسانی", "🔄 Refresh"), callback_data="autotrade_open")],
            [InlineKeyboardButton(text=core.tr(lang, "⬅️ بازگشت", "⬅️ Back"), callback_data="client_autotrade_access")],
        ])
        return text, markup

    buttons = []
    for row in rows[:25]:
        ticket = str(row.get("ticket") or row.get("identifier") or "")
        symbol = str(row.get("symbol") or "—")
        direction = str(row.get("direction") or "").upper()
        side = "BUY" if direction in {"BUY", "LONG"} else "SELL" if direction in {"SELL", "SHORT"} else direction or "—"
        pnl = _fmt_pnl(row.get("profit"))
        icon = "🟢" if _float(row.get("profit")) >= 0 else "🔴"
        label = f"{icon} {symbol} • {side} • PnL {pnl}"
        buttons.append([InlineKeyboardButton(text=label[:60], callback_data=f"autotrade_position:{ticket}")])

    buttons.extend([
        [InlineKeyboardButton(text=core.tr(lang, "🔄 بروزرسانی لحظه‌ای", "🔄 Refresh Live"), callback_data="autotrade_open")],
        [InlineKeyboardButton(text=core.tr(lang, "⬅️ بازگشت", "⬅️ Back"), callback_data="client_autotrade_access")],
    ])
    text = core.tr(
        lang,
        f"<b>🖥 معاملات باز AutoTrade</b>\n\nتعداد پوزیشن‌های فعال: <b>{len(rows)}</b>\nبرای مشاهده فلش‌کارت کامل هر معامله، روی آن بزنید.",
        f"<b>🖥 Open AutoTrade Positions</b>\n\nActive positions: <b>{len(rows)}</b>\nTap a trade to open its full flash card.",
    )
    return text, InlineKeyboardMarkup(inline_keyboard=buttons)


def _position_card(core, user_id: int, lang: str, ticket: str) -> tuple[str, InlineKeyboardMarkup] | None:
    rows = _live_positions(core, user_id, refresh=True)
    row = next((r for r in rows if str(r.get("ticket") or "") == str(ticket)), None)
    if row is None:
        return None

    sig = _signal_for_live(core, row)
    leverage = None
    if sig is not None and "leverage" in sig.keys() and sig["leverage"] is not None:
        leverage = _float(sig["leverage"])
    signal_code = str(row.get("signal_code") or (sig["code"] if sig is not None else "") or "—")
    opened = _trade_opened_at(core, user_id, str(ticket), signal_code if signal_code != "—" else "")
    duration = int((datetime.now(timezone.utc) - opened).total_seconds()) if opened else 0
    direction = str(row.get("direction") or "").upper()
    side = "BUY" if direction in {"BUY", "LONG"} else "SELL" if direction in {"SELL", "SHORT"} else direction or "—"
    status = str(row.get("status") or "OPEN").upper()
    last_seen = _parse_dt(row.get("last_seen_at"))
    last_seen_text = core.fmt_dt(last_seen.isoformat()) if last_seen else "—"
    pnl = _fmt_pnl(row.get("profit"))

    fa = (
        "<b>🧾 فلش‌کارت معامله باز</b>\n\n"
        f"📌 نماد: <b>{escape(str(row.get('symbol') or '—'))}</b>\n"
        f"↕️ جهت: <b>{escape(side)}</b>\n"
        f"📦 حجم: <b>{_float(row.get('volume')):g}</b>\n"
        f"⚙️ لوریج: <b>{(f'{leverage:g}x' if leverage else '—')}</b>\n"
        f"🎯 ورود: <code>{_fmt_price(row.get('entry_price'))}</code>\n"
        f"🛡 استاپ فعلی: <code>{_fmt_price(row.get('stop_loss'))}</code>\n"
        f"🏁 تیک‌پروفیت فعلی: <code>{_fmt_price(row.get('take_profit'))}</code>\n"
        f"💹 قیمت فعلی: <code>{_fmt_price(row.get('current_price'))}</code>\n"
        f"💵 PnL لحظه‌ای: <b>{pnl}</b>\n"
        f"⏱ مدت باز بودن: <b>{_duration_fa(duration) if opened else '—'}</b>\n"
        f"📡 وضعیت: <b>{escape(status)}</b>\n"
        f"🆔 سیگنال: <code>{escape(signal_code)}</code>\n"
        f"🎫 Ticket: <code>{escape(str(ticket))}</code>\n"
        f"🕒 آخرین همگام‌سازی: <b>{escape(last_seen_text)}</b>"
    )
    en = (
        "<b>🧾 Open Trade Flash Card</b>\n\n"
        f"📌 Symbol: <b>{escape(str(row.get('symbol') or '—'))}</b>\n"
        f"↕️ Side: <b>{escape(side)}</b>\n"
        f"📦 Volume: <b>{_float(row.get('volume')):g}</b>\n"
        f"⚙️ Leverage: <b>{(f'{leverage:g}x' if leverage else '—')}</b>\n"
        f"🎯 Entry: <code>{_fmt_price(row.get('entry_price'))}</code>\n"
        f"🛡 Current SL: <code>{_fmt_price(row.get('stop_loss'))}</code>\n"
        f"🏁 Current TP: <code>{_fmt_price(row.get('take_profit'))}</code>\n"
        f"💹 Current price: <code>{_fmt_price(row.get('current_price'))}</code>\n"
        f"💵 Live PnL: <b>{pnl}</b>\n"
        f"⏱ Open duration: <b>{_duration_en(duration) if opened else '—'}</b>\n"
        f"📡 Status: <b>{escape(status)}</b>\n"
        f"🆔 Signal: <code>{escape(signal_code)}</code>\n"
        f"🎫 Ticket: <code>{escape(str(ticket))}</code>\n"
        f"🕒 Last sync: <b>{escape(last_seen_text)}</b>"
    )
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=core.tr(lang, "🔄 بروزرسانی PnL", "🔄 Refresh PnL"), callback_data=f"autotrade_position:{ticket}")],
        [InlineKeyboardButton(text=core.tr(lang, "🖥 معاملات باز", "🖥 Open Trades"), callback_data="autotrade_open")],
        [InlineKeyboardButton(text=core.tr(lang, "⬅️ مرکز AutoTrade", "⬅️ AutoTrade Center"), callback_data="client_autotrade_access")],
    ])
    return core.tr(lang, fa, en), markup


def _close_reason_fa(reason: str) -> str:
    return {
        "SL": "استاپ‌لاس",
        "TP": "تیک‌پروفیت",
        "CLIENT": "بستن دستی در MT5",
        "MOBILE": "بستن دستی از موبایل",
        "WEB": "بستن از Web Terminal",
        "EXPERT": "Expert / AutoTrade",
        "SO": "Stop Out",
        "ROLLOVER": "Rollover",
    }.get(str(reason or "").upper(), str(reason or "نامشخص"))


def _close_reason_en(reason: str) -> str:
    return {
        "SL": "Stop Loss",
        "TP": "Take Profit",
        "CLIENT": "Manual close in MT5",
        "MOBILE": "Manual close from mobile",
        "WEB": "Web terminal close",
        "EXPERT": "Expert / AutoTrade",
        "SO": "Stop Out",
        "ROLLOVER": "Rollover",
    }.get(str(reason or "").upper(), str(reason or "Unknown"))


def _event_message(core, user_id: int, payload: dict[str, Any]) -> tuple[str, InlineKeyboardMarkup]:
    lang = core.get_lang(user_id)
    event = str(payload.get("event") or "UPDATE").upper()
    symbol = escape(str(payload.get("symbol") or "—"))
    direction = str(payload.get("direction") or "").upper()
    side = "BUY" if direction in {"BUY", "LONG"} else "SELL" if direction in {"SELL", "SHORT"} else direction or "—"
    ticket = escape(str(payload.get("ticket") or "—"))
    signal_code = escape(str(payload.get("signal_id") or "—"))
    volume = _float(payload.get("volume"))
    entry = _fmt_price(payload.get("entry_price"))
    sl = _fmt_price(payload.get("stop_loss"))
    tp = _fmt_price(payload.get("take_profit"))
    pnl = _fmt_pnl(payload.get("profit"))
    event_id = str(payload.get("event_id") or "")
    previous = _previous_trade_event(core, user_id, str(payload.get("ticket") or ""), event_id)

    if event == "OPEN":
        fa = (
            "<b>🟢 معامله AutoTrade باز شد</b>\n\n"
            f"📌 {symbol} | <b>{escape(side)}</b>\n"
            f"📦 حجم: <b>{volume:g}</b>\n"
            f"🎯 Entry: <code>{entry}</code>\n"
            f"🛡 SL: <code>{sl}</code>\n"
            f"🏁 TP: <code>{tp}</code>\n"
            f"🆔 Signal: <code>{signal_code}</code>\n"
            f"🎫 Ticket: <code>{ticket}</code>"
        )
        en = (
            "<b>🟢 AutoTrade position opened</b>\n\n"
            f"📌 {symbol} | <b>{escape(side)}</b>\n"
            f"📦 Volume: <b>{volume:g}</b>\n"
            f"🎯 Entry: <code>{entry}</code>\n"
            f"🛡 SL: <code>{sl}</code>\n"
            f"🏁 TP: <code>{tp}</code>\n"
            f"🆔 Signal: <code>{signal_code}</code>\n"
            f"🎫 Ticket: <code>{ticket}</code>"
        )
    elif event == "PENDING":
        fa = f"<b>🟡 سفارش AutoTrade ثبت شد</b>\n\n📌 {symbol} | <b>{escape(side)}</b>\n🎯 Entry: <code>{entry}</code>\n🛡 SL: <code>{sl}</code>\n🏁 TP: <code>{tp}</code>\n🎫 Ticket: <code>{ticket}</code>"
        en = f"<b>🟡 AutoTrade pending order created</b>\n\n📌 {symbol} | <b>{escape(side)}</b>\n🎯 Entry: <code>{entry}</code>\n🛡 SL: <code>{sl}</code>\n🏁 TP: <code>{tp}</code>\n🎫 Ticket: <code>{ticket}</code>"
    elif event == "UPDATE":
        old_sl = _fmt_price(previous.get("stop_loss")) if previous else "—"
        old_tp = _fmt_price(previous.get("take_profit")) if previous else "—"
        old_volume = _float(payload.get("previous_volume"), _float(previous.get("volume")) if previous else 0.0)
        changes_fa: list[str] = []
        changes_en: list[str] = []
        if previous and abs(_float(previous.get("stop_loss")) - _float(payload.get("stop_loss"))) > 1e-12:
            changes_fa.append(f"🛡 Stop Loss: <code>{old_sl}</code> → <code>{sl}</code>")
            changes_en.append(f"🛡 Stop Loss: <code>{old_sl}</code> → <code>{sl}</code>")
        if previous and abs(_float(previous.get("take_profit")) - _float(payload.get("take_profit"))) > 1e-12:
            changes_fa.append(f"🏁 Take Profit: <code>{old_tp}</code> → <code>{tp}</code>")
            changes_en.append(f"🏁 Take Profit: <code>{old_tp}</code> → <code>{tp}</code>")
        if (payload.get("previous_volume") is not None or previous) and abs(old_volume - volume) > 1e-12:
            changes_fa.append(f"📦 حجم: <b>{old_volume:g}</b> → <b>{volume:g}</b>")
            changes_en.append(f"📦 Volume: <b>{old_volume:g}</b> → <b>{volume:g}</b>")
        if not changes_fa:
            if not previous:
                changes_fa.append(f"🛡 Stop Loss فعلی: <code>{sl}</code>\n🏁 Take Profit فعلی: <code>{tp}</code>\n📦 حجم فعلی: <b>{volume:g}</b>")
                changes_en.append(f"🛡 Current SL: <code>{sl}</code>\n🏁 Current TP: <code>{tp}</code>\n📦 Current volume: <b>{volume:g}</b>")
            else:
                changes_fa.append("🔄 وضعیت پوزیشن بروزرسانی شد.")
                changes_en.append("🔄 Position state was updated.")
        fa = f"<b>🔄 تغییر در معامله AutoTrade</b>\n\n📌 {symbol} | <b>{escape(side)}</b>\n" + "\n".join(changes_fa) + f"\n🎫 Ticket: <code>{ticket}</code>"
        en = f"<b>🔄 AutoTrade position updated</b>\n\n📌 {symbol} | <b>{escape(side)}</b>\n" + "\n".join(changes_en) + f"\n🎫 Ticket: <code>{ticket}</code>"
    elif event == "CLOSE":
        reason = str(payload.get("close_reason") or "")
        exit_price = _fmt_price(payload.get("exit_price"))
        fa = f"<b>🔴 معامله AutoTrade بسته شد</b>\n\n📌 {symbol} | <b>{escape(side)}</b>\n💵 PnL نهایی: <b>{pnl}</b>\n🚪 Exit: <code>{exit_price}</code>\n📋 علت: <b>{escape(_close_reason_fa(reason))}</b>\n🎫 Ticket: <code>{ticket}</code>"
        en = f"<b>🔴 AutoTrade position closed</b>\n\n📌 {symbol} | <b>{escape(side)}</b>\n💵 Final PnL: <b>{pnl}</b>\n🚪 Exit: <code>{exit_price}</code>\n📋 Reason: <b>{escape(_close_reason_en(reason))}</b>\n🎫 Ticket: <code>{ticket}</code>"
    elif event in {"CANCEL", "EXPIRE"}:
        fa_title = "⚪ سفارش AutoTrade لغو شد" if event == "CANCEL" else "⌛ سفارش AutoTrade منقضی شد"
        en_title = "⚪ AutoTrade order cancelled" if event == "CANCEL" else "⌛ AutoTrade order expired"
        fa = f"<b>{fa_title}</b>\n\n📌 {symbol}\n🎫 Ticket: <code>{ticket}</code>"
        en = f"<b>{en_title}</b>\n\n📌 {symbol}\n🎫 Ticket: <code>{ticket}</code>"
    else:
        fa = f"<b>ℹ️ تغییر وضعیت AutoTrade</b>\n\n📌 {symbol}\n📡 وضعیت: <b>{escape(event)}</b>\n🎫 Ticket: <code>{ticket}</code>"
        en = f"<b>ℹ️ AutoTrade status changed</b>\n\n📌 {symbol}\n📡 Status: <b>{escape(event)}</b>\n🎫 Ticket: <code>{ticket}</code>"

    callback = "autotrade_history" if event in {"CLOSE", "CANCEL", "EXPIRE"} else "autotrade_open"
    label_fa = "📜 تاریخچه معاملات" if callback == "autotrade_history" else "🖥 مشاهده معاملات باز"
    label_en = "📜 Trade History" if callback == "autotrade_history" else "🖥 View Open Trades"
    markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=core.tr(lang, label_fa, label_en), callback_data=callback)]])
    return core.tr(lang, fa, en), markup


async def _send_private_trade_event(core, bot, n, payload: dict[str, Any]) -> None:
    user_id = int(n["telegram_id"])
    if user_id <= 0:
        return
    # Admin-MT5 events are channel-authority lifecycle events, not customer
    # account events. A real customer AutoTrade user has a bound MT5 account.
    if not core.db.mt5_account(user_id):
        return

    event_key = str(n["event_key"] or f"notification:{n['id']}")
    if not _claim_delivery(core, event_key, user_id, int(n["id"])):
        return
    try:
        text, markup = _event_message(core, user_id, payload)
        msg = await bot.send_message(
            user_id,
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=markup,
            disable_web_page_preview=True,
        )
        _finish_delivery(core, event_key, msg.message_id)
        _OPEN_CACHE.pop(user_id, None)
        ttl = int(core.settings.autotrade_notification_ttl_seconds)
        task = asyncio.create_task(core._delete_transient_notification(bot, user_id, msg.message_id, ttl))
        core.BACKGROUND_TASKS.add(task)
        task.add_done_callback(core.BACKGROUND_TASKS.discard)
    except Exception as exc:
        _finish_delivery(core, event_key, None, str(exc))
        core.log.warning("AutoTrade private lifecycle notification failed for %s: %s", user_id, exc)


async def _enhanced_notification_worker(core, bot) -> None:
    """Durable DB-queue worker with sub-second polling and lifecycle routing."""
    while True:
        try:
            for n in core.db.pending_autotrade_notifications(100):
                notification_id = int(n["id"])
                if not core.db.claim_autotrade_notification(notification_id):
                    continue
                payload: dict[str, Any] = {}
                if n["payload_json"]:
                    try:
                        payload = json.loads(str(n["payload_json"]))
                    except Exception:
                        payload = {}
                event_type = str(n["event_type"] or "")
                user_id = int(n["telegram_id"])
                try:
                    if event_type == "MT5_TRADE_EVENT":
                        await core._process_mt5_trade_event(bot, n, payload)
                        core.db.mark_autotrade_notification_sent(notification_id)
                    elif event_type == "SIGNAL_RECEIPT":
                        # OPEN/UPDATE/CLOSE MT5 trade events are the authoritative
                        # lifecycle messages. Keep receipt chat output only for
                        # execution failures so users do not receive duplicates.
                        status = str(payload.get("status") or "").lower()
                        if status in {"rejected", "failed", "failed_retryable"} and user_id > 0:
                            sig = core.db.get_signal(int(n["signal_id"])) if n["signal_id"] else None
                            symbol = escape(str(sig["symbol"])) if sig else "—"
                            lang = core.get_lang(user_id)
                            text = core.tr(
                                lang,
                                f"⚠️ <b>AutoTrade اجرا نشد</b>\n\n📌 {symbol}\nجزئیات خطا در تاریخچه AutoTrade ثبت شده است.",
                                f"⚠️ <b>AutoTrade execution failed</b>\n\n📌 {symbol}\nThe error details are stored in AutoTrade history.",
                            )
                            msg = await bot.send_message(user_id, text, parse_mode=ParseMode.HTML)
                            task = asyncio.create_task(core._delete_transient_notification(bot, user_id, msg.message_id, core.settings.autotrade_notification_ttl_seconds))
                            core.BACKGROUND_TASKS.add(task)
                            task.add_done_callback(core.BACKGROUND_TASKS.discard)
                        core.db.mark_autotrade_notification_sent(notification_id)
                    else:
                        core.db.mark_autotrade_notification_sent(notification_id)
                except Exception as exc:
                    core.db.release_autotrade_notification_claim(notification_id)
                    core.log.warning("AutoTrade queued notification failed id=%s: %s", notification_id, exc)
                await asyncio.sleep(0.04)
        except Exception:
            core.log.exception("AutoTrade notification worker error")
        await asyncio.sleep(_poll_seconds())


class _AutoTradeOpenTradesMiddleware:
    def __init__(self, core):
        self.core = core

    async def __call__(self, handler, event, data):
        raw = str(getattr(event, "data", None) or "")
        if raw != "autotrade_open" and not raw.startswith("autotrade_position:"):
            return await handler(event, data)

        bot = data.get("bot")
        if bot is None:
            return await handler(event, data)
        if not await self.core.gated(event, bot):
            return None

        user_id = int(event.from_user.id)
        lang = self.core.get_lang(user_id)
        if not self.core.license_service.has_autotrade(user_id):
            await event.answer(
                self.core.tr(lang, "AutoTrade برای این حساب فعال نیست.", "AutoTrade is not active for this account."),
                show_alert=True,
            )
            await self.core.show_main(bot, user_id, event.message.chat.id)
            return None

        if raw == "autotrade_open":
            await event.answer()
            text, markup = _open_menu(self.core, user_id, lang, refresh=True)
            await self.core.screen(bot, user_id, event.message.chat.id, text, markup)
            return None

        ticket = raw.split(":", 1)[1].strip()
        await event.answer()
        card = _position_card(self.core, user_id, lang, ticket)
        if card is None:
            await event.answer(
                self.core.tr(lang, "این معامله دیگر باز نیست یا متعلق به حساب شما نیست.", "This trade is no longer open or does not belong to your account."),
                show_alert=True,
            )
            text, markup = _open_menu(self.core, user_id, lang, refresh=True)
            await self.core.screen(bot, user_id, event.message.chat.id, text, markup)
            return None
        text, markup = card
        await self.core.screen(bot, user_id, event.message.chat.id, text, markup)
        return None


def install_autotrade_user_experience(core) -> None:
    """Install private lifecycle notifications and live Open Trades flash cards."""
    if getattr(core, "_NEXUS_AUTOTRADE_USER_UX_INSTALLED", False):
        return

    _ensure_delivery_table(core)
    original_process = core._process_mt5_trade_event

    async def process_with_private_delivery(bot, n, payload):
        try:
            await original_process(bot, n, payload)
        finally:
            # Private account lifecycle truth must not disappear merely because
            # a public-channel publication step is temporarily unavailable.
            await _send_private_trade_event(core, bot, n, payload)

    core._process_mt5_trade_event = process_with_private_delivery

    async def notification_worker(bot):
        await _enhanced_notification_worker(core, bot)

    core.autotrade_notification_worker = notification_worker
    core.router.callback_query.outer_middleware(_AutoTradeOpenTradesMiddleware(core))
    core._NEXUS_AUTOTRADE_USER_UX_INSTALLED = True
