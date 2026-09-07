from __future__ import annotations

"""Unified NEXUS channel-report runtime.

The legacy report split performance into CRYPTO and FOREX buckets. XAUUSD is
stored by the execution pipeline as market_type=GOLD, so a valid closed Gold
trade was excluded from both buckets and the public report incorrectly showed
zero trades. This runtime replaces that market-type-dependent aggregation with
publication-channel truth: every actually published signal is counted in one
unified report regardless of market_type.
"""

import asyncio
import html
import logging
from datetime import datetime, timedelta
from typing import Any

from aiogram.enums import ParseMode


log = logging.getLogger(__name__)


def _allowed_destinations(audience: str | None) -> tuple[str, str] | None:
    if audience is None:
        return None
    audience = audience.upper().strip()
    if audience == "FREE":
        return ("FREE", "BOTH")
    if audience == "VIP":
        return ("VIP", "BOTH")
    raise ValueError("audience must be FREE, VIP or None")


def _publication_predicate(audience: str | None) -> str:
    if audience == "FREE":
        return "free_message_id IS NOT NULL"
    if audience == "VIP":
        return "vip_message_id IS NOT NULL"
    return "(free_message_id IS NOT NULL OR vip_message_id IS NOT NULL)"


def unified_report_stats(main: Any, start_iso: str, end_iso: str, audience: str | None) -> dict[str, Any]:
    """Return one market-agnostic summary based on durable publication/close truth."""
    audience = audience.upper().strip() if audience else None
    allowed = _allowed_destinations(audience)
    publication = _publication_predicate(audience)

    destination_sql = ""
    destination_args: list[Any] = []
    if allowed:
        destination_sql = " AND destination IN (?,?)"
        destination_args.extend(allowed)

    with main.db.conn() as con:
        issued = int(
            con.execute(
                f"""SELECT COUNT(*) FROM signals
                    WHERE created_at>=? AND created_at<?
                      AND {publication}
                      AND UPPER(COALESCE(status,''))<>'REJECTED'
                      {destination_sql}""",
                (start_iso, end_iso, *destination_args),
            ).fetchone()[0]
        )

        closed_rows = list(
            con.execute(
                f"""SELECT s.id, s.result_value,
                           (SELECT e.profit
                              FROM autotrade_trade_executions e
                             WHERE e.signal_id=s.id AND UPPER(COALESCE(e.event_type,''))='CLOSE'
                             ORDER BY e.created_at DESC, e.id DESC
                             LIMIT 1) AS broker_pnl
                      FROM signals s
                     WHERE UPPER(COALESCE(s.status,''))='CLOSED'
                       AND s.closed_at>=? AND s.closed_at<?
                       AND {publication}
                       {destination_sql}
                     ORDER BY s.closed_at, s.id""",
                (start_iso, end_iso, *destination_args),
            ).fetchall()
        )

    wins = losses = be = 0
    broker_pnl = 0.0
    pnl_rows = 0
    for row in closed_rows:
        value = float(row["result_value"] or 0)
        if value > 0:
            wins += 1
        elif value < 0:
            losses += 1
        else:
            be += 1
        if row["broker_pnl"] is not None:
            broker_pnl += float(row["broker_pnl"] or 0)
            pnl_rows += 1

    closed = len(closed_rows)
    return {
        "issued": issued,
        "closed": closed,
        "wins": wins,
        "losses": losses,
        "be": be,
        "win_rate": round((wins / closed * 100) if closed else 0.0, 1),
        "broker_pnl": round(broker_pnl, 2),
        "broker_pnl_available": pnl_rows,
    }


def _period_labels(kind: str, start_local: datetime, end_local: datetime) -> tuple[str, str]:
    end_day = (end_local - timedelta(seconds=1)).date()
    if kind == "daily":
        return start_local.date().strftime("%Y/%m/%d"), start_local.date().isoformat()
    return (
        f"{start_local.date().strftime('%Y/%m/%d')} تا {end_day.strftime('%Y/%m/%d')}",
        f"{start_local.date().isoformat()} to {end_day.isoformat()}",
    )


