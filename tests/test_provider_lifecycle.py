from __future__ import annotations

import sqlite3

import httpx
from cryptography.fernet import Fernet

from app.provider_credentials import SECRET_KIND_TELEGRAM_BOT_TOKEN, store_secret
from app.provider_lifecycle import format_position_update, reply_signal_event
from app.signal_domain import init_signal_domain_schema
from app.telegram_tenant_domain import create_connection, create_destination
from app.tenancy import init_tenant_schema


class _Client:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.next_message_id = 901

    def post(self, url: str, json: dict):
        self.calls.append((url, json))
        message_id = self.next_message_id
        self.next_message_id += 1
        return httpx.Response(200, json={"ok": True, "result": {"message_id": message_id}})


def _db(monkeypatch):
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("CREATE TABLE users(telegram_id INTEGER PRIMARY KEY)")
    tenant_id = int(init_tenant_schema(con))
    con.execute(
        "CREATE TABLE signals(id INTEGER PRIMARY KEY,tenant_id INTEGER NOT NULL,code TEXT)"
    )
    con.execute("INSERT INTO signals(id,tenant_id,code) VALUES(1,?,?)", (tenant_id, "NX1"))
    init_signal_domain_schema(con)
    key = Fernet.generate_key().decode("ascii")
    monkeypatch.setenv("PROVIDER_CREDENTIALS_KEY", key)
    token = "123456:tenant-private-token"
    secret_ref = store_secret(con, tenant_id=tenant_id, kind=SECRET_KIND_TELEGRAM_BOT_TOKEN, plaintext=token)
    connection_id = create_connection(con, tenant_id=tenant_id, label="primary", secret_ref=secret_ref, status="ACTIVE")
    create_destination(con, tenant_id=tenant_id, connection_id=connection_id, destination_key="VIP", chat_id="-100111", kind="VIP")
    con.execute(
        "INSERT INTO signal_publications(tenant_id,signal_id,destination_key,telegram_chat_id,root_message_id,last_message_id,status,published_at,updated_at) "
        "VALUES(?,1,'VIP','-100111',500,500,'PUBLISHED','x','x')",
        (tenant_id,),
    )
    con.commit()
    return con, tenant_id, token


def test_partial_close_requires_stage_profit_and_formats_tp_sl() -> None:
    text = format_position_update(
        "PARTIAL_CLOSE",
        {
            "brand": "Provider X",
            "closed_volume": 0.01,
            "closed_percent": 50,
            "remaining_volume": 0.01,
            "remaining_percent": 50,
            "profit_usd": 12.4,
            "tp": 2450,
            "sl": 2410,
        },
    )
    assert "Profit this stage: $12.4" in text
    assert "TP: 2450" in text
    assert "SL: 2410" in text
    assert "Position Status: ACTIVE" in text


def test_lifecycle_replies_chain_on_last_message_and_update_receipts(monkeypatch) -> None:
    con, tenant_id, token = _db(monkeypatch)
    client = _Client()
    payload = {
        "closed_volume": 0.01,
        "closed_percent": 50,
        "remaining_volume": 0.01,
        "remaining_percent": 50,
        "profit_usd": 9.5,
        "tp": 2450,
        "sl": 2420,
    }
    first = reply_signal_event(
        con,
        tenant_id=tenant_id,
        signal_id=1,
        destination_key="VIP",
        event_type="PARTIAL_CLOSE",
        payload=payload,
        actor_user_id=1001,
        client=client,
    )
    assert first["reply_to_message_id"] == 500
    assert first["message_id"] == 901
    assert token in client.calls[0][0]
    assert client.calls[0][1]["reply_parameters"]["message_id"] == 500

    second = reply_signal_event(
        con,
        tenant_id=tenant_id,
        signal_id=1,
        destination_key="VIP",
        event_type="TRAILING",
        payload={"tp": 2450, "sl": 2430},
        actor_user_id=1001,
        client=client,
    )
    assert second["reply_to_message_id"] == 901
    assert client.calls[1][1]["reply_parameters"]["message_id"] == 901
    row = con.execute("SELECT root_message_id,last_message_id,status FROM signal_publications").fetchone()
    assert tuple(row) == (500, 902, "PUBLISHED")
    assert con.execute("SELECT COUNT(*) FROM signal_events").fetchone()[0] == 2


def test_terminal_event_closes_publication(monkeypatch) -> None:
    con, tenant_id, _ = _db(monkeypatch)
    client = _Client()
    result = reply_signal_event(
        con,
        tenant_id=tenant_id,
        signal_id=1,
        destination_key="VIP",
        event_type="CLOSED",
        payload={"tp": 2450, "sl": 2420, "position_status": "CLOSED"},
        client=client,
    )
    assert result["publication_status"] == "CLOSED"
    assert con.execute("SELECT status FROM signal_publications").fetchone()[0] == "CLOSED"
