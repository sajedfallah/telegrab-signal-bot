from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from typing import Any

import httpx
from cryptography.fernet import Fernet, InvalidToken


SECRET_KIND_TELEGRAM_BOT_TOKEN = "TELEGRAM_BOT_TOKEN"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fernet(key: str | None = None) -> Fernet:
    raw = (key or os.getenv("PROVIDER_CREDENTIALS_KEY", "")).strip()
    if not raw:
        raise RuntimeError("PROVIDER_CREDENTIALS_KEY is not configured")
    try:
        return Fernet(raw.encode("ascii"))
    except Exception as exc:
        raise RuntimeError("PROVIDER_CREDENTIALS_KEY is invalid") from exc


def init_provider_secret_schema(con: sqlite3.Connection) -> None:
    statements = (
        """CREATE TABLE IF NOT EXISTS provider_secrets(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            kind TEXT NOT NULL,
            ciphertext BLOB NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
        )""",
        "CREATE INDEX IF NOT EXISTS idx_provider_secrets_tenant_kind ON provider_secrets(tenant_id,kind)",
    )
    for statement in statements:
        con.execute(statement)


def store_secret(
    con: sqlite3.Connection,
    *,
    tenant_id: int,
    kind: str,
    plaintext: str,
    key: str | None = None,
) -> str:
    if not plaintext or not plaintext.strip():
        raise ValueError("secret is required")
    init_provider_secret_schema(con)
    now = _now()
    ciphertext = _fernet(key).encrypt(plaintext.strip().encode("utf-8"))
    cur = con.execute(
        "INSERT INTO provider_secrets(tenant_id,kind,ciphertext,created_at,updated_at) VALUES(?,?,?,?,?)",
        (tenant_id, str(kind).upper(), ciphertext, now, now),
    )
    return f"provider-secret:{int(cur.lastrowid)}"


def load_secret(
    con: sqlite3.Connection,
    *,
    tenant_id: int,
    secret_ref: str,
    key: str | None = None,
) -> str:
    prefix = "provider-secret:"
    if not secret_ref.startswith(prefix):
        raise LookupError("secret not found")
    try:
        secret_id = int(secret_ref[len(prefix):])
    except ValueError as exc:
        raise LookupError("secret not found") from exc
    row = con.execute(
        "SELECT ciphertext FROM provider_secrets WHERE id=? AND tenant_id=?",
        (secret_id, tenant_id),
    ).fetchone()
    if row is None:
        raise LookupError("secret not found")
    try:
        return _fernet(key).decrypt(bytes(row[0])).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError("stored credential cannot be decrypted") from exc


def test_telegram_bot_token(
    token: str,
    *,
    timeout_seconds: float = 8.0,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Validate a bot token through Telegram getMe without returning or logging it."""
    if not token or not token.strip():
        return {"ok": False, "error": "credential_missing"}
    own_client = client is None
    session = client or httpx.Client(timeout=timeout_seconds)
    try:
        response = session.get(f"https://api.telegram.org/bot{token.strip()}/getMe")
        if response.status_code != 200:
            return {"ok": False, "error": "telegram_rejected_credential"}
        payload = response.json()
        if not payload.get("ok") or not isinstance(payload.get("result"), dict):
            return {"ok": False, "error": "telegram_rejected_credential"}
        bot = payload["result"]
        return {
            "ok": True,
            "bot_id": bot.get("id"),
            "username": bot.get("username"),
            "first_name": bot.get("first_name"),
        }
    except (httpx.HTTPError, ValueError):
        return {"ok": False, "error": "telegram_connection_failed"}
    finally:
        if own_client:
            session.close()
