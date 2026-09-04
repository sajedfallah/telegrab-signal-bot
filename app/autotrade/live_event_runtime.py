from __future__ import annotations

from typing import Any

from .. import db


_INSTALLED = False
_ORIGINAL_UPSERT = None


def _f(value: Any) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def _customer_for_account(account_number: str) -> int | None:
    """Resolve a licensed customer's Telegram identity from the bound MT5 account."""
    try:
        with db.conn() as con:
            row = con.execute(
                "SELECT telegram_id FROM autotrade_mt5_accounts "
                "WHERE account_number=? AND status='active' LIMIT 1",
                (str(account_number),),
            ).fetchone()
            if not row:
                return None
            uid = int(row["telegram_id"])
            return uid if uid > 0 else None
    except Exception:
        return None


def _old_positions(account_number: str) -> dict[str, dict[str, Any]]:
    """Read the previous authoritative snapshot before it is atomically replaced."""
    try:
        with db.conn() as con:
            rows = con.execute(
                "SELECT * FROM mt5_live_state "
                "WHERE account_number=? AND state_type='POSITION' AND status='OPEN' AND nexus_managed=1",
                (str(account_number),),
            ).fetchall()
            return {str(r["identifier"]): dict(r) for r in rows}
    except Exception:
        return {}


def _emit_volume_updates(account_number: str, before: dict[str, dict[str, Any]], positions: list[dict[str, Any]]) -> None:
    """Emit UPDATE when a still-open position changes volume (partial close/scale change).

    MT5's explicit trade-event stream already reports OPEN/CLOSE and SL/TP changes.
    The live snapshot bridge fills the remaining lifecycle gap: a partial close can
    reduce POSITION_VOLUME while the position remains open, so no final CLOSE event
    exists yet. The durable notification queue then delivers the change privately.
    """
    uid = _customer_for_account(account_number)
    if not uid:
        return

    for current in positions or []:
        identifier = str(current.get("identifier") or "").strip()
        if not identifier or identifier not in before:
            continue
        previous = before[identifier]
        old_volume = _f(previous.get("volume"))
        new_volume = _f(current.get("volume"))
        if abs(old_volume - new_volume) <= 1e-12:
            continue

        ticket = str(current.get("ticket") or previous.get("ticket") or identifier)
        signal_code = str(current.get("signal_code") or previous.get("signal_code") or "")
        event_id = f"LIVE-VOLUME-{identifier}-{new_volume:.8f}"
        payload = {
            "event": "UPDATE",
            "ticket": ticket,
            "signal_id": signal_code,
            "symbol": str(current.get("symbol") or previous.get("symbol") or ""),
            "direction": str(current.get("direction") or previous.get("direction") or ""),
            "volume": new_volume,
            "entry_price": _f(current.get("entry_price")),
            "stop_loss": _f(current.get("stop_loss")),
            "take_profit": _f(current.get("take_profit")),
            "profit": _f(current.get("profit")),
            "position_id": identifier,
            "event_id": event_id,
            "destination": "NONE",
            "change_source": "LIVE_SNAPSHOT_VOLUME",
            "previous_volume": old_volume,
        }
        db.enqueue_autotrade_trade_event(uid, "UPDATE", payload, ticket)


def install_live_snapshot_event_bridge() -> None:
    """Patch the live-state writer before FastAPI imports its API module.

    This is intentionally installed from run_api.py. It preserves the hardened
    DB implementation and adds only the missing partial-volume lifecycle event.
    """
    global _INSTALLED, _ORIGINAL_UPSERT
    if _INSTALLED:
        return

    _ORIGINAL_UPSERT = db.upsert_mt5_live_snapshot

    def wrapped(account_number: str, *, broker: str = "", server: str = "", ea_version: str = "", positions=None, orders=None):
        before = _old_positions(str(account_number))
        result = _ORIGINAL_UPSERT(
            account_number,
            broker=broker,
            server=server,
            ea_version=ea_version,
            positions=positions,
            orders=orders,
        )
        try:
            _emit_volume_updates(str(account_number), before, list(positions or []))
        except Exception:
            # Live-state synchronization is more important than an optional
            # notification bridge. Never fail the authoritative snapshot write.
            pass
        return result

    db.upsert_mt5_live_snapshot = wrapped
    _INSTALLED = True
