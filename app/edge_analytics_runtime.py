from __future__ import annotations

"""Broker-verified NEXUS performance analytics.

Only CLOSE executions reported by MT5 are used for the verified edge report.
Telegram card outcomes are intentionally not treated as proof of execution.
"""

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from aiogram import F
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from . import db

_INSTALLED = False
MIN_EDGE_SAMPLE = 5


@dataclass(frozen=True)
class EdgeMetric:
    label: str
    trades: int
    wins: int
    losses: int
    breakeven: int
    win_rate: float
    total_r: float
    avg_r: float
    profit_factor: float | None


def _r_value(row) -> float | None:
    raw = row.get("realized_r") if isinstance(row, dict) else row["realized_r"]
    if raw is not None:
        return float(raw)
    risk_cash = float((row.get("risk_cash") if isinstance(row, dict) else row["risk_cash"]) or 0.0)
    if risk_cash <= 0:
        return None
    profit = float((row.get("profit") if isinstance(row, dict) else row["profit"]) or 0.0)
    commission = float((row.get("commission") if isinstance(row, dict) else row["commission"]) or 0.0)
    swap = float((row.get("swap") if isinstance(row, dict) else row["swap"]) or 0.0)
    return (profit + commission + swap) / risk_cash


def aggregate_r_values(label: str, values: Iterable[float]) -> EdgeMetric:
    vals = [float(v) for v in values]
    wins = sum(1 for v in vals if v > 0)
    losses = sum(1 for v in vals if v < 0)
    be = len(vals) - wins - losses
    positives = sum(v for v in vals if v > 0)
    negatives = abs(sum(v for v in vals if v < 0))
    pf = None if negatives == 0 else round(positives / negatives, 2)
    total = round(sum(vals), 2)
    avg = round(total / len(vals), 2) if vals else 0.0
    wr = round((wins / len(vals) * 100.0), 1) if vals else 0.0
    return EdgeMetric(label, len(vals), wins, losses, be, wr, total, avg, pf)


def verified_edge_snapshot() -> dict:
    with db.conn() as con:
        rows = con.execute(
            """
            SELECT e.realized_r,e.risk_cash,e.profit,e.commission,e.swap,
                   COALESCE(s.symbol,e.symbol,'UNKNOWN') AS symbol,
                   COALESCE(s.timeframe,'UNKNOWN') AS timeframe,
                   COALESCE(s.direction,e.direction,'UNKNOWN') AS direction,
                   COALESCE(s.trailing_code,'NONE') AS trailing_code
            FROM autotrade_trade_executions e
            LEFT JOIN signals s ON s.id=e.signal_id
            WHERE UPPER(e.event_type)='CLOSE'
              AND (e.realized_r IS NOT NULL OR COALESCE(e.risk_cash,0)>0)
            ORDER BY e.created_at ASC,e.id ASC
            """
        ).fetchall()

    normalized: list[dict] = []
    for row in rows:
        item = dict(row)
        r = _r_value(item)
        if r is None:
            continue
        item["r"] = float(r)
        normalized.append(item)

    overall = aggregate_r_values("ALL", [x["r"] for x in normalized])
    groups: dict[str, list[float]] = defaultdict(list)
    for item in normalized:
        groups[f"SYMBOL:{item['symbol']}"] .append(item["r"])
        groups[f"TF:{item['timeframe']}"] .append(item["r"])
        groups[f"DIR:{item['direction']}"] .append(item["r"])
        if str(item.get("trailing_code") or "NONE") != "NONE":
            groups[f"TRAIL:{item['trailing_code']}"] .append(item["r"])

    metrics = [aggregate_r_values(label, values) for label, values in groups.items()]
    qualified = [m for m in metrics if m.trades >= MIN_EDGE_SAMPLE]
    qualified.sort(key=lambda m: (m.avg_r, m.total_r, m.trades), reverse=True)
    weakest = sorted(qualified, key=lambda m: (m.avg_r, m.total_r, -m.trades))

    return {
        "verified_trades": len(normalized),
        "overall": overall,
        "best_edges": qualified[:5],
        "weak_edges": weakest[:3],
        "minimum_sample": MIN_EDGE_SAMPLE,
    }


def _fmt_pf(value: float | None) -> str:
    return "∞" if value is None else f"{value:.2f}"


