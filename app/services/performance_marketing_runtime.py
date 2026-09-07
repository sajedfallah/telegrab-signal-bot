from __future__ import annotations

"""NEXUS performance marketing engine.

Evaluates realized FREE vs VIP signal performance, sends low-frequency
performance promotions to the public topic and eligible private users, and can
issue truthful time-limited discounts when VIP materially outperforms FREE.

No unrealized PnL, no guaranteed-profit claims, no fake scarcity.
"""

import asyncio
import json
import logging
import os
import secrets
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from aiogram import F
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

log = logging.getLogger(__name__)

_INSTALLED = False


def _env_bool(name: str, default: bool) -> bool:
    raw = str(os.getenv(name, "true" if default else "false")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(str(os.getenv(name, default)).strip())
    except Exception:
        value = default
    return max(minimum, min(maximum, value))


def _env_float(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(str(os.getenv(name, default)).strip())
    except Exception:
        value = default
    return max(minimum, min(maximum, value))


def _parse_hm(value: str, default: str = "22:30") -> tuple[int, int]:
    raw = str(value or default).strip()
    try:
        hh_s, mm_s = raw.split(":", 1)
        hh, mm = int(hh_s), int(mm_s)
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return hh, mm
    except Exception:
        pass
    return (22, 30)


@dataclass(frozen=True)
class ChannelMetrics:
    channel: str
    trades: int
    wins: int
    losses: int
    be: int
    win_rate: float
    net_r: float
    avg_r: float
    r_coverage: float
    net_usd: float
    gross_profit_usd: float
    gross_loss_usd: float
    usd_coverage: float
    profit_factor: float
    winning_streak: int
    max_drawdown_r: float


@dataclass(frozen=True)
class AdvantageDecision:
    score: int
    hard_conditions: int
    qualifies: bool
    strong: bool
    reasons: tuple[str, ...]


def ensure_schema(main: Any) -> None:
    with main.db.conn() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS performance_marketing_campaigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                period_key TEXT NOT NULL,
                period_start TEXT NOT NULL,
                period_end TEXT NOT NULL,
                score INTEGER NOT NULL,
                hard_conditions INTEGER NOT NULL,
                vip_metrics_json TEXT NOT NULL,
                free_metrics_json TEXT NOT NULL,
                discount_percent REAL,
                public_discount_code TEXT,
                discount_expires_at TEXT,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS performance_marketing_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id INTEGER NOT NULL,
                recipient_type TEXT NOT NULL,
                telegram_id INTEGER NOT NULL DEFAULT 0,
                chat_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                action TEXT NOT NULL DEFAULT 'PERFORMANCE',
                sent_at TEXT NOT NULL,
                delete_at TEXT,
                deleted_at TEXT,
                FOREIGN KEY(campaign_id) REFERENCES performance_marketing_campaigns(id)
            );
            CREATE INDEX IF NOT EXISTS idx_perf_messages_user_time
                ON performance_marketing_messages(telegram_id, sent_at);
            CREATE INDEX IF NOT EXISTS idx_perf_messages_delete
                ON performance_marketing_messages(delete_at, deleted_at);

            CREATE TABLE IF NOT EXISTS performance_marketing_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id INTEGER NOT NULL,
                telegram_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                value TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(campaign_id) REFERENCES performance_marketing_campaigns(id)
            );
            CREATE INDEX IF NOT EXISTS idx_perf_events_campaign
                ON performance_marketing_events(campaign_id, event_type, created_at);
            """
        )


def _signal_r(row: Any) -> float | None:
    unit = str(row["result_unit"] or "").strip().upper()
    rv = float(row["result_value"] or 0.0)
    if unit in {"R", "RR", "R-MULTIPLE", "R_MULTIPLE"}:
        return rv

    entry = float(row["entry_price"] or 0.0)
    stop = float(row["stop_loss"] or 0.0)
    exit_price = float(row["exit_price"] or 0.0)
    risk = abs(entry - stop)
    if entry <= 0 or exit_price <= 0 or risk <= 0:
        return None
    direction = str(row["direction"] or "").upper()
    move = (exit_price - entry) if direction in {"BUY", "LONG"} else (entry - exit_price)
    return move / risk


def _signal_return_pct(row: Any) -> float | None:
    entry = float(row["entry_price"] or 0.0)
    exit_price = float(row["exit_price"] or 0.0)
    if entry <= 0 or exit_price <= 0:
        return None
    direction = str(row["direction"] or "").upper()
    move = (exit_price - entry) if direction in {"BUY", "LONG"} else (entry - exit_price)
    return (move / entry) * 100.0


def _channel_rows(main: Any, start_iso: str, end_iso: str, channel: str) -> list[Any]:
    channel = channel.upper()
    if channel not in {"FREE", "VIP"}:
        raise ValueError("channel must be FREE or VIP")
    allowed = ("FREE", "BOTH") if channel == "FREE" else ("VIP", "BOTH")
    with main.db.conn() as con:
        return list(
            con.execute(
                """
                SELECT id,direction,entry_price,stop_loss,exit_price,result_value,result_unit,closed_at
                FROM signals
                WHERE status='CLOSED'
                  AND closed_at>=? AND closed_at<?
                  AND destination IN (?,?)
                ORDER BY closed_at ASC,id ASC
                """,
                (start_iso, end_iso, allowed[0], allowed[1]),
            ).fetchall()
        )


def calculate_channel_metrics(main: Any, start_iso: str, end_iso: str, channel: str) -> ChannelMetrics:
    rows = _channel_rows(main, start_iso, end_iso, channel)
    wins = losses = be = 0
    r_values: list[float] = []
    usd_values: list[float] = []
    return_values: list[float] = []
    current_streak = best_streak = 0

    for row in rows:
        ret = _signal_return_pct(row)
        rv = float(row["result_value"] or 0.0)
        sign_value = ret if ret is not None else rv
        if sign_value > 1e-12:
            wins += 1
            current_streak += 1
            best_streak = max(best_streak, current_streak)
        elif sign_value < -1e-12:
            losses += 1
            current_streak = 0
        else:
            be += 1
            current_streak = 0

        if ret is not None:
            return_values.append(ret)

        r_value = _signal_r(row)
        if r_value is not None:
            r_values.append(float(r_value))

        if str(row["result_unit"] or "").strip().upper() in {"USD", "$", "USDT"}:
            usd_values.append(rv)

    total = len(rows)
    positives = sum(x for x in return_values if x > 0)
    negatives = abs(sum(x for x in return_values if x < 0))
    if negatives > 1e-12:
        profit_factor = positives / negatives
    elif positives > 0:
        profit_factor = 99.0
    else:
        profit_factor = 0.0

    cumulative = 0.0
    peak = 0.0
    max_dd = 0.0
    for value in r_values:
        cumulative += value
        peak = max(peak, cumulative)
        max_dd = max(max_dd, peak - cumulative)

    gross_profit_usd = sum(x for x in usd_values if x > 0)
    gross_loss_usd = abs(sum(x for x in usd_values if x < 0))

    return ChannelMetrics(
        channel=channel.upper(),
        trades=total,
        wins=wins,
        losses=losses,
        be=be,
        win_rate=round((wins / total * 100.0) if total else 0.0, 1),
        net_r=round(sum(r_values), 2),
        avg_r=round((sum(r_values) / len(r_values)) if r_values else 0.0, 2),
        r_coverage=round((len(r_values) / total) if total else 0.0, 3),
        net_usd=round(sum(usd_values), 2),
        gross_profit_usd=round(gross_profit_usd, 2),
        gross_loss_usd=round(gross_loss_usd, 2),
        usd_coverage=round((len(usd_values) / total) if total else 0.0, 3),
        profit_factor=round(min(profit_factor, 99.0), 2),
        winning_streak=best_streak,
        max_drawdown_r=round(max_dd, 2),
    )


def score_advantage(vip: ChannelMetrics, free: ChannelMetrics, *, usd_threshold: float = 150.0) -> AdvantageDecision:
    score = 0
    hard = 0
    reasons: list[str] = []

    net_r_delta = vip.net_r - free.net_r
    if net_r_delta >= 2.0 and vip.net_r > 0:
        score += 25
        hard += 1
        reasons.append(f"Net R advantage {net_r_delta:+.2f}R")
    elif net_r_delta >= 1.0 and vip.net_r > 0:
        score += 12

    usd_ready = vip.usd_coverage >= 0.60 and free.usd_coverage >= 0.60
    usd_delta = vip.net_usd - free.net_usd
    if usd_ready and usd_delta >= usd_threshold and vip.net_usd > 0:
        score += 20
        hard += 1
        reasons.append(f"Net USD advantage ${usd_delta:+.2f}")
    elif usd_ready and usd_delta >= usd_threshold * 0.5 and vip.net_usd > 0:
        score += 10

    pf_delta = vip.profit_factor - free.profit_factor
    if vip.profit_factor >= 1.50 and pf_delta >= 0.30:
        score += 20
        hard += 1
        reasons.append(f"Profit factor {vip.profit_factor:.2f} vs {free.profit_factor:.2f}")
    elif vip.profit_factor >= 1.25 and pf_delta > 0:
        score += 10

    wr_delta = vip.win_rate - free.win_rate
    if wr_delta >= 15.0:
        score += 15
        hard += 1
        reasons.append(f"Win rate advantage {wr_delta:+.1f}pp")
    elif wr_delta >= 7.5:
        score += 7

    avg_r_delta = vip.avg_r - free.avg_r
    if vip.r_coverage >= 0.60 and free.r_coverage >= 0.60 and avg_r_delta >= 0.25:
        score += 10
        hard += 1
        reasons.append(f"Average R advantage {avg_r_delta:+.2f}R")

    if vip.winning_streak >= 3 and vip.winning_streak > free.winning_streak:
        score += 5
        reasons.append(f"VIP winning streak {vip.winning_streak}")

    dd_advantage = free.max_drawdown_r - vip.max_drawdown_r
    if vip.r_coverage >= 0.60 and free.r_coverage >= 0.60 and dd_advantage >= 1.0:
        score += 5
        reasons.append(f"Drawdown advantage {dd_advantage:+.2f}R")

    score = min(100, int(score))
    qualifies = vip.trades >= 5 and vip.net_r > 0 and hard >= 2 and score >= 75
    return AdvantageDecision(
        score=score,
        hard_conditions=hard,
        qualifies=qualifies,
        strong=qualifies and score >= 85,
        reasons=tuple(reasons),
    )


def _format_money(value: float) -> str:
    sign = "+" if value > 0 else ""
    return f"{sign}${value:,.2f}"


def _format_r(value: float) -> str:
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.2f}R"


def render_public_message(vip: ChannelMetrics, free: ChannelMetrics, decision: AdvantageDecision, *, discount_code: str = "", discount_expires_local: str = "") -> str:
    lines = [
        "<b>📊 NEXUS | VIP PERFORMANCE EDGE</b>",
        "",
        "عملکرد معاملات <b>بسته‌شده</b> در ۷ روز اخیر:",
        "",
        "<b>🟣 VIP</b>",
        f"• Net R: <code>{_format_r(vip.net_r)}</code>",
        f"• Win Rate: <code>{vip.win_rate:.1f}%</code>",
        f"• Profit Factor: <code>{vip.profit_factor:.2f}</code>",
    ]
    if vip.usd_coverage >= 0.60:
        lines.append(f"• PnL ثبت‌شده: <code>{_format_money(vip.net_usd)}</code>")

    lines += [
        "",
        "<b>🔵 FREE</b>",
        f"• Net R: <code>{_format_r(free.net_r)}</code>",
        f"• Win Rate: <code>{free.win_rate:.1f}%</code>",
        f"• Profit Factor: <code>{free.profit_factor:.2f}</code>",
    ]
    if free.usd_coverage >= 0.60:
        lines.append(f"• PnL ثبت‌شده: <code>{_format_money(free.net_usd)}</code>")

    if vip.usd_coverage >= 0.60 and free.usd_coverage >= 0.60:
        lines += ["", f"💵 اختلاف PnL ثبت‌شده: <b>{_format_money(vip.net_usd-free.net_usd)}</b> به نفع VIP"]

    lines += ["", f"⚡ VIP Advantage Score: <b>{decision.score}/100</b>"]

    if discount_code:
        lines += [
            "",
            "<b>🎁 پیشنهاد محدود واقعی</b>",
            "برای این کمپین، تخفیف عضویت VIP فعال شده است:",
            f"<code>{discount_code}</code>",
            f"⏳ اعتبار تا: <b>{discount_expires_local}</b>",
        ]

    lines += [
        "",
        "نتایج بر اساس داده‌های ثبت‌شده معاملات بسته‌شده محاسبه شده‌اند.",
        "<i>عملکرد گذشته تضمینی برای نتایج آینده نیست.</i>",
    ]
    return "\n".join(lines)


def _cta(campaign_id: int, *, discount: bool = False) -> InlineKeyboardMarkup:
    label = "💎 ارتقا به VIP با تخفیف" if discount else "💎 ارتقا به NEXUS VIP"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=f"perfpromo:open:{campaign_id}")]
        ]
    )


def _public_target(main: Any) -> tuple[int, int | None]:
    chat = str(os.getenv("PUBLIC_CHANNEL_CHAT_ID", "") or "").strip()
    if not chat:
        chat = str(getattr(main.settings, "public_channel_id", "") or "").strip()
    if not chat or chat == "0":
        raise RuntimeError("public target is not configured")
    topic_raw = str(os.getenv("PUBLIC_CHANNEL_TOPIC_ID", "") or "").strip()
    topic = int(topic_raw) if topic_raw and topic_raw.lstrip("-").isdigit() else None
    return int(chat), topic


def _create_discount(main: Any, *, percent: float, expires_at: datetime, max_uses: int, prefix: str) -> str:
    ensure_schema(main)
    for _ in range(10):
        code = f"{prefix}{secrets.token_hex(2).upper()}"
        try:
            with main.db.conn() as con:
                con.execute(
                    """
                    INSERT INTO discounts(
                        code,title_fa,title_en,percent,max_uses,used_count,
                        starts_at,expires_at,active,created_by,created_at
                    ) VALUES(?,?,?,?,?,0,?,?,1,NULL,?)
                    """,
                    (
                        code,
                        "تخفیف هوشمند NEXUS VIP",
                        "NEXUS VIP Smart Discount",
                        float(percent),
                        int(max_uses),
                        datetime.now(timezone.utc).isoformat(),
                        expires_at.isoformat(),
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
            return code
        except Exception:
            continue
    raise RuntimeError("unable to allocate unique discount code")


def _recent_auto_discount(main: Any, now: datetime) -> bool:
    cutoff = (now - timedelta(days=_env_int("NEXUS_PERF_DISCOUNT_COOLDOWN_DAYS", 14, 1, 90))).isoformat()
    with main.db.conn() as con:
        row = con.execute(
            """
            SELECT 1 FROM performance_marketing_campaigns
            WHERE discount_percent IS NOT NULL AND created_at>=?
            LIMIT 1
            """,
            (cutoff,),
        ).fetchone()
    return row is not None


def _campaign_exists(main: Any, period_key: str) -> bool:
    with main.db.conn() as con:
        return con.execute(
            "SELECT 1 FROM performance_marketing_campaigns WHERE period_key=? LIMIT 1",
            (period_key,),
        ).fetchone() is not None


def _create_campaign(main: Any, period_key: str, start: datetime, end: datetime, vip: ChannelMetrics, free: ChannelMetrics, decision: AdvantageDecision, *, discount_percent: float | None, public_code: str | None, discount_expires_at: datetime | None) -> int:
    with main.db.conn() as con:
        cur = con.execute(
            """
            INSERT INTO performance_marketing_campaigns(
                period_key,period_start,period_end,score,hard_conditions,
                vip_metrics_json,free_metrics_json,discount_percent,
                public_discount_code,discount_expires_at,status,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                period_key,
                start.isoformat(),
                end.isoformat(),
                decision.score,
                decision.hard_conditions,
                json.dumps(asdict(vip), ensure_ascii=False),
                json.dumps(asdict(free), ensure_ascii=False),
                discount_percent,
                public_code,
                discount_expires_at.isoformat() if discount_expires_at else None,
                "ACTIVE",
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        return int(cur.lastrowid)


def _log_message(main: Any, campaign_id: int, recipient_type: str, telegram_id: int, chat_id: int, message_id: int, *, action: str, delete_at: datetime | None) -> None:
    with main.db.conn() as con:
        con.execute(
            """
            INSERT INTO performance_marketing_messages(
                campaign_id,recipient_type,telegram_id,chat_id,message_id,action,sent_at,delete_at
            ) VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                int(campaign_id), recipient_type, int(telegram_id), int(chat_id),
                int(message_id), action, datetime.now(timezone.utc).isoformat(),
                delete_at.isoformat() if delete_at else None,
            ),
        )


def _public_cooldown_ok(main: Any, now: datetime) -> bool:
    day_cut = (now - timedelta(hours=_env_int("NEXUS_PERF_PUBLIC_COOLDOWN_HOURS", 24, 1, 168))).isoformat()
    week_cut = (now - timedelta(days=7)).isoformat()
    with main.db.conn() as con:
        recent = con.execute(
            "SELECT COUNT(*) FROM performance_marketing_messages WHERE recipient_type='PUBLIC' AND sent_at>=?",
            (day_cut,),
        ).fetchone()[0]
        week = con.execute(
            "SELECT COUNT(*) FROM performance_marketing_messages WHERE recipient_type='PUBLIC' AND sent_at>=?",
            (week_cut,),
        ).fetchone()[0]
    return int(recent) == 0 and int(week) < _env_int("NEXUS_PERF_PUBLIC_MAX_WEEK", 3, 1, 7)


def _private_cooldown_ok(main: Any, telegram_id: int, now: datetime) -> bool:
    hour_cut = (now - timedelta(hours=_env_int("NEXUS_PERF_PRIVATE_COOLDOWN_HOURS", 72, 24, 336))).isoformat()
    week_cut = (now - timedelta(days=7)).isoformat()
    with main.db.conn() as con:
        recent = con.execute(
            "SELECT COUNT(*) FROM performance_marketing_messages WHERE recipient_type='PRIVATE' AND telegram_id=? AND sent_at>=?",
            (int(telegram_id), hour_cut),
        ).fetchone()[0]
        week = con.execute(
            "SELECT COUNT(*) FROM performance_marketing_messages WHERE recipient_type='PRIVATE' AND telegram_id=? AND sent_at>=?",
            (int(telegram_id), week_cut),
        ).fetchone()[0]
    return int(recent) == 0 and int(week) < _env_int("NEXUS_PERF_PRIVATE_MAX_WEEK", 2, 1, 7)


def _eligible_users(main: Any, now: datetime) -> list[int]:
    limit = _env_int("NEXUS_PERF_PRIVATE_BATCH", 50, 1, 500)
    now_iso = now.isoformat()
    with main.db.conn() as con:
        rows = con.execute(
            """
            SELECT u.telegram_id
            FROM users u
            WHERE NOT EXISTS(
                SELECT 1 FROM licenses l
                WHERE l.telegram_id=u.telegram_id
                  AND l.status='active'
                  AND COALESCE(l.vip_access,1)=1
                  AND COALESCE(l.vip_expires_at,l.expires_at)>?
            )
            ORDER BY u.updated_at DESC
            LIMIT ?
            """,
            (now_iso, limit * 3),
        ).fetchall()
    result: list[int] = []
    for row in rows:
        uid = int(row["telegram_id"])
        if main.is_admin(uid):
            continue
        if _private_cooldown_ok(main, uid, now):
            result.append(uid)
        if len(result) >= limit:
            break
    return result


async def _send_public(main: Any, bot: Any, campaign_id: int, text: str, *, discount: bool) -> bool:
    if not _public_cooldown_ok(main, datetime.now(timezone.utc)):
        return False
    chat_id, topic_id = _public_target(main)
    kwargs: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": ParseMode.HTML,
        "disable_web_page_preview": True,
        "reply_markup": _cta(campaign_id, discount=discount),
    }
    if topic_id is not None:
        kwargs["message_thread_id"] = topic_id
    msg = await bot.send_message(**kwargs)
    _log_message(main, campaign_id, "PUBLIC", 0, chat_id, msg.message_id, action="DISCOUNT" if discount else "PERFORMANCE", delete_at=None)
    return True


async def _send_private(main: Any, bot: Any, campaign_id: int, user_id: int, text: str, *, discount_percent: float | None, discount_expires_at: datetime | None) -> bool:
    if not _private_cooldown_ok(main, user_id, datetime.now(timezone.utc)):
        return False

    private_text = text
    delete_at = datetime.now(timezone.utc) + timedelta(hours=_env_int("NEXUS_PERF_PRIVATE_TTL_HOURS", 24, 1, 168))
    discount = discount_percent is not None and discount_expires_at is not None
    if discount:
        personal_code = _create_discount(
            main,
            percent=float(discount_percent),
            expires_at=discount_expires_at,
            max_uses=1,
            prefix="NXV",
        )
        local_exp = discount_expires_at.astimezone(ZoneInfo(main.settings.timezone)).strftime("%Y/%m/%d %H:%M")
        private_text += (
            "\n\n<b>🎁 کد اختصاصی شما</b>\n"
            f"<code>{personal_code}</code>\n"
            f"⏳ اعتبار تا: <b>{local_exp}</b>"
        )
        delete_at = discount_expires_at

    msg = await bot.send_message(
        int(user_id),
        private_text,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        reply_markup=_cta(campaign_id, discount=discount),
    )
    _log_message(
        main, campaign_id, "PRIVATE", int(user_id), int(user_id), msg.message_id,
        action="DISCOUNT" if discount else "PERFORMANCE", delete_at=delete_at
    )
    return True


async def _cleanup_expired_messages(main: Any, bot: Any) -> None:
    now_iso = datetime.now(timezone.utc).isoformat()
    with main.db.conn() as con:
        rows = con.execute(
            """
            SELECT id,chat_id,message_id FROM performance_marketing_messages
            WHERE delete_at IS NOT NULL AND deleted_at IS NULL AND delete_at<=?
            ORDER BY delete_at ASC LIMIT 100
            """,
            (now_iso,),
        ).fetchall()
    for row in rows:
        try:
            await bot.delete_message(int(row["chat_id"]), int(row["message_id"]))
        except Exception:
            pass
        with main.db.conn() as con:
            con.execute(
                "UPDATE performance_marketing_messages SET deleted_at=? WHERE id=?",
                (datetime.now(timezone.utc).isoformat(), int(row["id"])),
            )


async def evaluate_and_dispatch(main: Any, bot: Any, *, local_now: datetime | None = None) -> dict[str, Any]:
    ensure_schema(main)
    tz = ZoneInfo(main.settings.timezone)
    local = local_now or datetime.now(timezone.utc).astimezone(tz)
    end = local.astimezone(timezone.utc)
    start = (local - timedelta(days=7)).astimezone(timezone.utc)
    period_key = f"rolling7:{local.date().isoformat()}"

    if _campaign_exists(main, period_key):
        return {"status": "already_evaluated", "period_key": period_key}

    vip = calculate_channel_metrics(main, start.isoformat(), end.isoformat(), "VIP")
    free = calculate_channel_metrics(main, start.isoformat(), end.isoformat(), "FREE")
    decision = score_advantage(
        vip, free,
        usd_threshold=_env_float("NEXUS_PERF_WEEKLY_USD_ADVANTAGE", 150.0, 0.0, 1_000_000.0),
    )

    if not decision.qualifies:
        main.db.set_setting("performance_marketing_last_evaluation", json.dumps({
            "period_key": period_key, "vip": asdict(vip), "free": asdict(free),
            "decision": asdict(decision),
        }, ensure_ascii=False))
        return {"status": "not_qualified", "period_key": period_key, "score": decision.score}

    now = datetime.now(timezone.utc)
    discount_percent: float | None = None
    public_code: str | None = None
    discount_expires_at: datetime | None = None

    if decision.strong and _env_bool("NEXUS_PERF_AUTO_DISCOUNT_ENABLED", True) and not _recent_auto_discount(main, now):
        discount_percent = _env_float("NEXUS_PERF_DISCOUNT_PERCENT", 15.0, 1.0, 50.0)
        discount_expires_at = now + timedelta(hours=_env_int("NEXUS_PERF_DISCOUNT_HOURS", 6, 1, 72))
        public_code = _create_discount(
            main,
            percent=discount_percent,
            expires_at=discount_expires_at,
            max_uses=_env_int("NEXUS_PERF_PUBLIC_DISCOUNT_MAX_USES", 20, 1, 10000),
            prefix="NXVIP",
        )

    campaign_id = _create_campaign(
        main, period_key, start, end, vip, free, decision,
        discount_percent=discount_percent,
        public_code=public_code,
        discount_expires_at=discount_expires_at,
    )

    local_exp = ""
    if discount_expires_at:
        local_exp = discount_expires_at.astimezone(tz).strftime("%Y/%m/%d %H:%M")
    public_text = render_public_message(
        vip, free, decision,
        discount_code=public_code or "",
        discount_expires_local=local_exp,
    )

    public_sent = False
    private_sent = 0
    try:
        public_sent = await _send_public(main, bot, campaign_id, public_text, discount=bool(public_code))
    except Exception:
        log.exception("[NEXUS][PERF_MARKETING] public delivery failed campaign=%s", campaign_id)

    private_base = render_public_message(vip, free, decision)
    if _env_bool("NEXUS_PERF_PRIVATE_ENABLED", True):
        for uid in _eligible_users(main, now):
            try:
                if await _send_private(
                    main, bot, campaign_id, uid, private_base,
                    discount_percent=discount_percent,
                    discount_expires_at=discount_expires_at,
                ):
                    private_sent += 1
                await asyncio.sleep(0.05)
            except Exception:
                log.exception("[NEXUS][PERF_MARKETING] private delivery failed campaign=%s user=%s", campaign_id, uid)

    log.info(
        "[NEXUS][PERF_MARKETING][DISPATCH] campaign=%s score=%s public=%s private=%s discount=%s",
        campaign_id, decision.score, public_sent, private_sent, bool(public_code),
    )
    return {
        "status": "sent",
        "campaign_id": campaign_id,
        "score": decision.score,
        "public_sent": public_sent,
        "private_sent": private_sent,
        "discount": public_code,
    }


async def performance_marketing_worker(main: Any, bot: Any) -> None:
    tz = ZoneInfo(main.settings.timezone)
    while True:
        try:
            await _cleanup_expired_messages(main, bot)
            if _env_bool("NEXUS_PERF_MARKETING_ENABLED", True):
                local = datetime.now(timezone.utc).astimezone(tz)
                hh, mm = _parse_hm(os.getenv("NEXUS_PERF_PROMO_TIME", "22:30"))
                scheduled = local.replace(hour=hh, minute=mm, second=0, microsecond=0)
                catchup = timedelta(minutes=_env_int("NEXUS_PERF_PROMO_CATCHUP_MINUTES", 90, 5, 360))
                if scheduled <= local <= scheduled + catchup:
                    last_key = str(main.db.get_setting("performance_marketing_worker_last_date", "") or "")
                    today = local.date().isoformat()
                    if last_key != today:
                        result = await evaluate_and_dispatch(main, bot, local_now=local)
                        main.db.set_setting("performance_marketing_worker_last_date", today)
                        log.info("[NEXUS][PERF_MARKETING][EVALUATED] %s", result)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("[NEXUS][PERF_MARKETING][WORKER_FAILURE]")
        await asyncio.sleep(30)


def install(main: Any) -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    ensure_schema(main)

    original_report_worker = main.report_worker

    async def report_and_performance_worker(bot: Any) -> None:
        core = asyncio.create_task(original_report_worker(bot), name="nexus-report-worker")
        perf = asyncio.create_task(performance_marketing_worker(main, bot), name="nexus-performance-marketing")
        try:
            await asyncio.gather(core, perf)
        finally:
            for task in (core, perf):
                if not task.done():
                    task.cancel()
            await asyncio.gather(core, perf, return_exceptions=True)

    main.report_worker = report_and_performance_worker

    @main.router.callback_query(F.data.startswith("perfpromo:open:"))
    async def _performance_promo_open(callback, bot):
        try:
            campaign_id = int(str(callback.data).rsplit(":", 1)[-1])
        except Exception:
            await callback.answer()
            return
        ensure_schema(main)
        with main.db.conn() as con:
            con.execute(
                """
                INSERT INTO performance_marketing_events(
                    campaign_id,telegram_id,event_type,value,created_at
                ) VALUES(?,?,?,?,?)
                """,
                (
                    campaign_id,
                    int(callback.from_user.id),
                    "CTA_CLICK",
                    "vip",
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        await callback.answer("پلن‌های VIP برای شما آماده است.")
        lang = main.get_lang(int(callback.from_user.id))
        text = (
            "<b>💎 NEXUS VIP</b>\n\nپلن موردنظر را برای عضویت یا تمدید انتخاب کنید."
            if lang == "fa"
            else "<b>💎 NEXUS VIP</b>\n\nChoose a plan to subscribe or renew."
        )
        await bot.send_message(
            int(callback.from_user.id),
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(
                        text="💎 مشاهده پلن‌های VIP" if lang == "fa" else "💎 View VIP Plans",
                        callback_data="vip",
                    )]
                ]
            ),
        )

    log.info(
        "[NEXUS][PERF_MARKETING][INSTALLED] time=%s score>=75 strong>=85 public_topic=%s private=%s",
        os.getenv("NEXUS_PERF_PROMO_TIME", "22:30"),
        os.getenv("PUBLIC_CHANNEL_TOPIC_ID", ""),
        _env_bool("NEXUS_PERF_PRIVATE_ENABLED", True),
    )
