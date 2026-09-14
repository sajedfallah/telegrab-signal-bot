from __future__ import annotations

import sqlite3

import httpx
import pytest
from cryptography.fernet import Fernet

from app.provider_credentials import SECRET_KIND_TELEGRAM_BOT_TOKEN, store_secret
from app.provider_publish import publish_signal_text
from app.signal_domain import init_signal_domain_schema
from app.telegram_tenant_domain import create_connection, create_destination
from app.tenancy import init_tenant_schema


class _Client:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def post(self, url: str, json: dict):
        self.calls.append((url, json))
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 901}})


def _db(monkeypatch) -> tuple[sqlite3.Connection, int, int, str]:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("CREATE TABLE users(telegram_id INTEGER PRIMARY KEY)")
    nexus = init_tenant_schema(con)
    other = int(con.execute(
        "INSERT INTO tenants(slug,business_name,display_name,status,timezone,locale,created_at,updated_at) "
        "VALUES('other','Other','Other','ACTIVE','UTC','en','x','x') RETURNING id"
    ).fetchone()[0])
    con.execute(
        "CREATE TABLE signals(id INTEGER PRIMARY KEY,tenant_id INTEGER NOT NULL,code TEXT,created_at TEXT)"
    )
    con.executemany(
        "INSERT INTO signals(id,tenant_id,code,created_at) VALUES(?,?,?,?)",
        [(1, nexus, 'NX1', 'x'), (2, other, 'OT1', 'x')],
    )
    init_signal_domain_schema(con)
    key = Fernet.generate_key().decode("ascii")
    monkeypatch.setenv("PROVIDER_CREDENTIALS_KEY", key)
    secret_ref = store_secret(
        con,
        tenant_id=nexus,
        kind=SECRET_KIND_TELEGRAM_BOT_TOKEN,
        plaintext="123456:nexus-provider-token",
    )
    connection = create_connection(
        con,
        tenant_id=nexus,
        label="primary",
        bot_username="nexus_provider_bot",
        secret_ref=secret_ref,
        status="ACTIVE",
    )
    create_destination(
        con,
        tenant_id=nexus,
        connection_id=connection,
        destination_key="VIP",
        chat_id="-100111",
        kind="VIP",
    )
    con.commit()
    return con, nexus, other, "123456:nexus-provider-token"


def test_publish_uses_only_tenant_bot_and_records_receipt(monkeypatch) -> None:
    con, nexus, _, token = _db(monkeypatch)
    client = _Client()
    result = publish_signal_text(
        con,
        tenant_id=nexus,
        signal_id=1,
        destination_key="VIP",
        text="Provider signal",
        client=client,
    )
    assert result["message_id"] == 901
    assert result["chat_id"] == "-100111"
    assert client.calls == [
        (f"https://api.telegram.org/bot{token}/sendMessage", {"chat_id": "-100111", "text": "Provider signal"})
    ]
    row = con.execute(
        "SELECT tenant_id,signal_id,destination_key,telegram_chat_id,root_message_id,last_message_id,status "
        "FROM signal_publications"
    ).fetchone()
    assert tuple(row) == (nexus, 1, "VIP", "-100111", 901, 901, "PUBLISHED")


def test_cross_tenant_signal_is_never_published(monkeypatch) -> None:
    con, nexus, other, _ = _db(monkeypatch)
    client = _Client()
    with pytest.raises(LookupError):
        publish_signal_text(
            con,
            tenant_id=nexus,
            signal_id=2,
            destination_key="VIP",
            text="must not send",
            client=client,
        )
    assert client.calls == []
    assert con.execute("SELECT COUNT(*) FROM signal_publications").fetchone()[0] == 0
    assert other != nexus


def test_missing_destination_has_no_global_fallback(monkeypatch) -> None:
    con, nexus, _, _ = _db(monkeypatch)
    monkeypatch.setenv("BOT_TOKEN", "999999:global-nexus-token")
    client = _Client()
    with pytest.raises(LookupError):
        publish_signal_text(
            con,
            tenant_id=nexus,
            signal_id=1,
            destination_key="FREE",
            text="must not fallback",
            client=client,
        )
    assert client.calls == []


def test_republish_same_signal_destination_is_blocked(monkeypatch) -> None:
    con, nexus, _, _ = _db(monkeypatch)
    client = _Client()
    publish_signal_text(con, tenant_id=nexus, signal_id=1, destination_key="VIP", text="first", client=client)
    with pytest.raises(FileExistsError):
        publish_signal_text(con, tenant_id=nexus, signal_id=1, destination_key="VIP", text="second", client=client)
    assert len(client.calls) == 1
