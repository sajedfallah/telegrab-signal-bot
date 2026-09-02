from __future__ import annotations

"""Delivery-safe bridge for broker history reconciliation.

NEXUS has two independent truths for a closed position:
1. broker/execution truth (the position is really closed), and
2. Telegram lifecycle delivery truth (the close result was actually replied to
   the original channel signal).

The legacy history reconciliation path may repair (1) by marking a signal
CLOSED without creating (2).  If the event-driven CLOSE arrives afterwards,
app.main historically returned immediately because the signal was already
CLOSED.  The result reply was therefore lost permanently.

This compatibility guard keeps broker truth authoritative while ensuring a
history-repaired CLOSE with *no* prior Telegram close reply is put back through
the durable MT5_TRADE_EVENT queue.  The temporary CLOSING state is deliberately
not eligible for new AutoTrade polling (only ACTIVE is), but allows the normal
CLOSE worker to publish/retry the final reply and then atomically finalize the
signal as CLOSED.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from .. import db

log = logging.getLogger("nexus-close-reply-guard")
_INSTALLED = False
_ORIGINAL_RECONCILE = None


def _as_dict(item: Any) -> dict:
    if isinstance(item, dict):
        return dict(item)
    if hasattr(item, "model_dump"):
        return dict(item.model_dump())
    return {}


def _resolve_signal(telegram_id: int, item: dict):
    token = str(item.get("signal_id") or "").strip()
    ticket = str(item.get("ticket") or "").strip()

    row = None
    if token:
        row = db.get_signal_by_publish_token(token)
        if not row:
            row = db.get_signal_by_code(token)
    if not row and ticket:
        row = db.get_signal_by_autotrade_ticket(int(telegram_id), ticket)
    if not row and ticket:
        # History reconciliation itself links the execution row to signal_id.
        # Use that durable broker identity as the final fallback.
        with db.conn() as con:
            row = con.execute(
                """SELECT s.* FROM signals s
                   JOIN autotrade_trade_executions e ON e.signal_id=s.id
                   WHERE e.telegram_id=? AND e.ticket=? AND e.event_type='CLOSE'
                   ORDER BY e.id DESC LIMIT 1""",
                (int(telegram_id), ticket),
            ).fetchone()
    return row


def _has_close_reply(signal_id: int) -> bool:
    """Return True only when a CLOSE lifecycle reply has a Telegram message id."""
    for update in db.signal_updates(int(signal_id)):
        action = str(update["action"] or "").upper()
        if action not in {"MT5_CLOSE", "CLOSE"}:
            continue
        if update["free_message_id"] is not None or update["vip_message_id"] is not None:
            return True
    return False


def _event_time_ms(item: dict) -> int:
    raw = int(item.get("event_time_ms") or 0)
    if raw > 0:
        return raw
    text = str(item.get("event_time") or "").strip()
    if not text:
        return 0
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0, int(dt.timestamp() * 1000))
    except (TypeError, ValueError, OverflowError):
        return 0


def _close_payload(item: dict, row) -> dict:
    ticket = str(item.get("ticket") or "").strip()
    return {
        "event": "CLOSE",
        "ticket": ticket,
        "signal_id": str(row["code"]),
        "symbol": str(item.get("symbol") or row["symbol"] or "").upper(),
        "direction": str(item.get("direction") or row["direction"] or "").upper(),
        "volume": float(item.get("volume") or 0),
        "entry_price": float(item.get("entry_price") or row["entry_price"] or 0),
        "stop_loss": float(item.get("stop_loss") or row["stop_loss"] or 0),
        "take_profit": float(item.get("take_profit") or 0),
        "exit_price": float(item.get("exit_price") or row["exit_price"] or 0),
        "profit": float(item.get("profit") or row["result_value"] or 0),
        "gross_profit": float(item.get("gross_profit") or item.get("profit") or 0),
        "commission": float(item.get("commission") or 0),
        "swap": float(item.get("swap") or 0),
        "slippage": float(item.get("slippage") or 0),
        "risk_cash": float(item.get("risk_cash") or 0),
        "realized_r": item.get("realized_r"),
        "position_id": str(item.get("position_id") or ""),
        "deal_id": str(item.get("deal_id") or ticket),
        "cycle_id": str(item.get("cycle_id") or ""),
        "event_id": str(item.get("event_id") or f"HISTORY-CLOSE:{ticket}"),
        "event_time_ms": _event_time_ms(item),
        "destination": str(row["destination"] or item.get("destination") or "BOTH").upper(),
        "close_reason": str(item.get("close_reason") or "HISTORY_RECONCILE").upper(),
    }


def install_history_reconcile_delivery_guard() -> None:
    """Install the idempotent history->Telegram close-delivery recovery bridge."""
    global _INSTALLED, _ORIGINAL_RECONCILE
    if _INSTALLED:
        return

    original = db.reconcile_mt5_history
    _ORIGINAL_RECONCILE = original

    def _delivery_safe_reconcile(telegram_id: int, items: list[dict]) -> dict:
        normalized = [_as_dict(x) for x in items]
        result = dict(original(int(telegram_id), normalized))
        queued = 0

        for item in normalized:
            if str(item.get("event") or "").upper() != "CLOSE":
                continue
            ticket = str(item.get("ticket") or "").strip()
            if not ticket or float(item.get("exit_price") or 0) <= 0:
                continue

            row = _resolve_signal(int(telegram_id), item)
            if not row or _has_close_reply(int(row["id"])):
                continue

            # CLOSED here only means broker/history truth is known.  Telegram
            # delivery is still pending, so use a terminal-but-retryable state.
            with db.conn() as con:
                con.execute(
                    "UPDATE signals SET status='CLOSING' WHERE id=? AND status='CLOSED'",
                    (int(row["id"]),),
                )

            payload = _close_payload(item, row)
            db.enqueue_autotrade_trade_event(int(telegram_id), "CLOSE", payload, ticket)
            queued += 1
            log.warning(
                "[NEXUS][CLOSE_REPLY][RECOVERY_QUEUED] signal=%s ticket=%s event_id=%s",
                row["code"], ticket, payload["event_id"],
            )

        result["telegram_close_retries_queued"] = queued
        return result

    _delivery_safe_reconcile.__name__ = "reconcile_mt5_history_delivery_safe"
    db.reconcile_mt5_history = _delivery_safe_reconcile
    _INSTALLED = True


__all__ = ["install_history_reconcile_delivery_guard"]
