from __future__ import annotations

import sqlite3

import pytest
from fastapi import HTTPException

from app.provider_panel_api import TelegramDestinationCreate, create_telegram_destination
from app.telegram_tenant_domain import create_connection
from app.tenancy import TenantRole, grant_membership, init_tenant_schema


def _setup(tmp_path, role: TenantRole):
    path = tmp_path / "provider.db"
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("CREATE TABLE users(telegram_id INTEGER PRIMARY KEY)")
    con.executemany("INSERT INTO users VALUES(?)", [(1001,), (2002,)])
    nexus_id = init_tenant_schema(con)
    other_id = con.execute(
        "INSERT INTO tenants(slug,business_name,display_name,status,timezone,locale,created_at,updated_at) "
        "VALUES('other','Other','Other','ACTIVE','UTC','en','x','x') RETURNING id"
    ).fetchone()[0]
    grant_membership(con, tenant_id=nexus_id, user_id=1001, role=role)
    own_connection = create_connection(con, tenant_id=nexus_id, label="primary", status="ACTIVE")
    other_connection = create_connection(con, tenant_id=other_id, label="primary", status="ACTIVE")
    con.commit()
    con.close()
    return path, int(nexus_id), int(own_connection), int(other_connection)


class Conn:
    def __init__(self, path):
        self.path = path

    def __enter__(self):
        self.con = sqlite3.connect(self.path)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA foreign_keys=ON")
        return self.con

    def __exit__(self, exc_type, *_):
        if exc_type is None:
            self.con.commit()
        else:
            self.con.rollback()
        self.con.close()


def _patch(monkeypatch, path):
    monkeypatch.setattr("app.provider_panel_api.db.conn", lambda: Conn(path))
    monkeypatch.setattr("app.provider_panel_api._authenticate_provider", lambda _: {"id": 1001})


def test_owner_can_create_destination_for_active_tenant_connection(monkeypatch, tmp_path):
    path, tenant_id, connection_id, _ = _setup(tmp_path, TenantRole.OWNER)
    _patch(monkeypatch, path)
    result = create_telegram_destination(
        TelegramDestinationCreate(
            connection_id=connection_id,
            destination_key="vip",
            chat_id="-100111",
            kind="VIP",
            display_name="VIP Signals",
        ),
        "signed",
        tenant_id,
    )
    assert result["destination"]["destination_key"] == "VIP"
    assert result["destination"]["chat_id"] == "-100111"
    assert result["publish_enabled"] is False


def test_publisher_cannot_manage_destinations(monkeypatch, tmp_path):
    path, tenant_id, connection_id, _ = _setup(tmp_path, TenantRole.PUBLISHER)
    _patch(monkeypatch, path)
    with pytest.raises(HTTPException) as exc:
        create_telegram_destination(
            TelegramDestinationCreate(connection_id=connection_id, destination_key="VIP", chat_id="-100111", kind="VIP"),
            "signed",
            tenant_id,
        )
    assert exc.value.status_code == 403


def test_cross_tenant_connection_is_not_exposed(monkeypatch, tmp_path):
    path, tenant_id, _, other_connection = _setup(tmp_path, TenantRole.ADMIN)
    _patch(monkeypatch, path)
    with pytest.raises(HTTPException) as exc:
        create_telegram_destination(
            TelegramDestinationCreate(connection_id=other_connection, destination_key="FREE", chat_id="-100222", kind="FREE"),
            "signed",
            tenant_id,
        )
    assert exc.value.status_code == 404
    assert exc.value.detail == "Telegram connection not found"