def render_channel_report(
    main: Any,
    kind: str,
    start_local: datetime,
    end_local: datetime,
    lang: str,
    audience: str,
) -> str:
    start_iso, end_iso = main._period_utc(start_local, end_local)
    st = unified_report_stats(main, start_iso, end_iso, audience)
    period_fa, period_en = _period_labels(kind, start_local, end_local)
    audience = audience.upper()
    audience_fa = "FREE" if audience == "FREE" else "VIP"
    audience_en = audience_fa
    title_fa = "گزارش روزانه" if kind == "daily" else "گزارش هفتگی"
    title_en = "Daily Report" if kind == "daily" else "Weekly Report"
    pnl_fa = f"{st['broker_pnl']:+.2f}" if st["broker_pnl_available"] else "—"
    pnl_en = pnl_fa

    fa = (
        f"<b>📊 NEXUS {title_fa} — {audience_fa}</b>\n"
        f"📅 {period_fa}\n\n"
        f"📨 سیگنال‌های صادرشده: <b>{st['issued']}</b>\n"
        f"🏁 معاملات بسته‌شده: <b>{st['closed']}</b>\n"
        f"🟢 WIN: <b>{st['wins']}</b>\n"
        f"🔴 LOSS: <b>{st['losses']}</b>\n"
        f"⚪ BREAK EVEN: <b>{st['be']}</b>\n"
        f"🎯 Win Rate: <b>{st['win_rate']}%</b>\n"
        f"💰 Broker P/L: <b>{html.escape(pnl_fa)}</b>"
    )
    en = (
        f"<b>📊 NEXUS {title_en} — {audience_en}</b>\n"
        f"📅 {period_en}\n\n"
        f"📨 Signals issued: <b>{st['issued']}</b>\n"
        f"🏁 Closed trades: <b>{st['closed']}</b>\n"
        f"🟢 WIN: <b>{st['wins']}</b>\n"
        f"🔴 LOSS: <b>{st['losses']}</b>\n"
        f"⚪ BREAK EVEN: <b>{st['be']}</b>\n"
        f"🎯 Win Rate: <b>{st['win_rate']}%</b>\n"
        f"💰 Broker P/L: <b>{html.escape(pnl_en)}</b>"
    )
    return main.tr(lang, fa, en)


def render_admin_report(
    main: Any,
    kind: str,
    start_local: datetime,
    end_local: datetime,
    lang: str,
    *,
    partial: bool = False,
) -> str:
    """Keep the private business section available for explicit admin use."""
    start_iso, end_iso = main._period_utc(start_local, end_local)
    st = unified_report_stats(main, start_iso, end_iso, None)
    business = main.db.trading_report_stats(start_iso, end_iso)
    period_fa, period_en = _period_labels(kind, start_local, end_local)
    if partial:
        period_fa += " — تا این لحظه"
        period_en += " — so far"
    pnl = f"{st['broker_pnl']:+.2f}" if st["broker_pnl_available"] else "—"

    fa = (
        f"<b>📊 گزارش {'روزانه' if kind == 'daily' else 'هفتگی'} NEXUS</b>\n"
        f"{period_fa}\n\n"
        f"<b>عملکرد کلی سیگنال‌ها</b>\n"
        f"سیگنال‌های صادرشده: <b>{st['issued']}</b>\n"
        f"معاملات بسته‌شده: <b>{st['closed']}</b>\n"
        f"WIN: <b>{st['wins']}</b>\n"
        f"LOSS: <b>{st['losses']}</b>\n"
        f"BREAK EVEN: <b>{st['be']}</b>\n"
        f"Win Rate: <b>{st['win_rate']}%</b>\n"
        f"Broker P/L: <b>{html.escape(pnl)}</b>\n\n"
        f"<b>کسب‌وکار</b>\n"
        f"کاربران جدید: <b>{business['new_users']}</b>\n"
        f"اشتراک جدید/تمدید: <b>{business['vip_activations']}</b>\n"
        f"پرداخت تأییدشده: <b>{business['approved_payments']}</b>\n"
        f"فروش: <b>{business['revenue_usdt']:g} USDT</b>"
    )
    en = (
        f"<b>📊 NEXUS {'Daily' if kind == 'daily' else 'Weekly'} Report</b>\n"
        f"{period_en}\n\n"
        f"<b>Overall Signal Performance</b>\n"
        f"Signals issued: <b>{st['issued']}</b>\n"
        f"Closed trades: <b>{st['closed']}</b>\n"
        f"WIN: <b>{st['wins']}</b>\n"
        f"LOSS: <b>{st['losses']}</b>\n"
        f"BREAK EVEN: <b>{st['be']}</b>\n"
        f"Win Rate: <b>{st['win_rate']}%</b>\n"
        f"Broker P/L: <b>{html.escape(pnl)}</b>\n\n"
        f"<b>Business</b>\n"
        f"New users: <b>{business['new_users']}</b>\n"
        f"New/Renewed subscriptions: <b>{business['vip_activations']}</b>\n"
        f"Approved payments: <b>{business['approved_payments']}</b>\n"
        f"Revenue: <b>{business['revenue_usdt']:g} USDT</b>"
    )
    return main.tr(lang, fa, en)


