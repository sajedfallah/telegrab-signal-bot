from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

VALID_KEYS = (
    "asia_open",
    "asia_close",
    "london_open",
    "london_close",
    "newyork_open",
    "newyork_close",
)


def _default_db_path() -> Path:
    configured = os.getenv("SESSION_STICKER_DB_PATH", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / "nexus_session_stickers.db"


class SessionStickerStore:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path is not None else _default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=10.0)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA busy_timeout = 10000")
        return con

    def init_db(self) -> None:
        with self._connect() as con:
            con.execute("PRAGMA journal_mode = WAL")
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS session_stickers (
                    event_key TEXT PRIMARY KEY,
                    file_id TEXT NOT NULL,
                    file_unique_id TEXT,
                    set_name TEXT,
                    emoji TEXT,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS session_sticker_deliveries (
                    event_key TEXT NOT NULL,
                    local_date TEXT NOT NULL,
                    target TEXT NOT NULL,
                    message_id INTEGER,
                    sent_at TEXT NOT NULL,
                    PRIMARY KEY(event_key, local_date, target)
                );
                """
            )

    def set_sticker(self, event_key: str, sticker: object) -> None:
        if event_key not in VALID_KEYS:
            raise ValueError(f"unknown session event: {event_key}")
        with self._connect() as con:
            con.execute(
                """INSERT INTO session_stickers(event_key,file_id,file_unique_id,set_name,emoji,updated_at)
                   VALUES(?,?,?,?,?,?)
                   ON CONFLICT(event_key) DO UPDATE SET
                     file_id=excluded.file_id,
                     file_unique_id=excluded.file_unique_id,
                     set_name=excluded.set_name,
                     emoji=excluded.emoji,
                     updated_at=excluded.updated_at""",
                (
                    event_key,
                    getattr(sticker, "file_id"),
                    getattr(sticker, "file_unique_id", None),
                    getattr(sticker, "set_name", None),
                    getattr(sticker, "emoji", None),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def get_sticker(self, event_key: str):
        with self._connect() as con:
            return con.execute("SELECT * FROM session_stickers WHERE event_key=?", (event_key,)).fetchone()

    def all_configured(self):
        with self._connect() as con:
            return con.execute("SELECT * FROM session_stickers ORDER BY event_key").fetchall()

    def was_delivered(self, event_key: str, local_date: str, target: int | str) -> bool:
        with self._connect() as con:
            row = con.execute(
                "SELECT 1 FROM session_sticker_deliveries WHERE event_key=? AND local_date=? AND target=?",
                (event_key, local_date, str(target)),
            ).fetchone()
        return row is not None

    def mark_delivered(self, event_key: str, local_date: str, target: int | str, message_id: int | None) -> None:
        with self._connect() as con:
            con.execute(
                """INSERT INTO session_sticker_deliveries(event_key,local_date,target,message_id,sent_at)
                   VALUES(?,?,?,?,?)
                   ON CONFLICT(event_key,local_date,target) DO UPDATE SET
                     message_id=excluded.message_id,
                     sent_at=excluded.sent_at""",
                (event_key, local_date, str(target), message_id, datetime.now(timezone.utc).isoformat()),
            )


_store: SessionStickerStore | None = None


def get_store() -> SessionStickerStore:
    global _store
    if _store is None:
        _store = SessionStickerStore()
    return _store
