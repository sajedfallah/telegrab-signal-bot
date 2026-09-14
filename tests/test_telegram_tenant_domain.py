from __future__ import annotations

import sqlite3

import pytest

from app.telegram_tenant_domain import (
    create_connection,
    create_destination,
    init_telegram_tenant_schema,
    list_connections,
    list_destinations,
    resolve_destination,
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
    init_telegram_tenant_schema(con)
    return con, nexus, int(other)


def test_connections_and_destinations_are_tenant_scoped() -> None:
    con, nexus, other = _db()
    nx_conn = create_connection(con, tenant_id=nexus, label="primary", bot_username="nexus_bot", secret_ref="secret:nexus", status="ACTIVE")
    ot_conn = create_connection(con, tenant_id=other, label="primary", bot_username="other_bot", secret_ref="secret:other", status="ACTIVE")
    create_destination(con, tenant_id=nexus, connection_id=nx_conn, destination_key="VIP", chat_id="-100111", kind="VIP")
    create_destination(con, tenant_id=other, connection_id=ot_conn, destination_key="VIP", chat_id="-100222", kind="VIP")

    nx_connections = list_connections(con, tenant_id=nexus)
    nx_destinations = list_destinations(con, tenant_id=nexus)
    assert [row["bot_username"] for row in nx_connections] == ["nexus_bot"]
    assert "secret_ref" not in nx_connections[0]
    assert [row["chat_id"] for row in nx_destinations] == ["-100111"]
    assert resolve_destination(con, tenant_id=nexus, destination_key="VIP")["chat_id"] == "-100111"
    assert resolve_destination(con, tenant_id=other, destination_key="VIP")["chat_id"] == "-100222"


def test_cross_tenant_connection_cannot_be_used_for_destination() -> None:
    con, nexus, other = _db()
    other_conn = create_connection(con, tenant_id=other, label="primary", status="ACTIVE")
    with pytest.raises(LookupError):
        create_destination(
            con,
            tenant_id=nexus,
            connection_id=other_conn,
            destination_key="FREE",
            chat_id="-100333",
            kind="FREE",
        )


def test_inactive_connection_cannot_create_destination() -> None:
    con, nexus, _ = _db()
    connection = create_connection(con, tenant_id=nexus, label="primary", status="DISABLED")
    with pytest.raises(RuntimeError):
        create_destination(
            con,
            tenant_id=nexus,
            connection_id=connection,
            destination_key="FREE",
            chat_id="-100444",
            kind="FREE",
        )
    assert resolve_destination(con, tenant_id=nexus, destination_key="FREE") is None
