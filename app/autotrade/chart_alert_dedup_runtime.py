from __future__ import annotations

import hashlib
import json
from typing import Any

from .. import db


def _incident_payload(account: str, health: dict[str, Any]) -> tuple[str, int | None, dict[str, Any]] | None:
    severity = str(health.get("severity") or "").upper()
    if severity not in {"WARN", "CRITICAL"}:
        return None

    exhausted = list(health.get("repair_exhausted") or [])
    first = dict(exhausted[0]) if exhausted else {}
    signal_id = int(first.get("signal_id")) if first.get("signal_id") else None
    job_id = int(first.get("job_id")) if first.get("job_id") else None
    error = str(first.get("error_text") or "")
    code = str(first.get("code") or "")

    # Incident identity deliberately excludes rolling health counters. A new
    # unrelated failure/fallback must not make the same exhausted NX signal
    # alert again. A changed signal/job/error/severity is a genuinely new event.
    identity = {
        "account": str(account),
        "severity": severity,
        "signal_id": signal_id,
        "job_id": job_id,
        "error": error,
    }
    payload = {
        **identity,
        "code": code,
        "failed": int((health.get("counts") or {}).get("FAILED", 0)),
        "expired": int((health.get("counts") or {}).get("EXPIRED", 0)),
        "fallback": int(health.get("fallback_publications") or 0),
    }
    canonical = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest(), signal_id, payload


def _ensure_schema() -> None:
    with db.conn() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS chart_delivery_alert_incidents (
                incident_key TEXT PRIMARY KEY,
                account_number TEXT NOT NULL,
                signal_id INTEGER,
                severity TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                claimed_at TEXT NOT NULL
            )
            """
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_chart_delivery_alert_account "
            "ON chart_delivery_alert_incidents(account_number, claimed_at)"
        )


def _resolve_account(account: str) -> None:
    # A clean health cycle closes all previous alert identities for this MT5.
    # If the same problem genuinely returns after recovery it is allowed to
    # produce one fresh alert again.
    with db.conn() as con:
        con.execute(
            "DELETE FROM chart_delivery_alert_incidents WHERE account_number=?",
            (str(account),),
        )


def _claim_incident(account: str, health: dict[str, Any]) -> bool:
    data = _incident_payload(account, health)
    if data is None:
        return False
    incident_key, signal_id, payload = data
    with db.conn() as con:
        cur = con.execute(
            """INSERT OR IGNORE INTO chart_delivery_alert_incidents
               (incident_key,account_number,signal_id,severity,payload_json,claimed_at)
               VALUES(?,?,?,?,?,?)""",
            (
                incident_key,
                str(account),
                signal_id,
                str(payload["severity"]),
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
                db.now_iso(),
            ),
        )
        claimed = int(cur.rowcount or 0) == 1
    if claimed and signal_id:
        db.add_signal_event(
            signal_id,
            "CHART_DELIVERY_ALERT_CLAIMED",
            actor_type="BACKEND",
            account_number=str(account),
            correlation_id=str(payload.get("code") or ""),
            payload={"incident_key": incident_key, **payload},
        )
    return claimed


def install_chart_alert_dedup_runtime(app) -> None:
    """Make Chart Delivery admin alerts incident-based and restart-safe.

    V24 used an in-memory 600-second throttle, so one exhausted incident was
    resent forever and every process restart forgot the throttle. This patch
    keeps V24 health/repair behavior intact and replaces only its alert gate.
    """
    if getattr(app.state, "nexus_chart_alert_dedup_v36", False):
        return

    from . import chart_delivery_guard as guard

    _ensure_schema()

    def durable_alert_due(account: str, health: dict[str, Any]) -> bool:
        severity = str(health.get("severity") or "").upper()
        if severity not in {"WARN", "CRITICAL"}:
            _resolve_account(str(account))
            return False
        return _claim_incident(str(account), health)

    guard._alert_due = durable_alert_due
    app.state.nexus_chart_alert_dedup_v36 = True