def channel_targets(main: Any, audience: str) -> tuple[Any, ...]:
    """Canonical report routing required by product policy.

    FREE report -> Free channel and NEXUS public channel.
    VIP report  -> VIP channel and NEXUS public channel.
    """
    audience = audience.upper().strip()
    raw = (
        (main.settings.free_channel_target, main.settings.public_channel_id)
        if audience == "FREE"
        else (main.settings.vip_channel_id, main.settings.public_channel_id)
    )
    unique: list[Any] = []
    seen: set[str] = set()
    for target in raw:
        key = str(target)
        if key in seen:
            continue
        seen.add(key)
        unique.append(target)
    return tuple(unique)


async def send_channel_report(
    main: Any,
    bot: Any,
    kind: str,
    period_key: str,
    start_local: datetime,
    end_local: datetime,
) -> None:
    if not main.settings.channel_reports_enabled:
        return

    lang = main.settings.channel_content_language
    start_iso, end_iso = main._period_utc(start_local, end_local)

    for audience in ("FREE", "VIP"):
        text = await asyncio.to_thread(
            render_channel_report,
            main,
            kind,
            start_local,
            end_local,
            lang,
            audience,
        )
        for target in channel_targets(main, audience):
            report_type = f"{kind}_channel_v3_{audience.lower()}"
            recipient_key = str(target)
            if not main.db.claim_report_dispatch(
                report_type,
                period_key,
                recipient_key,
                start_iso,
                end_iso,
            ):
                continue
            try:
                await bot.send_message(
                    target,
                    text,
                    parse_mode=ParseMode.HTML,
                    protect_content=True,
                )
                main.db.mark_report_sent(
                    report_type,
                    period_key,
                    recipient_key,
                    start_iso,
                    end_iso,
                )
            except Exception as exc:
                main.db.release_report_dispatch(report_type, period_key, recipient_key)
                log.warning(
                    "%s %s report failed for target=%s: %s",
                    audience,
                    kind,
                    target,
                    exc,
                )


def install(main: Any) -> None:
    """Install unified channel routing and suppress automatic private signal reports."""
    main._channel_report_caption = lambda kind, start_local, end_local, lang: render_channel_report(
        main, kind, start_local, end_local, lang, "FREE"
    )
    main._admin_report_text = lambda kind, start_local, end_local, lang, partial=False: render_admin_report(
        main,
        kind,
        start_local,
        end_local,
        lang,
        partial=partial,
    )

    async def patched_send_channel_report(bot, kind, period_key, start_local, end_local):
        await send_channel_report(main, bot, kind, period_key, start_local, end_local)

    async def patched_send_scheduled_report(bot, kind, period_key, start_local, end_local):
        # Product policy: scheduled FREE/VIP performance reports are channel
        # content, not private bot messages. Explicit admin reports remain
        # available through the admin UI, but the automatic worker publishes
        # only to the designated signal/public channels.
        await send_channel_report(main, bot, kind, period_key, start_local, end_local)

    main._send_channel_report = patched_send_channel_report
    main._send_scheduled_report = patched_send_scheduled_report
    log.info(
        "[NEXUS][REPORT_RUNTIME][INSTALLED] channel-only scheduled reports: "
        "FREE->free+public VIP->vip+public"
    )
