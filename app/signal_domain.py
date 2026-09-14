from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any


EVENT_TYPES = {
    "PARTIAL_CLOSE", "SL_CHANGED", "TP_CHANGED", "BREAKEVEN", "TRAILING",
    "TP_HIT", "SL_HIT", "MANUAL_CLOSE", "CLOSED",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in con.execute(f"PRAGMA table_info({table})").fetchall()}


def _exists(con: sqlite3.Connection, table: str) -> bool:
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def init_signal_domain_schema(con: sqlite3.Connection) -> None:
    """Add the normalized SignalPublication/SignalEvent layer without changing legacy runtime columns."""
    statements = (
        """CREATE TABLE IF NOT EXISTS signal_publications(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            signal_id INTEGER NOT NULL,
            destination_key TEXT NOT NULL,
            telegram_chat_id TEXT,
            root_message_id INTEGER,
            last_message_id INTEGER,
            status TEXT NOT NULL DEFAULT 'PUBLISHED',
            published_at TEXT,
            updated_at TEXT NOT NULL,
            UNIQUE(tenant_id,signal_id,destination_key),
            FOREIGN KEY(tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
            FOREIGN KEY(signal_id) REFERENCES signals(id) ON DELETE CASCADE
        )""",
        "CREATE INDEX IF NOT EXISTS idx_signal_publications_tenant_signal ON signal_publications(tenant_id,signal_id)",
        """CREATE TABLE IF NOT EXISTS signal_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            signal_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            payload_json TEXT,
            actor_user_id INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY(tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
            FOREIGN KEY(signal_id) REFERENCES signals(id) ON DELETE CASCADE
        )""",
        "CREATE INDEX IF NOT EXISTS idx_signal_events_tenant_signal ON signal_events(tenant_id,signal_id,id)",
    )
    for statement in statements:
        con.execute(statement)


def backfill_legacy_publications(con: sqlite3.Connection) -> int:
    """Copy legacy FREE/VIP message ids into normalized publications without assuming optional legacy columns exist."""
    init_signal_domain_schema(con)
    if not _exists(con, "signals"):
        return 0
    cols = _columns(con, "signals")
    required = {"id", "tenant_id", "free_message_id", "vip_message_id"}
    if not required.issubset(cols):
        return 0

    free_last_expr = "free_last_message_id" if "free_last_message_id" in cols else "free_message_id AS free_last_message_id"
    vip_last_expr = "vip_last_message_id" if "vip_last_message_id" in cols else "vip_message_id AS vip_last_message_id"
    created_expr = "created_at" if "created_at" in cols else "NULL AS created_at"
    sql = (
        "SELECT id,tenant_id,free_message_id,vip_message_id,"
        f"{free_last_expr},{vip_last_expr},{created_expr} "
        "FROM signals WHERE tenant_id IS NOT NULL"
    )

    count = 0
    for row in con.execute(sql).fetchall():
        for key, root_col, last_col in (
            ("FREE", "free_message_id", "free_last_message_id"),
            ("VIP", "vip_message_id", "vip_last_message_id"),
        ):
            root = row[root_col]
            if root is None:
                continue
            before = con.total_changes
            published_at = row["created_at"] or _now()
            con.execute(
                "INSERT OR IGNORE INTO signal_publications(tenant_id,signal_id,destination_key,root_message_id,last_message_id,published_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (int(row["tenant_id"]), int(row["id"]), key, int(root), int(row[last_col] or root), published_at, _now()),
            )
            if con.total_changes > before:
                count += 1
    return count


def list_signals(con: sqlite3.Connection, *, tenant_id: int, limit: int = 50) -> list[dict[str, Any]]:
    if not _exists(con, "signals") or "tenant_id" not in _columns(con, "signals"):
        return []
    limit = max(1, min(int(limit), 200))
    rows = con.execute(
        "SELECT * FROM signals WHERE tenant_id=? ORDER BY id DESC LIMIT ?", (tenant_id, limit)
    ).fetchall()
    return [dict(row) for row in rows]


def get_signal(con: sqlite3.Connection, *, tenant_id: int, signal_id: int) -> dict[str, Any] | None:
    if not _exists(con, "signals") or "tenant_id" not in _columns(con, "signals"):
        return None
    row = con.execute("SELECT * FROM signals WHERE id=? AND tenant_id=?", (signal_id, tenant_id)).fetchone()
    if row is None:
        return None
    data = dict(row)
    data["publications"] = []
    data["events"] = []
    if _exists(con, "signal_publications"):
        data["publications"] = [dict(r) for r in con.execute(
            "SELECT id,destination_key,telegram_chat_id,root_message_id,last_message_id,status,published_at,updated_at "
            "FROM signal_publications WHERE tenant_id=? AND signal_id=? ORDER BY id",
            (tenant_id, signal_id),
        ).fetchall()]
    if _exists(con, "signal_events"):
        events = con.execute(
            "SELECT id,event_type,payload_json,actor_user_id,created_at FROM signal_events "
            "WHERE tenant_id=? AND signal_id=? ORDER BY id", (tenant_id, signal_id)
        ).fetchall()
        data["events"] = [
            {**dict(r), "payload": json.loads(r["payload_json"] or "{}")}
            for r in events
        ]
        for event in data["events"]:
            event.pop("payload_json", None)
    return data


def record_signal_event(
    con: sqlite3.Connection, *, tenant_id: int, signal_id: int, event_type: str,
    payload: dict[str, Any] | None = None, actor_user_id: int | None = None,
) -> int:
    """Record an event only when the signal belongs to the same tenant."""
    kind = str(event_type).upper()
    if kind not in EVENT_TYPES:
        raise ValueError("unsupported signal event type")
    owner = con.execute("SELECT tenant_id FROM signals WHERE id=?", (signal_id,)).fetchone()
    if owner is None or int(owner[0]) != int(tenant_id):
        raise LookupError("signal not found")
    init_signal_domain_schema(con)
    cur = con.execute(
        "INSERT INTO signal_events(tenant_id,signal_id,event_type,payload_json,actor_user_id,created_at) VALUES(?,?,?,?,?,?)",
        (tenant_id, signal_id, kind, json.dumps(payload or {}, separators=(",", ":")), actor_user_id, _now()),
    )
    return int(cur.lastrowid)
