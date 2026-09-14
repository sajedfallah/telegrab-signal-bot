from __future__ import annotations

import sqlite3

import pytest

from app.signal_domain import (
    backfill_legacy_publications,
    get_signal,
    init_signal_domain_schema,
    list_signals,
    record_signal_event,
)
from app.tenancy import init_tenant_schema


def _db() -> tuple[sqlite3.Connection, int, int]:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("CREATE TABLE users(telegram_id INTEGER PRIMARY KEY)")
    nexus = init_tenant_schema(con)
    other = con.execute(
        "INSERT INTO tenants(slug,business_name,display_name,status,timezone,locale,created_at,updated_at) "
        "VALUES('other','Other','Other','ACTIVE','UTC','en','x','x') RETURNING id"
    ).fetchone()[0]
    con.execute(
        "CREATE TABLE signals(id INTEGER PRIMARY KEY,tenant_id INTEGER,code TEXT,symbol TEXT,market_type TEXT,direction TEXT,"
        "free_message_id INTEGER,vip_message_id INTEGER,free_last_message_id INTEGER,vip_last_message_id INTEGER,created_at TEXT)"
    )
    con.executemany(
        "INSERT INTO signals VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        [
            (1, nexus, 'NX1', 'XAUUSD', 'Gold', 'BUY', 101, 201, 102, 202, '2026-09-14T00:00:00+00:00'),
            (2, other, 'OT1', 'BTCUSDT', 'Crypto', 'SELL', 301, None, 302, None, '2026-09-14T00:00:00+00:00'),
        ],
    )
    init_signal_domain_schema(con)
    return con, nexus, other


def test_signal_list_and_detail_do_not_leak_cross_tenant_rows():
    con, nexus, other = _db()
    assert [row["symbol"] for row in list_signals(con, tenant_id=nexus)] == ["XAUUSD"]
    assert get_signal(con, tenant_id=nexus, signal_id=2) is None
    assert get_signal(con, tenant_id=other, signal_id=1) is None


def test_legacy_publication_backfill_is_idempotent_and_tenant_scoped():
    con, nexus, other = _db()
    assert backfill_legacy_publications(con) == 3
    assert backfill_legacy_publications(con) == 0
    nx = get_signal(con, tenant_id=nexus, signal_id=1)
    ot = get_signal(con, tenant_id=other, signal_id=2)
    assert [(p["destination_key"], p["root_message_id"], p["last_message_id"]) for p in nx["publications"]] == [
        ("FREE", 101, 102), ("VIP", 201, 202)
    ]
    assert [(p["destination_key"], p["root_message_id"]) for p in ot["publications"]] == [("FREE", 301)]


def test_event_cannot_be_attached_to_another_tenants_signal():
    con, nexus, other = _db()
    event_id = record_signal_event(
        con, tenant_id=nexus, signal_id=1, event_type="PARTIAL_CLOSE",
        payload={"profit_usd": 12.5, "remaining_percent": 50, "sl": 2350, "tp": 2380}, actor_user_id=1001,
    )
    assert event_id > 0
    with pytest.raises(LookupError):
        record_signal_event(con, tenant_id=nexus, signal_id=2, event_type="SL_CHANGED", payload={"sl": 1})
    assert get_signal(con, tenant_id=nexus, signal_id=1)["events"][0]["payload"]["profit_usd"] == 12.5
    assert get_signal(con, tenant_id=other, signal_id=2)["events"] == []
