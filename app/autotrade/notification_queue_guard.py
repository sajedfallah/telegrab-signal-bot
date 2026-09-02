from __future__ import annotations

"""Runtime guard for stale/corrupt MT5 history notifications.

Direct MT5 lifecycle events are authoritative and are never filtered here.
Only synthetic history-reconciliation events (RECON-*) are validated before the
Telegram notification worker can claim them.  This protects a fresh NEXUS DB
from old broker history whose short human-readable codes (NX-0001, NX-0002, ...)
may collide with codes issued by an earlier installation/database.

A legacy EA formatting bug could also shift BuildReconcileItem() arguments so
``event_time_ms`` contained the deal ticket instead of epoch milliseconds.  Such
rows are not safe enough to publish and are quarantined instead of replied to a
possibly unrelated Telegram signal.
"""

import json
import logging
import re
from datetime import datetime, timezone

from .. import db

log = logging.getLogger("nexus-notification-queue-guard")
_INSTALLED = False
_ORIGINAL_PENDING = None
_FIRST_POLL_LOGGED = False


def _compact_symbol(value: object) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def _symbols_compatible(a: object, b: object) -> bool:
    left = _compact_symbol(a)
    right = _compact_symbol(b)
    if not left or not right:
        return True
    # Broker suffixes/prefix aliases commonly turn XAUUSD into XAUUSD.EC,
    # XAUUSDm, etc.  A shared six-character FX/metal root is sufficient here.
    if left.startswith(right) or right.startswith(left):
        return True
    return len(left) >= 6 and len(right) >= 6 and left[:6] == right[:6]


def _parse_iso(value: object):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def _resolve_signal(notification, payload: dict):
    signal_db_id = notification["signal_id"]
    if signal_db_id:
        row = db.get_signal(int(signal_db_id))
        if row:
            return row

    code = str(payload.get("signal_id") or "").strip()
    if code:
        row = db.get_signal_by_code(code)
        if row:
            return row
        row = db.get_signal_by_publish_token(code)
        if row:
            return row

    ticket = str(payload.get("ticket") or "").strip()
    if ticket:
        try:
            return db.get_signal_by_autotrade_ticket(int(notification["telegram_id"]), ticket)
        except Exception:
            return None
    return None


def _reconcile_rejection_reason(notification, payload: dict) -> str | None:
    event_id = str(payload.get("event_id") or "").upper().strip()
    if not event_id.startswith("RECON-"):
        return None

    # Legacy corrupt snapshots used the deal ticket (e.g. 75,000,000) as
    # event_time_ms.  Valid contemporary epoch-ms values are > 1e12.
    try:
        event_ms = int(payload.get("event_time_ms") or 0)
    except (TypeError, ValueError):
        event_ms = 0
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    if event_ms < 1_000_000_000_000 or event_ms > now_ms + 86_400_000:
        return f"invalid reconcile event_time_ms={event_ms}"

    row = _resolve_signal(notification, payload)
    if not row:
        return "reconcile signal identity is unresolved"

    payload_direction = str(payload.get("direction") or "").upper().strip()
    row_direction = str(row["direction"] or "").upper().strip()
    if payload_direction and row_direction and payload_direction != row_direction:
        return f"direction mismatch history={payload_direction} signal={row_direction}"

    if not _symbols_compatible(payload.get("symbol"), row["symbol"]):
        return f"symbol mismatch history={payload.get('symbol')} signal={row['symbol']}"

    try:
        history_entry = float(payload.get("entry_price") or 0)
        signal_entry = float(row["entry_price"] or 0)
    except (TypeError, ValueError):
        history_entry = signal_entry = 0.0
    if history_entry > 0 and signal_entry > 0:
        deviation_pct = abs(history_entry - signal_entry) / abs(signal_entry) * 100.0
        if deviation_pct > 0.50:
            return f"entry mismatch deviation={deviation_pct:.4f}%"

    # A close snapshot cannot predate the signal it allegedly belongs to.
    signal_created = _parse_iso(row["created_at"] if "created_at" in row.keys() else None)
    if signal_created is not None:
        event_dt = datetime.fromtimestamp(event_ms / 1000.0, tz=timezone.utc)
        if event_dt < signal_created.replace(microsecond=0):
            return "reconcile event predates signal creation"

    return None


def _quarantine(notification, payload: dict, reason: str) -> None:
    notification_id = int(notification["id"])
    with db.conn() as con:
        con.execute(
            "UPDATE autotrade_notifications SET sent_at=?,claimed_at=NULL WHERE id=? AND sent_at IS NULL",
            (db.now_iso(), notification_id),
        )

    ticket = str(payload.get("ticket") or "").strip()
    event_id = str(payload.get("event_id") or "").strip()
    if ticket and event_id:
        try:
            db.update_trade_execution(
                int(notification["telegram_id"]), ticket, event_id,
                status="IGNORED", error_text=f"QUEUE_GUARD: {reason}",
                destination=str(payload.get("destination") or "BOTH"),
            )
        except Exception:
            log.exception("[NEXUS][QUEUE_GUARD] failed to mark execution ignored id=%s", notification_id)

    log.warning(
        "[NEXUS][QUEUE_GUARD][QUARANTINED_RECON] notification_id=%s signal=%s ticket=%s reason=%s",
        notification_id, payload.get("signal_id"), ticket, reason,
    )


def install_notification_queue_guard() -> None:
    global _INSTALLED, _ORIGINAL_PENDING
    if _INSTALLED:
        return

    original = db.pending_autotrade_notifications
    _ORIGINAL_PENDING = original

    def _safe_pending(limit: int = 100):
        global _FIRST_POLL_LOGGED
        rows = original(limit)
        if not _FIRST_POLL_LOGGED:
            log.info("[NEXUS][QUEUE_GUARD][WORKER_POLL] pending=%s", len(rows))
            _FIRST_POLL_LOGGED = True

        safe = []
        for notification in rows:
            if str(notification["event_type"] or "") != "MT5_TRADE_EVENT":
                safe.append(notification)
                continue
            try:
                payload = json.loads(str(notification["payload_json"] or "{}"))
            except Exception:
                safe.append(notification)
                continue
            reason = _reconcile_rejection_reason(notification, payload)
            if reason:
                _quarantine(notification, payload, reason)
                continue
            safe.append(notification)
        return safe

    _safe_pending.__name__ = "pending_autotrade_notifications_identity_safe"
    db.pending_autotrade_notifications = _safe_pending
    _INSTALLED = True


__all__ = ["install_notification_queue_guard"]
