from __future__ import annotations

"""Broker-truth Telegram lifecycle bridge for automatic MT5 UPDATE events.

The legacy core handler persisted MT5 SL/TP changes but did not publish them to
Telegram. It also treated live-snapshot volume changes as ordinary UPDATEs,
which meant partial closes were silently ignored because neither SL nor TP had
changed.

This runtime patch keeps MT5/broker data authoritative while reusing the
existing per-signal Telegram reply-chain primitive. Partial-close Telegram
messages are emitted only when the EA marks the event as an explicit broker
deal partial (``close_reason=PARTIAL``); floating live PnL is never presented as
realized stage PnL.
"""

import json
import logging
import os
from typing import Any

from .. import db

log = logging.getLogger("nexus-telegram-lifecycle-truth")
_INSTALLED = False
_ORIGINAL_PROCESS = None


def _f(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _resolve_row(telegram_id: int, payload: dict[str, Any]):
    signal_id = str(payload.get("signal_id") or "").strip()
    ticket = str(payload.get("ticket") or "").strip()
    row = None
    if signal_id:
        row = db.get_signal_by_autotrade_signal_id(int(telegram_id), signal_id)
    if not row and ticket:
        row = db.get_signal_by_autotrade_ticket(int(telegram_id), ticket)
    if not row and signal_id:
        row = db.get_signal_by_publish_token(signal_id)
    return row


def _display_code(row) -> str:
    """Return the human-facing code without changing broker correlation identity."""
    fallback = str(row["code"] or "")
    try:
        with db.conn() as con:
            exists = con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='signal_public_codes'"
            ).fetchone()
            if not exists:
                return fallback
            mapped = con.execute(
                "SELECT public_code FROM signal_public_codes WHERE signal_id=? LIMIT 1",
                (int(row["id"]),),
            ).fetchone()
            if mapped and str(mapped["public_code"] or "").strip():
                return str(mapped["public_code"]).strip()
    except Exception:
        log.exception("[NEXUS][LIFECYCLE] public display-code lookup failed for signal=%s", row["id"])
    return fallback


def _first_target(signal_id: int) -> float:
    try:
        targets = db.get_signal_targets(int(signal_id))
        if targets:
            return _f(targets[0]["price"])
    except Exception:
        pass
    return 0.0


def _initial_volume(row, telegram_id: int, ticket: str) -> float:
    lot = _f(row["lot_size"] if "lot_size" in row.keys() else 0.0)
    if lot > 0:
        return lot
    try:
        with db.conn() as con:
            execution = con.execute(
                "SELECT volume FROM autotrade_trade_executions "
                "WHERE telegram_id=? AND ticket=? AND event_type='OPEN' AND volume>0 "
                "ORDER BY id ASC LIMIT 1",
                (int(telegram_id), str(ticket)),
            ).fetchone()
            if execution and _f(execution["volume"]) > 0:
                return _f(execution["volume"])
            live = con.execute(
                "SELECT volume FROM mt5_live_state WHERE ticket=? AND state_type='POSITION' "
                "AND nexus_managed=1 ORDER BY last_seen_at DESC LIMIT 1",
                (str(ticket),),
            ).fetchone()
            if live and _f(live["volume"]) > 0:
                return _f(live["volume"])
    except Exception:
        pass
    return 0.0


def _prior_partial_closed(signal_id: int) -> float:
    total = 0.0
    try:
        for row in db.signal_updates(int(signal_id)):
            if str(row["action"] or "").upper() != "MT5_PARTIAL_CLOSE":
                continue
            raw = str(row["value"] or "").strip()
            if not raw:
                continue
            try:
                value = json.loads(raw)
            except json.JSONDecodeError:
                continue
            total += max(0.0, _f(value.get("closed_volume")))
    except Exception:
        return total
    return total


def _money(value: float) -> str:
    currency = str(os.getenv("NEXUS_PNL_CURRENCY", "") or "").strip().upper()
    if currency == "USD":
        return f"${value:+.2f}"
    if currency:
        return f"{value:+.2f} {currency}"
    return f"{value:+.2f} (account currency)"


def _delivery_required(row, channel: str) -> bool:
    destination = str(row["destination"] or "BOTH").upper()
    if channel == "FREE":
        return destination in {"FREE", "BOTH"} and bool(row["free_message_id"])
    return destination in {"VIP", "BOTH"} and bool(row["vip_message_id"])


