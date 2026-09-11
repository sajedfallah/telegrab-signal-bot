from __future__ import annotations

"""Runtime guard for stale/corrupt MT5 history lifecycle identity.

Direct MT5 lifecycle events are authoritative and are never filtered here.
Only synthetic history-reconciliation events (RECON-*) are identity-validated.
This protects a fresh NEXUS database from old broker history whose short
human-readable codes (NX-0001, NX-0002, ...) can collide with codes created by
an earlier installation/database.

A legacy EA BuildReconcileItem() formatting defect could also shift arguments
so ``event_time_ms`` contained the deal ticket instead of epoch milliseconds.
Those snapshots are unsafe: they are dropped before reconciliation and any
already-persisted legacy notification is quarantined before Telegram delivery.

Synthetic CLOSE reconciliation is also fail-closed against fresh authoritative
live MT5 state.  The legacy EA aggregates any exit deal into a RECON-CLOSE item,
including partial exits.  If the same NEXUS position is still OPEN in the fresh
live snapshot, that synthetic CLOSE is suppressed; the explicit broker-deal
partial UPDATE path owns the partial-close lifecycle instead.
"""

import json
import logging
import re
from datetime import datetime, timezone

from .. import db

log = logging.getLogger("nexus-notification-queue-guard")
_INSTALLED = False
_ORIGINAL_PENDING = None
_ORIGINAL_RECONCILE = None
_FIRST_POLL_LOGGED = False
_LIVE_CLOSE_GUARD_SECONDS = 30.0


def _compact_symbol(value: object) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def _symbols_compatible(a: object, b: object) -> bool:
    left = _compact_symbol(a)
    right = _compact_symbol(b)
    if not left or not right:
        return True
    # Broker suffixes commonly turn XAUUSD into XAUUSD.EC / XAUUSDm.
    if left.startswith(right) or right.startswith(left):
        return True
    return len(left) >= 6 and len(right) >= 6 and left[:6] == right[:6]


def _direction_family(value: object) -> str:
    """Normalize broker and signal direction aliases onto one identity family."""
    raw = str(value or "").upper().strip()
    if raw in {"BUY", "LONG"}:
        return "BUY"
    if raw in {"SELL", "SHORT"}:
        return "SELL"
    return raw


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


def _resolve_signal(telegram_id: int, payload: dict, signal_db_id: int | None = None):
    if signal_db_id:
        row = db.get_signal(int(signal_db_id))
        if row:
            return row

    code = str(payload.get("signal_id") or payload.get("code") or "").strip()
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
            return db.get_signal_by_autotrade_ticket(int(telegram_id), ticket)
        except Exception:
            return None
    return None


def _is_reconcile(payload: dict) -> bool:
    return str(payload.get("event_id") or "").upper().strip().startswith("RECON-")


def _fresh_live_position_still_open(telegram_id: int, payload: dict, row) -> bool:
    """Return True only for a fresh authoritative OPEN snapshot of this position.

    Freshness matters: an old OPEN row must not permanently block a legitimate
    final CLOSE after an EA/network outage.  In normal operation the EA sends
    live state every five seconds immediately before history reconciliation, so
    a 30-second window is deliberately conservative.
    """
    if str(payload.get("event") or "").upper().strip() != "CLOSE":
        return False
    if not _is_reconcile(payload):
        return False

    signal_code = str(row["code"] or "").strip() if row else ""
    position_id = str(payload.get("position_id") or "").strip()
    if not signal_code and not position_id:
        return False

    try:
        with db.conn() as con:
            live = con.execute(
                """
                SELECT l.last_seen_at
                FROM mt5_live_state AS l
                JOIN autotrade_mt5_accounts AS a
                  ON a.account_number=l.account_number
                WHERE a.telegram_id=?
                  AND LOWER(COALESCE(a.status,'active'))='active'
                  AND l.state_type='POSITION'
                  AND l.status='OPEN'
                  AND l.nexus_managed=1
                  AND (
                        UPPER(COALESCE(l.signal_code,''))=UPPER(?)
                        OR (?<>'' AND CAST(l.identifier AS TEXT)=?)
                      )
                ORDER BY l.last_seen_at DESC
                LIMIT 1
                """,
                (int(telegram_id), signal_code, position_id, position_id),
            ).fetchone()
    except Exception:
        log.exception(
            "[NEXUS][QUEUE_GUARD] live-state CLOSE guard lookup failed signal=%s position=%s",
            signal_code,
            position_id,
        )
        return False

    if not live:
        return False
    seen = _parse_iso(live["last_seen_at"])
    if seen is None:
        return False
    age = (datetime.now(timezone.utc) - seen).total_seconds()
    return -5.0 <= age <= _LIVE_CLOSE_GUARD_SECONDS


