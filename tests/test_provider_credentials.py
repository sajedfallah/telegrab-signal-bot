from __future__ import annotations

import sqlite3

import httpx
import pytest
from cryptography.fernet import Fernet

from app.provider_credentials import (
    SECRET_KIND_TELEGRAM_BOT_TOKEN,
    load_secret,
    store_secret,
    test_telegram_bot_token,
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
    return con, int(nexus), int(other)


def test_secret_is_encrypted_and_tenant_scoped() -> None:
    con, nexus, other = _db()
    key = Fernet.generate_key().decode("ascii")
    token = "123456:very-secret-token"
    ref = store_secret(con, tenant_id=nexus, kind=SECRET_KIND_TELEGRAM_BOT_TOKEN, plaintext=token, key=key)
    row = con.execute("SELECT ciphertext FROM provider_secrets").fetchone()
    assert token.encode() not in bytes(row[0])
    assert load_secret(con, tenant_id=nexus, secret_ref=ref, key=key) == token
    with pytest.raises(LookupError):
        load_secret(con, tenant_id=other, secret_ref=ref, key=key)


class _Client:
    def __init__(self, response: httpx.Response):
        self.response = response
        self.requested_url = ""

    def get(self, url: str):
        self.requested_url = url
        return self.response


def test_telegram_token_test_returns_identity_without_token() -> None:
    token = "123456:secret"
    client = _Client(httpx.Response(200, json={"ok": True, "result": {"id": 77, "username": "provider_bot", "first_name": "Provider"}}))
    result = test_telegram_bot_token(token, client=client)
    assert result == {"ok": True, "bot_id": 77, "username": "provider_bot", "first_name": "Provider"}
    assert token not in repr(result)
    assert token in client.requested_url


def test_telegram_token_rejection_is_sanitized() -> None:
    token = "123456:secret"
    client = _Client(httpx.Response(401, json={"ok": False, "description": f"bad {token}"}))
    result = test_telegram_bot_token(token, client=client)
    assert result == {"ok": False, "error": "telegram_rejected_credential"}
    assert token not in repr(result)
