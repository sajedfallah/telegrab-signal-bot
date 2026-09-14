from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any


CONNECTION_STATUSES = {"PENDING", "ACTIVE", "ERROR", "DISABLED"}
DESTINATION_KINDS = {"FREE", "VIP", "CHANNEL", "GROUP", "TOPIC"}
DESTINATION_STATUSES = {"ACTIVE", "DISABLED"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_telegram_tenant_schema(con: sqlite3.Connection) -> None:
    """Create tenant-owned Telegram routing metadata.

    Bot tokens are deliberately not stored here in plaintext. ``secret_ref`` is an
    opaque reference to the encrypted Provider credential store.
    """
    statements = (
        """CREATE TABLE IF NOT EXISTS telegram_connections(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            label TEXT NOT NULL,
            bot_username TEXT,
            secret_ref TEXT,
            status TEXT NOT NULL DEFAULT 'PENDING'
                CHECK(status IN ('PENDING','ACTIVE','ERROR','DISABLED')),
            last_tested_at TEXT,
            last_error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(tenant_id,label),
            FOREIGN KEY(tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
        )""",
        "CREATE INDEX IF NOT EXISTS idx_telegram_connections_tenant ON telegram_connections(tenant_id,status)",
        """CREATE TABLE IF NOT EXISTS telegram_destinations(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            connection_id INTEGER NOT NULL,
            destination_key TEXT NOT NULL,
            kind TEXT NOT NULL DEFAULT 'CHANNEL'
                CHECK(kind IN ('FREE','VIP','CHANNEL','GROUP','TOPIC')),
            chat_id TEXT NOT NULL,
            thread_id INTEGER,
            display_name TEXT,
            status TEXT NOT NULL DEFAULT 'ACTIVE'
                CHECK(status IN ('ACTIVE','DISABLED')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(tenant_id,destination_key),
            FOREIGN KEY(tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
            FOREIGN KEY(connection_id) REFERENCES telegram_connections(id) ON DELETE CASCADE
        )""",
        "CREATE INDEX IF NOT EXISTS idx_telegram_destinations_tenant ON telegram_destinations(tenant_id,status)",
    )
    for statement in statements:
        con.execute(statement)


def create_connection(
    con: sqlite3.Connection,
    *,
    tenant_id: int,
    label: str,
    bot_username: str | None = None,
    secret_ref: str | None = None,
    status: str = "PENDING",
) -> int:
    init_telegram_tenant_schema(con)
    normalized = str(status).upper()
    if normalized not in CONNECTION_STATUSES:
        raise ValueError("unsupported Telegram connection status")
    now = _now()
    cur = con.execute(
        "INSERT INTO telegram_connections(tenant_id,label,bot_username,secret_ref,status,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?)",
        (tenant_id, label.strip(), bot_username, secret_ref, normalized, now, now),
    )
    return int(cur.lastrowid)


def bind_connection_secret(
    con: sqlite3.Connection,
    *,
    tenant_id: int,
    connection_id: int,
    secret_ref: str,
) -> None:
    init_telegram_tenant_schema(con)
    cur = con.execute(
        "UPDATE telegram_connections SET secret_ref=?,status='PENDING',last_error=NULL,updated_at=? "
        "WHERE id=? AND tenant_id=?",
        (secret_ref, _now(), connection_id, tenant_id),
    )
    if cur.rowcount != 1:
        raise LookupError("Telegram connection not found")


def get_connection_private(con: sqlite3.Connection, *, tenant_id: int, connection_id: int) -> dict[str, Any]:
    init_telegram_tenant_schema(con)
    row = con.execute(
        "SELECT id,tenant_id,label,bot_username,secret_ref,status,last_tested_at,last_error,created_at,updated_at "
        "FROM telegram_connections WHERE id=? AND tenant_id=?",
        (connection_id, tenant_id),
    ).fetchone()
    if row is None:
        raise LookupError("Telegram connection not found")
    return dict(row)


def mark_connection_test(
    con: sqlite3.Connection,
    *,
    tenant_id: int,
    connection_id: int,
    ok: bool,
    bot_username: str | None = None,
    error: str | None = None,
) -> None:
    status = "ACTIVE" if ok else "ERROR"
    now = _now()
    cur = con.execute(
        "UPDATE telegram_connections SET bot_username=COALESCE(?,bot_username),status=?,last_tested_at=?,last_error=?,updated_at=? "
        "WHERE id=? AND tenant_id=?",
        (bot_username, status, now, None if ok else (error or "telegram_connection_failed"), now, connection_id, tenant_id),
    )
    if cur.rowcount != 1:
        raise LookupError("Telegram connection not found")


def create_destination(
    con: sqlite3.Connection,
    *,
    tenant_id: int,
    connection_id: int,
    destination_key: str,
    chat_id: str | int,
    kind: str = "CHANNEL",
    thread_id: int | None = None,
    display_name: str | None = None,
) -> int:
    init_telegram_tenant_schema(con)
    owner = con.execute("SELECT tenant_id FROM telegram_connections WHERE id=?", (connection_id,)).fetchone()
    if owner is None or int(owner[0]) != int(tenant_id):
        raise LookupError("Telegram connection not found")
    normalized_kind = str(kind).upper()
    if normalized_kind not in DESTINATION_KINDS:
        raise ValueError("unsupported Telegram destination kind")
    now = _now()
    cur = con.execute(
        "INSERT INTO telegram_destinations(tenant_id,connection_id,destination_key,kind,chat_id,thread_id,display_name,status,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,'ACTIVE',?,?)",
        (tenant_id, connection_id, destination_key.strip().upper(), normalized_kind, str(chat_id), thread_id, display_name, now, now),
    )
    return int(cur.lastrowid)


def list_connections(con: sqlite3.Connection, *, tenant_id: int) -> list[dict[str, Any]]:
    init_telegram_tenant_schema(con)
    rows = con.execute(
        "SELECT id,label,bot_username,status,last_tested_at,last_error,created_at,updated_at "
        "FROM telegram_connections WHERE tenant_id=? ORDER BY id", (tenant_id,)
    ).fetchall()
    return [dict(row) for row in rows]


def list_destinations(con: sqlite3.Connection, *, tenant_id: int) -> list[dict[str, Any]]:
    init_telegram_tenant_schema(con)
    rows = con.execute(
        "SELECT id,connection_id,destination_key,kind,chat_id,thread_id,display_name,status,created_at,updated_at "
        "FROM telegram_destinations WHERE tenant_id=? ORDER BY id", (tenant_id,)
    ).fetchall()
    return [dict(row) for row in rows]


def resolve_destination(con: sqlite3.Connection, *, tenant_id: int, destination_key: str) -> dict[str, Any] | None:
    init_telegram_tenant_schema(con)
    row = con.execute(
        "SELECT d.id,d.connection_id,d.destination_key,d.kind,d.chat_id,d.thread_id,d.display_name,d.status,"
        "c.bot_username,c.status AS connection_status "
        "FROM telegram_destinations d JOIN telegram_connections c ON c.id=d.connection_id "
        "WHERE d.tenant_id=? AND c.tenant_id=? AND d.destination_key=? "
        "AND d.status='ACTIVE' AND c.status='ACTIVE'",
        (tenant_id, tenant_id, destination_key.strip().upper()),
    ).fetchone()
    return dict(row) if row is not None else None