def _identity_rejection_reason(
    telegram_id: int,
    payload: dict,
    *,
    signal_db_id: int | None = None,
) -> str | None:
    if not _is_reconcile(payload):
        return None

    # Legacy corrupt snapshots used the deal ticket (e.g. 75,000,000) as
    # event_time_ms. Valid contemporary epoch-ms values are > 1e12.
    try:
        event_ms = int(payload.get("event_time_ms") or 0)
    except (TypeError, ValueError):
        event_ms = 0
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    if event_ms < 1_000_000_000_000 or event_ms > now_ms + 86_400_000:
        return f"invalid reconcile event_time_ms={event_ms}"

    row = _resolve_signal(int(telegram_id), payload, signal_db_id)
    if not row:
        return "reconcile signal identity is unresolved"

    payload_direction = str(payload.get("direction") or "").upper().strip()
    row_direction = str(row["direction"] or "").upper().strip()
    if (
        payload_direction
        and row_direction
        and _direction_family(payload_direction) != _direction_family(row_direction)
    ):
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
        # Broker execution may differ slightly from requested MARKET entry, but
        # a half-percent gap is far beyond normal execution tolerance and is a
        # strong indication that a recycled NX-* code belongs to old history.
        if deviation_pct > 0.50:
            return f"entry mismatch deviation={deviation_pct:.4f}%"

    # A broker lifecycle snapshot cannot predate the canonical signal that it
    # allegedly belongs to.  Five seconds of clock/order skew is tolerated.
    signal_created = _parse_iso(row["created_at"] if "created_at" in row.keys() else None)
    if signal_created is not None:
        event_dt = datetime.fromtimestamp(event_ms / 1000.0, tz=timezone.utc)
        if event_dt.timestamp() + 5 < signal_created.timestamp():
            return "reconcile event predates signal creation"

    if _fresh_live_position_still_open(int(telegram_id), payload, row):
        return "reconcile CLOSE suppressed: fresh authoritative live position is still OPEN"

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
    global _INSTALLED, _ORIGINAL_PENDING, _ORIGINAL_RECONCILE
    if _INSTALLED:
        return

    original_pending = db.pending_autotrade_notifications
    original_reconcile = db.reconcile_mt5_history
    _ORIGINAL_PENDING = original_pending
    _ORIGINAL_RECONCILE = original_reconcile

    def _safe_reconcile(telegram_id: int, items: list[dict]):
        safe_items: list[dict] = []
        rejected = 0
        for raw in items:
            if isinstance(raw, dict):
                payload = dict(raw)
            elif hasattr(raw, "model_dump"):
                payload = dict(raw.model_dump())
            else:
                continue
            reason = _identity_rejection_reason(int(telegram_id), payload)
            if reason:
                rejected += 1
                log.warning(
                    "[NEXUS][QUEUE_GUARD][RECON_REJECTED] signal=%s ticket=%s event_id=%s reason=%s",
                    payload.get("signal_id"), payload.get("ticket"), payload.get("event_id"), reason,
                )
                continue
            safe_items.append(payload)

        result = dict(original_reconcile(int(telegram_id), safe_items))
        result["identity_rejected"] = int(result.get("identity_rejected", 0)) + rejected
        return result

    def _safe_pending(limit: int = 100):
        global _FIRST_POLL_LOGGED
        rows = original_pending(limit)
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
            reason = _identity_rejection_reason(
                int(notification["telegram_id"]), payload,
                signal_db_id=int(notification["signal_id"]) if notification["signal_id"] else None,
            )
            if reason:
                _quarantine(notification, payload, reason)
                continue
            safe.append(notification)
        return safe

    _safe_reconcile.__name__ = "reconcile_mt5_history_identity_safe"
    _safe_pending.__name__ = "pending_autotrade_notifications_identity_safe"
    db.reconcile_mt5_history = _safe_reconcile
    db.pending_autotrade_notifications = _safe_pending
    _INSTALLED = True


__all__ = ["install_notification_queue_guard"]
