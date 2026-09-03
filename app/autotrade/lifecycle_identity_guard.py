from __future__ import annotations

"""Harden MT5 lifecycle identity resolution.

The MT5 EA uses the human-facing canonical signal code (for example NX-0001)
as the broker position/deal comment and sends that code back in lifecycle
events. The legacy backend resolver only compared that value with
``publish_token``. CLOSE/UPDATE events therefore became ``stale/unmatched``
whenever the broker deal ticket differed from the original execution receipt
(which is normal on hedging accounts).

A second legacy path treated a broker-confirmed OPEN event for an already issued
MARKET signal as a new manual signal. If the broker event did not contain a
positive TP, the synthetic fallback target equalled entry and repeatedly failed
validation (notably: ``SHORT take-profit targets must be below entry``).

The guard also records ``opened_at`` when that broker-confirmed OPEN reuses the
already-issued MT5_ADMIN signal. Without this timestamp, CLOSE duration falls
back to signal creation time and cannot represent the broker lifecycle cleanly.
"""

import logging
from typing import Any

from .. import db

log = logging.getLogger("nexus-lifecycle-identity-guard")
_INSTALLED = False
_ORIGINAL_LOOKUP = None
_ORIGINAL_ISSUE = None


def _row_value(row: Any, key: str, default: Any = None) -> Any:
    if row is None:
        return default
    try:
        return row[key]
    except Exception:
        return default


def _same_admin_owner(row: Any, admin_id: int | None, admin_account: str | None) -> bool:
    if row is None:
        return False
    if str(_row_value(row, "issuer_type", "")).upper() != "MT5_ADMIN":
        return False
    if admin_id is not None:
        try:
            if int(_row_value(row, "created_by", -1)) != int(admin_id):
                return False
        except (TypeError, ValueError):
            return False
    account = str(admin_account or "").strip()
    issuer_account = str(_row_value(row, "issuer_account", "") or "").strip()
    if account and issuer_account and account != issuer_account:
        return False
    return True


def _is_broker_open_request(request_id: str) -> bool:
    value = str(request_id or "").strip().upper()
    return value.startswith("OPEN-") or value.startswith("OPEN:") or value.startswith("LIVE-OPEN-")


def install_lifecycle_identity_guard() -> None:
    """Install idempotent lifecycle-code and OPEN-reuse compatibility guards."""
    global _INSTALLED, _ORIGINAL_LOOKUP, _ORIGINAL_ISSUE
    if _INSTALLED:
        return

    original_lookup = db.get_signal_by_autotrade_signal_id
    original_issue = db.issue_mt5_admin_signal
    _ORIGINAL_LOOKUP = original_lookup
    _ORIGINAL_ISSUE = original_issue

    def _lookup_by_canonical_identity(telegram_id: int, signal_id: str):
        row = original_lookup(int(telegram_id), signal_id)
        if row is not None:
            return row
        token = str(signal_id or "").strip()
        if not token:
            return None
        # Canonical NX-* code is what the EA persists in POSITION/DEAL comments.
        # Keep the admin owner constraint so one account cannot bind another
        # administrator's lifecycle event merely by guessing a signal code.
        with db.conn() as con:
            row = con.execute(
                """SELECT s.* FROM signals s
                   WHERE s.created_by=? AND (s.code=? OR s.publish_token=?)
                   ORDER BY s.id DESC LIMIT 1""",
                (int(telegram_id), token, token),
            ).fetchone()
        if row is not None:
            log.info(
                "[NEXUS][LIFECYCLE_ID][CODE_MATCH] signal=%s publish_token=%s admin=%s",
                _row_value(row, "code", token), _row_value(row, "publish_token", ""), telegram_id,
            )
        return row

    def _reuse_existing_admin_signal(*args, **kwargs):
        signal_code = str(kwargs.get("signal_code") or "").strip()
        request_id = str(kwargs.get("request_id") or "").strip()
        if signal_code and _is_broker_open_request(request_id):
            existing = db.get_signal_by_code(signal_code)
            if _same_admin_owner(existing, kwargs.get("admin_id"), kwargs.get("admin_account")):
                # This call is reached from the authoritative broker OPEN path.
                # Record a backend-UTC open timestamp once so duration is based
                # on execution truth rather than the earlier issuance timestamp.
                if not _row_value(existing, "opened_at", None):
                    opened_at = db.now_iso()
                    db.mark_signal_opened(int(_row_value(existing, "id")), opened_at)
                    refreshed = db.get_signal(int(_row_value(existing, "id")))
                    if refreshed is not None:
                        existing = refreshed
                    log.info(
                        "[NEXUS][LIFECYCLE_ID][OPEN_TIME_RECORDED] signal=%s opened_at=%s",
                        signal_code,
                        opened_at,
                    )
                log.info(
                    "[NEXUS][LIFECYCLE_ID][OPEN_REUSE] signal=%s request_id=%s account=%s",
                    signal_code, request_id, kwargs.get("admin_account") or "",
                )
                return existing
        return original_issue(*args, **kwargs)

    _lookup_by_canonical_identity.__name__ = "get_signal_by_autotrade_signal_id_canonical"
    _reuse_existing_admin_signal.__name__ = "issue_mt5_admin_signal_lifecycle_safe"
    db.get_signal_by_autotrade_signal_id = _lookup_by_canonical_identity
    db.issue_mt5_admin_signal = _reuse_existing_admin_signal
    _INSTALLED = True


__all__ = ["install_lifecycle_identity_guard"]
