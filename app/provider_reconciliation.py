from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from .provider_lifecycle import TERMINAL_EVENTS, _payload_hash
from .signal_domain import record_signal_event


RESOLUTIONS = {"CONFIRMED_SENT", "CONFIRMED_NOT_SENT"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_reconciliation_schema(con: sqlite3.Connection) -> None:
    statements = (
        """CREATE TABLE IF NOT EXISTS provider_delivery_reconciliations(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            delivery_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'OPEN'
                CHECK(status IN ('OPEN','RESOLVED')),
            resolution TEXT
                CHECK(resolution IS NULL OR resolution IN ('CONFIRMED_SENT','CONFIRMED_NOT_SENT')),
            resolution_note TEXT,
            evidence_message_id INTEGER,
            resolved_by_user_id INTEGER,
            created_at TEXT NOT NULL,
            resolved_at TEXT,
            updated_at TEXT NOT NULL,
            UNIQUE(tenant_id,delivery_id),
            FOREIGN KEY(tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
            FOREIGN KEY(delivery_id) REFERENCES provider_lifecycle_deliveries(id) ON DELETE CASCADE
        )""",
        "CREATE INDEX IF NOT EXISTS idx_provider_delivery_reconciliation_queue ON provider_delivery_reconciliations(tenant_id,status,id)",
        """CREATE TABLE IF NOT EXISTS provider_audit_log(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            actor_user_id INTEGER,
            action TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id INTEGER NOT NULL,
            metadata_json TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
        )""",
        "CREATE INDEX IF NOT EXISTS idx_provider_audit_tenant_entity ON provider_audit_log(tenant_id,entity_type,entity_id,id)",
    )
    for statement in statements:
        con.execute(statement)


def _audit(
    con: sqlite3.Connection,
    *,
    tenant_id: int,
    actor_user_id: int | None,
    action: str,
    entity_type: str,
    entity_id: int,
    metadata: dict[str, Any] | None = None,
) -> int:
    cur = con.execute(
        "INSERT INTO provider_audit_log(tenant_id,actor_user_id,action,entity_type,entity_id,metadata_json,created_at) VALUES(?,?,?,?,?,?,?)",
        (
            tenant_id,
            actor_user_id,
            action,
            entity_type,
            entity_id,
            json.dumps(metadata or {}, sort_keys=True, separators=(",", ":")),
            _now(),
        ),
    )
    return int(cur.lastrowid)


def sync_reconciliation_queue(con: sqlite3.Connection, *, tenant_id: int) -> int:
    """Materialize UNKNOWN lifecycle deliveries into a tenant-owned review queue."""
    init_reconciliation_schema(con)
    now = _now()
    before = con.total_changes
    con.execute(
        "INSERT OR IGNORE INTO provider_delivery_reconciliations(tenant_id,delivery_id,status,created_at,updated_at) "
        "SELECT tenant_id,id,'OPEN',?,? FROM provider_lifecycle_deliveries "
        "WHERE tenant_id=? AND status='UNKNOWN'",
        (now, now, tenant_id),
    )
    return con.total_changes - before


def reconciliation_health(con: sqlite3.Connection, *, tenant_id: int) -> dict[str, Any]:
    """Return tenant-scoped recovery health after materializing ambiguous deliveries."""
    init_reconciliation_schema(con)
    sync_reconciliation_queue(con, tenant_id=tenant_id)
    unknown = int(con.execute(
        "SELECT COUNT(*) FROM provider_lifecycle_deliveries WHERE tenant_id=? AND status='UNKNOWN'",
        (tenant_id,),
    ).fetchone()[0])
    claimed = int(con.execute(
        "SELECT COUNT(*) FROM provider_lifecycle_deliveries WHERE tenant_id=? AND status='CLAIMED'",
        (tenant_id,),
    ).fetchone()[0])
    open_items = int(con.execute(
        "SELECT COUNT(*) FROM provider_delivery_reconciliations WHERE tenant_id=? AND status='OPEN'",
        (tenant_id,),
    ).fetchone()[0])
    status = "attention" if unknown or claimed or open_items else "healthy"
    return {
        "status": status,
        "unknown_delivery_count": unknown,
        "claimed_delivery_count": claimed,
        "open_reconciliation_count": open_items,
        "requires_attention": status == "attention",
    }


def list_reconciliation_queue(con: sqlite3.Connection, *, tenant_id: int) -> list[dict[str, Any]]:
    sync_reconciliation_queue(con, tenant_id=tenant_id)
    rows = con.execute(
        "SELECT r.id AS reconciliation_id,r.status AS reconciliation_status,r.created_at AS reconciliation_created_at,"
        "d.id AS delivery_id,d.publication_id,d.signal_id,d.destination_key,d.idempotency_key,d.event_type,d.status AS delivery_status,"
        "d.reply_to_message_id,d.telegram_message_id,d.event_id,d.error_code,d.created_at,d.updated_at "
        "FROM provider_delivery_reconciliations r "
        "JOIN provider_lifecycle_deliveries d ON d.id=r.delivery_id AND d.tenant_id=r.tenant_id "
        "WHERE r.tenant_id=? AND r.status='OPEN' ORDER BY r.id",
        (tenant_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def resolve_delivery(
    con: sqlite3.Connection,
    *,
    tenant_id: int,
    delivery_id: int,
    resolution: str,
    resolved_by_user_id: int,
    note: str | None = None,
    telegram_message_id: int | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    init_reconciliation_schema(con)
    sync_reconciliation_queue(con, tenant_id=tenant_id)
    normalized = str(resolution).upper()
    if normalized not in RESOLUTIONS:
        raise ValueError("unsupported reconciliation resolution")

    row = con.execute(
        "SELECT d.id,d.tenant_id,d.publication_id,d.signal_id,d.destination_key,d.idempotency_key,d.event_type,d.payload_hash,"
        "d.status,d.reply_to_message_id,d.telegram_message_id,d.event_id,d.error_code,"
        "r.id AS reconciliation_id,r.status AS reconciliation_status "
        "FROM provider_lifecycle_deliveries d "
        "JOIN provider_delivery_reconciliations r ON r.delivery_id=d.id AND r.tenant_id=d.tenant_id "
        "WHERE d.id=? AND d.tenant_id=?",
        (delivery_id, tenant_id),
    ).fetchone()
    if row is None:
        raise LookupError("delivery reconciliation not found")
    item = dict(row)
    if item["reconciliation_status"] != "OPEN":
        raise RuntimeError("delivery reconciliation is already resolved")
    if item["status"] != "UNKNOWN":
        raise RuntimeError("delivery is not in UNKNOWN state")

    now = _now()
    event_id: int | None = item.get("event_id")
    publication_status: str | None = None

    if normalized == "CONFIRMED_SENT":
        if telegram_message_id is None or int(telegram_message_id) <= 0:
            raise ValueError("telegram_message_id is required for CONFIRMED_SENT")
        if payload is None:
            raise ValueError("payload is required for CONFIRMED_SENT")
        if _payload_hash(str(item["event_type"]), payload) != str(item["payload_hash"]):
            raise ValueError("payload does not match original lifecycle delivery")

        publication = con.execute(
            "SELECT id,status FROM signal_publications WHERE id=? AND tenant_id=? AND signal_id=?",
            (int(item["publication_id"]), tenant_id, int(item["signal_id"])),
        ).fetchone()
        if publication is None:
            raise LookupError("signal publication not found")

        event_id = record_signal_event(
            con,
            tenant_id=tenant_id,
            signal_id=int(item["signal_id"]),
            event_type=str(item["event_type"]),
            payload=payload,
            actor_user_id=resolved_by_user_id,
        )
        publication_status = "CLOSED" if str(item["event_type"]).upper() in TERMINAL_EVENTS else str(publication["status"])
        con.execute(
            "UPDATE signal_publications SET last_message_id=?,status=?,updated_at=? WHERE id=? AND tenant_id=?",
            (int(telegram_message_id), publication_status, now, int(item["publication_id"]), tenant_id),
        )
        con.execute(
            "UPDATE provider_lifecycle_deliveries SET status='SENT',telegram_message_id=?,event_id=?,error_code=NULL,updated_at=? "
            "WHERE id=? AND tenant_id=?",
            (int(telegram_message_id), event_id, now, delivery_id, tenant_id),
        )
    else:
        con.execute(
            "UPDATE provider_lifecycle_deliveries SET error_code='confirmed_not_sent',updated_at=? WHERE id=? AND tenant_id=?",
            (now, delivery_id, tenant_id),
        )

    con.execute(
        "UPDATE provider_delivery_reconciliations SET status='RESOLVED',resolution=?,resolution_note=?,evidence_message_id=?,"
        "resolved_by_user_id=?,resolved_at=?,updated_at=? WHERE id=? AND tenant_id=?",
        (
            normalized,
            (note or "").strip() or None,
            int(telegram_message_id) if telegram_message_id is not None else None,
            resolved_by_user_id,
            now,
            now,
            int(item["reconciliation_id"]),
            tenant_id,
        ),
    )
    audit_id = _audit(
        con,
        tenant_id=tenant_id,
        actor_user_id=resolved_by_user_id,
        action="DELIVERY_RECONCILED",
        entity_type="provider_lifecycle_delivery",
        entity_id=delivery_id,
        metadata={
            "resolution": normalized,
            "telegram_message_id": telegram_message_id,
            "event_id": event_id,
            "retry_permitted_with_new_key": normalized == "CONFIRMED_NOT_SENT",
        },
    )
    con.commit()
    return {
        "delivery_id": delivery_id,
        "reconciliation_id": int(item["reconciliation_id"]),
        "resolution": normalized,
        "delivery_status": "SENT" if normalized == "CONFIRMED_SENT" else "UNKNOWN",
        "telegram_message_id": int(telegram_message_id) if telegram_message_id is not None else None,
        "event_id": event_id,
        "publication_status": publication_status,
        "retry_permitted_with_new_key": normalized == "CONFIRMED_NOT_SENT",
        "audit_id": audit_id,
    }
