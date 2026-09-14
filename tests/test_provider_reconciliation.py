from __future__ import annotations

import sqlite3

import pytest

from app.provider_lifecycle import _payload_hash, init_lifecycle_delivery_schema
from app.provider_reconciliation import list_reconciliation_queue, reconciliation_health, resolve_delivery
from app.signal_domain import init_signal_domain_schema
from app.tenancy import init_tenant_schema


def _db() -> tuple[sqlite3.Connection, int, int, dict]:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("CREATE TABLE users(telegram_id INTEGER PRIMARY KEY)")
    nexus = int(init_tenant_schema(con))
    other = int(con.execute(
        "INSERT INTO tenants(slug,business_name,display_name,status,timezone,locale,created_at,updated_at) "
        "VALUES('other','Other','Other','ACTIVE','UTC','en','x','x') RETURNING id"
    ).fetchone()[0])
    con.execute("CREATE TABLE signals(id INTEGER PRIMARY KEY,tenant_id INTEGER NOT NULL,code TEXT)")
    con.executemany("INSERT INTO signals(id,tenant_id,code) VALUES(?,?,?)", [(1,nexus,'NX1'),(2,other,'OT1')])
    init_signal_domain_schema(con)
    con.execute(
        "INSERT INTO signal_publications(id,tenant_id,signal_id,destination_key,telegram_chat_id,root_message_id,last_message_id,status,published_at,updated_at) "
        "VALUES(10,?,1,'VIP','-100111',500,500,'PUBLISHED','x','x')",
        (nexus,),
    )
    con.execute(
        "INSERT INTO signal_publications(id,tenant_id,signal_id,destination_key,telegram_chat_id,root_message_id,last_message_id,status,published_at,updated_at) "
        "VALUES(20,?,2,'VIP','-100222',600,600,'PUBLISHED','x','x')",
        (other,),
    )
    init_lifecycle_delivery_schema(con)
    payload = {"tp": 2450, "sl": 2420}
    con.execute(
        "INSERT INTO provider_lifecycle_deliveries(id,tenant_id,publication_id,signal_id,destination_key,idempotency_key,event_type,payload_hash,status,reply_to_message_id,error_code,created_at,updated_at) "
        "VALUES(100,?,10,1,'VIP','evt-1','TRAILING',?,'UNKNOWN',500,'telegram_delivery_uncertain','x','x')",
        (nexus, _payload_hash('TRAILING', payload)),
    )
    con.execute(
        "INSERT INTO provider_lifecycle_deliveries(id,tenant_id,publication_id,signal_id,destination_key,idempotency_key,event_type,payload_hash,status,reply_to_message_id,error_code,created_at,updated_at) "
        "VALUES(200,?,20,2,'VIP','evt-2','TRAILING',?,'UNKNOWN',600,'telegram_delivery_uncertain','x','x')",
        (other, _payload_hash('TRAILING', payload)),
    )
    con.commit()
    return con, nexus, other, payload


def test_reconciliation_queue_is_tenant_scoped() -> None:
    con, nexus, other, _ = _db()
    nx = list_reconciliation_queue(con, tenant_id=nexus)
    ot = list_reconciliation_queue(con, tenant_id=other)
    assert [item["delivery_id"] for item in nx] == [100]
    assert [item["delivery_id"] for item in ot] == [200]


def test_reconciliation_health_is_tenant_scoped_and_flags_attention() -> None:
    con, nexus, other, _ = _db()
    nx = reconciliation_health(con, tenant_id=nexus)
    ot = reconciliation_health(con, tenant_id=other)
    assert nx == {
        "status": "attention",
        "unknown_delivery_count": 1,
        "claimed_delivery_count": 0,
        "open_reconciliation_count": 1,
        "requires_attention": True,
    }
    assert ot["unknown_delivery_count"] == 1
    assert ot["open_reconciliation_count"] == 1


def test_confirmed_sent_finalizes_receipt_event_publication_and_audit() -> None:
    con, nexus, _, payload = _db()
    result = resolve_delivery(
        con,
        tenant_id=nexus,
        delivery_id=100,
        resolution="CONFIRMED_SENT",
        resolved_by_user_id=1001,
        telegram_message_id=901,
        payload=payload,
        note="Verified in Telegram channel",
    )
    assert result["delivery_status"] == "SENT"
    assert result["telegram_message_id"] == 901
    assert result["event_id"] is not None
    assert result["retry_permitted_with_new_key"] is False
    publication = con.execute("SELECT last_message_id,status FROM signal_publications WHERE id=10").fetchone()
    assert tuple(publication) == (901, "PUBLISHED")
    delivery = con.execute("SELECT status,telegram_message_id,event_id FROM provider_lifecycle_deliveries WHERE id=100").fetchone()
    assert delivery["status"] == "SENT"
    assert delivery["telegram_message_id"] == 901
    assert delivery["event_id"] is not None
    audit = con.execute("SELECT action,entity_id FROM provider_audit_log WHERE tenant_id=?", (nexus,)).fetchone()
    assert tuple(audit) == ("DELIVERY_RECONCILED", 100)
    assert list_reconciliation_queue(con, tenant_id=nexus) == []
    assert reconciliation_health(con, tenant_id=nexus)["requires_attention"] is False


def test_confirmed_not_sent_allows_only_new_key_retry_and_keeps_original_blocked() -> None:
    con, nexus, _, _ = _db()
    result = resolve_delivery(
        con,
        tenant_id=nexus,
        delivery_id=100,
        resolution="CONFIRMED_NOT_SENT",
        resolved_by_user_id=1001,
        note="No message found in destination",
    )
    assert result["delivery_status"] == "UNKNOWN"
    assert result["retry_permitted_with_new_key"] is True
    row = con.execute("SELECT status,error_code FROM provider_lifecycle_deliveries WHERE id=100").fetchone()
    assert tuple(row) == ("UNKNOWN", "confirmed_not_sent")
    assert list_reconciliation_queue(con, tenant_id=nexus) == []


def test_cross_tenant_delivery_is_not_exposed() -> None:
    con, nexus, _, payload = _db()
    with pytest.raises(LookupError):
        resolve_delivery(
            con,
            tenant_id=nexus,
            delivery_id=200,
            resolution="CONFIRMED_SENT",
            resolved_by_user_id=1001,
            telegram_message_id=999,
            payload=payload,
        )


def test_confirmed_sent_requires_original_payload_hash() -> None:
    con, nexus, _, _ = _db()
    with pytest.raises(ValueError, match="payload does not match"):
        resolve_delivery(
            con,
            tenant_id=nexus,
            delivery_id=100,
            resolution="CONFIRMED_SENT",
            resolved_by_user_id=1001,
            telegram_message_id=901,
            payload={"tp": 9999, "sl": 1},
        )