def install(main_module) -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    original_reports_menu = main_module.admin_reports_group

    def _reports_menu_with_edge(lang: str) -> InlineKeyboardMarkup:
        base = original_reports_menu(lang)
        rows = [list(row) for row in base.inline_keyboard]
        label = "📈 Edge واقعی / عملکرد" if lang == "fa" else "📈 Verified Edge / Performance"
        rows.insert(0, [InlineKeyboardButton(text=label, callback_data="admin_verified_edge")])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    main_module.admin_reports_group = _reports_menu_with_edge

    @main_module.router.callback_query(F.data == "admin_verified_edge")
    async def admin_verified_edge(cb, bot):
        if not main_module.is_admin(cb.from_user.id):
            await cb.answer()
            return
        snap = verified_edge_snapshot()
        overall: EdgeMetric = snap["overall"]
        lang = main_module.get_lang(cb.from_user.id)
        if overall.trades == 0:
            text = (
                "<b>📈 Edge واقعی NEXUS</b>\n\nهنوز معامله بسته‌شده و تأییدشده توسط MT5 برای اثبات عملکرد وجود ندارد.\n\nاین گزارش عمداً از نتایج صرفاً تلگرامی استفاده نمی‌کند."
                if lang == "fa" else
                "<b>📈 Verified NEXUS Edge</b>\n\nThere are no broker-confirmed closed MT5 trades yet.\n\nThis report intentionally does not treat Telegram-only outcomes as execution proof."
            )
        else:
            best_lines = []
            for m in snap["best_edges"]:
                best_lines.append(
                    f"• {m.label} | n={m.trades} | WR={m.win_rate:.1f}% | Avg={m.avg_r:+.2f}R | PF={_fmt_pf(m.profit_factor)}"
                )
            weak_lines = []
            for m in snap["weak_edges"]:
                weak_lines.append(
                    f"• {m.label} | n={m.trades} | Avg={m.avg_r:+.2f}R"
                )
            if lang == "fa":
                text = (
                    "<b>📈 عملکرد تأییدشده توسط Broker</b>\n\n"
                    f"معاملات بسته‌شده: <b>{overall.trades}</b>\n"
                    f"Win Rate: <b>{overall.win_rate:.1f}%</b>\n"
                    f"Total R: <b>{overall.total_r:+.2f}R</b>\n"
                    f"Average R: <b>{overall.avg_r:+.2f}R</b>\n"
                    f"Profit Factor: <b>{_fmt_pf(overall.profit_factor)}</b>\n\n"
                    f"<b>Edgeهای معتبر (حداقل {snap['minimum_sample']} نمونه)</b>\n"
                    + ("\n".join(best_lines) if best_lines else "هنوز Sample کافی نیست.")
                    + "\n\n<b>ضعیف‌ترین Segmentها</b>\n"
                    + ("\n".join(weak_lines) if weak_lines else "—")
                    + "\n\nمبنای گزارش: فقط CLOSEهای ثبت‌شده از MT5."
                )
            else:
                text = (
                    "<b>📈 Broker-Verified Performance</b>\n\n"
                    f"Closed trades: <b>{overall.trades}</b>\n"
                    f"Win rate: <b>{overall.win_rate:.1f}%</b>\n"
                    f"Total R: <b>{overall.total_r:+.2f}R</b>\n"
                    f"Average R: <b>{overall.avg_r:+.2f}R</b>\n"
                    f"Profit factor: <b>{_fmt_pf(overall.profit_factor)}</b>\n\n"
                    f"<b>Qualified edges (min {snap['minimum_sample']} samples)</b>\n"
                    + ("\n".join(best_lines) if best_lines else "Not enough sample yet.")
                    + "\n\n<b>Weakest segments</b>\n"
                    + ("\n".join(weak_lines) if weak_lines else "—")
                    + "\n\nSource of truth: MT5 CLOSE executions only."
                )
        await cb.answer()
        await main_module.screen(
            bot,
            cb.from_user.id,
            cb.message.chat.id,
            text,
            InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text="⬅️ بازگشت" if lang == "fa" else "⬅️ Back",
                    callback_data="admin_group_reports",
                )
            ]]),
        )

    _INSTALLED = True
