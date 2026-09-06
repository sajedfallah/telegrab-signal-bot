from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable


def _default_db_path() -> Path:
    configured = os.getenv("DAILY_STICKER_DB_PATH", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / "nexus_daily_stickers.db"


class StickerStore:
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
                CREATE TABLE IF NOT EXISTS daily_stickers (
                    date_key TEXT PRIMARY KEY,
                    file_id TEXT NOT NULL,
                    file_unique_id TEXT,
                    set_name TEXT,
                    emoji TEXT,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS daily_sticker_deliveries (
                    date_key TEXT NOT NULL,
                    target TEXT NOT NULL,
                    message_id INTEGER,
                    sent_at TEXT NOT NULL,
                    PRIMARY KEY (date_key, target)
                );
                """
            )

    @staticmethod
    def _key(value: date | str) -> str:
        if isinstance(value, date):
            return value.isoformat()
        return date.fromisoformat(str(value)).isoformat()

    def set_sticker(self, day: date | str, file_id: str, *, file_unique_id: str | None = None,
                    set_name: str | None = None, emoji: str | None = None) -> None:
        key = self._key(day)
        with self._connect() as con:
            con.execute(
                """INSERT INTO daily_stickers(date_key,file_id,file_unique_id,set_name,emoji,updated_at)
                   VALUES(?,?,?,?,?,?)
                   ON CONFLICT(date_key) DO UPDATE SET file_id=excluded.file_id,
                   file_unique_id=excluded.file_unique_id,set_name=excluded.set_name,
                   emoji=excluded.emoji,updated_at=excluded.updated_at""",
                (key, file_id, file_unique_id, set_name, emoji, datetime.now(timezone.utc).isoformat()),
            )

    def import_pack(self, first_day: date, stickers: Iterable[object], count: int) -> int:
        from datetime import timedelta
        imported = 0
        for offset, sticker in enumerate(list(stickers)[:count]):
            self.set_sticker(first_day + timedelta(days=offset), getattr(sticker, "file_id"),
                             file_unique_id=getattr(sticker, "file_unique_id", None),
                             set_name=getattr(sticker, "set_name", None), emoji=getattr(sticker, "emoji", None))
            imported += 1
        return imported

    def get_sticker(self, day: date | str):
        key = self._key(day)
        with self._connect() as con:
            return con.execute("SELECT * FROM daily_stickers WHERE date_key=?", (key,)).fetchone()

    def delete_sticker(self, day: date | str) -> bool:
        key = self._key(day)
        with self._connect() as con:
            return con.execute("DELETE FROM daily_stickers WHERE date_key=?", (key,)).rowcount > 0

    def was_delivered(self, day: date | str, target: int | str) -> bool:
        key = self._key(day)
        with self._connect() as con:
            return con.execute("SELECT 1 FROM daily_sticker_deliveries WHERE date_key=? AND target=?",
                               (key, str(target))).fetchone() is not None

    def mark_delivered(self, day: date | str, target: int | str, message_id: int | None) -> None:
        key = self._key(day)
        with self._connect() as con:
            con.execute(
                """INSERT INTO daily_sticker_deliveries(date_key,target,message_id,sent_at) VALUES(?,?,?,?)
                   ON CONFLICT(date_key,target) DO UPDATE SET message_id=excluded.message_id,sent_at=excluded.sent_at""",
                (key, str(target), message_id, datetime.now(timezone.utc).isoformat()),
            )

    def count_configured(self) -> int:
        with self._connect() as con:
            return int(con.execute("SELECT COUNT(*) FROM daily_stickers").fetchone()[0])


_store: StickerStore | None = None


def get_store() -> StickerStore:
    global _store
    if _store is None:
        _store = StickerStore()
    return _store