def _assert_delivery(row, free_mid, vip_mid, errors: list[str]) -> None:
    missing = []
    if _delivery_required(row, "FREE") and not free_mid:
        missing.append("FREE")
    if _delivery_required(row, "VIP") and not vip_mid:
        missing.append("VIP")
    if missing:
        detail = "; ".join(errors) if errors else "no Telegram message id returned"
        raise RuntimeError(f"Telegram lifecycle reply failed for {','.join(missing)}: {detail}")


async def _handle_update(main, bot, notification, payload: dict[str, Any]) -> bool:
    uid = int(notification["telegram_id"])
    row = _resolve_row(uid, payload)
    if not row:
        return False

    ticket = str(payload.get("ticket") or "").strip()
    event_id = str(payload.get("event_id") or f"UPDATE:{ticket}").strip()
    source = str(payload.get("change_source") or "").strip().upper()
    close_reason = str(payload.get("close_reason") or "").strip().upper()

    sl = _f(payload.get("stop_loss"))
    tp = _f(payload.get("take_profit"))
    old_sl = _f(row["stop_loss"])
    old_tp = _first_target(int(row["id"]))
    sl_changed = sl > 0 and abs(sl - old_sl) > 1e-12
    tp_changed = tp > 0 and abs(tp - old_tp) > 1e-12
    explicit_partial = close_reason in {"PARTIAL", "PARTIAL_CLOSE"}

    # Live snapshots can prove volume changed but their ``profit`` is floating
    # position PnL. Never label it as the realized profit of the partial deal.
    # The upgraded EA sends a separate broker-deal UPDATE with PARTIAL reason.
    if source == "LIVE_SNAPSHOT_VOLUME" and not explicit_partial:
        db.update_trade_execution(
            uid, ticket, event_id, signal_id=int(row["id"]),
            status="IGNORED", destination=str(row["destination"]),
            error_text="awaiting broker-deal partial truth",
        )
        return True

    display_code = _display_code(row)
    current_sl = sl if sl > 0 else old_sl
    current_tp = tp if tp > 0 else old_tp

    if explicit_partial:
        closed_volume = max(0.0, _f(payload.get("volume")))
        if closed_volume <= 0:
            raise ValueError("broker partial event requires positive closed volume")

        stage_profit = _f(payload.get("profit"))
        initial_volume = _initial_volume(row, uid, ticket)
        prior_closed = _prior_partial_closed(int(row["id"]))
        if initial_volume > 0:
            remaining_volume = max(0.0, initial_volume - prior_closed - closed_volume)
            closed_pct = closed_volume / initial_volume * 100.0
            remaining_pct = remaining_volume / initial_volume * 100.0
        else:
            remaining_volume = 0.0
            closed_pct = remaining_pct = 0.0

        fa = (
            "🔄 <b>NEXUS | POSITION UPDATE</b>\n\n"
            "<b>Partial Close Executed</b>\n\n"
            f"Signal: <b>{main.escape(display_code)}</b>\n"
            f"Closed Volume: <code>{closed_volume:g}</code>\n"
            f"Closed: <code>{closed_pct:.1f}%</code>\n"
            f"Remaining Volume: <code>{remaining_volume:g}</code>\n"
            f"Remaining: <code>{remaining_pct:.1f}%</code>\n"
            f"Stage Profit: <code>{_money(stage_profit)}</code>\n"
            f"SL: <code>{main._copy_price(current_sl)}</code>\n"
            f"TP: <code>{main._copy_price(current_tp)}</code>\n\n"
            "Position Status: <b>ACTIVE</b>"
        )
        en = fa
        text = main.tr(main.get_lang(uid), fa, en)

        free_mid, vip_mid, errors = await main._reply_signal_update(bot, row, text)
        _assert_delivery(row, free_mid, vip_mid, errors)

        if sl_changed:
            db.update_signal_sl(int(row["id"]), sl)
        if tp_changed:
            db.update_signal_tp(int(row["id"]), 1, tp)

        value = json.dumps(
            {
                "event_id": event_id,
                "closed_volume": closed_volume,
                "remaining_volume": remaining_volume,
                "stage_profit": stage_profit,
                "gross_profit": _f(payload.get("gross_profit")),
                "commission": _f(payload.get("commission")),
                "swap": _f(payload.get("swap")),
                "exit_price": _f(payload.get("exit_price")),
                "sl": current_sl,
                "tp": current_tp,
            },
            separators=(",", ":"),
        )
        db.add_signal_event(
            int(row["id"]), "PARTIAL_CLOSE", actor_type="MT5", actor_id=uid,
            account_number=str(payload.get("account_number") or ""),
            correlation_id=str(row["code"]), payload=json.loads(value),
        )
        db.add_signal_update(
            int(row["id"]), "MT5_PARTIAL_CLOSE", text, text, value, uid,
            free_mid, vip_mid, "ACTIVE",
        )
        db.update_trade_execution(
            uid, ticket, event_id, signal_id=int(row["id"]), status="PARTIAL",
            destination=str(row["destination"]),
        )
        db.add_audit(
            uid, "mt5_partial_close", int(row["id"]),
            f"ticket={ticket} closed={closed_volume:g} stage_profit={stage_profit:+.2f}",
        )
        return True

    if not sl_changed and not tp_changed:
        return False

    parts_fa = []
    parts_en = []
    if sl_changed:
        be = abs(sl - _f(row["entry_price"])) <= max(1e-8, abs(_f(row["entry_price"])) * 1e-7)
        label = "🟡 <b>BE ACTIVATED</b>" if be else "🛑 <b>SL CHANGED</b>"
        parts_fa.append(f"{label}\nOld: {main._copy_price(old_sl)}\nNew: {main._copy_price(sl)}")
        parts_en.append(f"{label}\nOld: {main._copy_price(old_sl)}\nNew: {main._copy_price(sl)}")
    if tp_changed:
        parts_fa.append(f"🎯 <b>TP CHANGED</b>\nOld: {main._copy_price(old_tp)}\nNew: {main._copy_price(tp)}")
        parts_en.append(f"🎯 <b>TP CHANGED</b>\nOld: {main._copy_price(old_tp)}\nNew: {main._copy_price(tp)}")

    suffix = (
        f"\n\nCurrent SL: <code>{main._copy_price(current_sl)}</code>"
        f"\nCurrent TP: <code>{main._copy_price(current_tp)}</code>"
        "\nPosition Status: <b>ACTIVE</b>"
    )
    fa = f"🔄 <b>NEXUS | POSITION UPDATE</b>\n\n<b>{main.escape(display_code)}</b>\n" + "\n\n".join(parts_fa) + suffix
    en = f"🔄 <b>NEXUS | POSITION UPDATE</b>\n\n<b>{main.escape(display_code)}</b>\n" + "\n\n".join(parts_en) + suffix
    text = main.tr(main.get_lang(uid), fa, en)

    free_mid, vip_mid, errors = await main._reply_signal_update(bot, row, text)
    _assert_delivery(row, free_mid, vip_mid, errors)

    if sl_changed:
        db.update_signal_sl(int(row["id"]), sl)
    if tp_changed:
        db.update_signal_tp(int(row["id"]), 1, tp)

    value = json.dumps(
        {"event_id": event_id, "sl": current_sl, "tp": current_tp},
        separators=(",", ":"),
    )
    db.add_signal_event(
        int(row["id"]), "UPDATE", actor_type="MT5", actor_id=uid,
        account_number=str(payload.get("account_number") or ""),
        correlation_id=str(row["code"]),
        payload={"sl_changed": sl_changed, "tp_changed": tp_changed, "sl": current_sl, "tp": current_tp},
    )
    db.add_signal_update(
        int(row["id"]), "MT5_UPDATE", text, text, value, uid,
        free_mid, vip_mid, "ACTIVE",
    )
    db.update_trade_execution(
        uid, ticket, event_id, signal_id=int(row["id"]), status="UPDATED",
        destination=str(row["destination"]),
    )
    db.add_audit(
        uid, "mt5_trade_update", int(row["id"]),
        f"ticket={ticket} sl={current_sl:g} tp={current_tp:g}",
    )
    return True


def install_telegram_lifecycle_truth(main) -> None:
    global _INSTALLED, _ORIGINAL_PROCESS
    if _INSTALLED:
        return

    original = main._process_mt5_trade_event
    _ORIGINAL_PROCESS = original

    async def wrapped(bot, notification, payload: dict[str, Any]):
        if str(payload.get("event") or "").upper().strip() == "UPDATE":
            handled = await _handle_update(main, bot, notification, payload)
            if handled:
                return None
        return await original(bot, notification, payload)

    wrapped.__name__ = "process_mt5_trade_event_lifecycle_truth"
    main._process_mt5_trade_event = wrapped
    _INSTALLED = True


__all__ = ["install_telegram_lifecycle_truth"]
