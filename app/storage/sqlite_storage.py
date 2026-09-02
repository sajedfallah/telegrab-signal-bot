from __future__ import annotations

import asyncio
import json
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StorageKey, StateType


class SQLiteStorage(BaseStorage):
    """Small persistent FSM storage for aiogram.

    State and data survive process restarts and are stored in a dedicated SQLite
    database. Each operation uses a short-lived connection so the storage is
    safe to use from asyncio.to_thread and does not share sqlite connections
    across threads.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @staticmethod
    def _key(key: StorageKey) -> str:
        # StorageKey fields have evolved across aiogram 3.x, so use getattr for
        # forward/backward compatibility while keeping a deterministic key.
        parts = (
            getattr(key, "bot_id", None),
            getattr(key, "business_connection_id", None),
            getattr(key, "chat_id", None),
            getattr(key, "user_id", None),
            getattr(key, "thread_id", None),
            getattr(key, "destiny", "default"),
        )
        return "|".join("" if value is None else str(value) for value in parts)

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=10.0)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=NORMAL")
        con.execute("PRAGMA busy_timeout=10000")
        return con

    def _init_db(self) -> None:
        with self._connect() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS fsm_context (
                    storage_key TEXT PRIMARY KEY,
                    state TEXT,
                    data_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def _set_state_sync(self, storage_key: str, state: str | None) -> None:
        with self._connect() as con:
            if state is None:
                row = con.execute("SELECT data_json FROM fsm_context WHERE storage_key=?", (storage_key,)).fetchone()
                if row is None:
                    return
                if row["data_json"] in (None, "", "{}"):
                    con.execute("DELETE FROM fsm_context WHERE storage_key=?", (storage_key,))
                else:
                    con.execute(
                        "UPDATE fsm_context SET state=NULL,updated_at=CURRENT_TIMESTAMP WHERE storage_key=?",
                        (storage_key,),
                    )
                return
            con.execute(
                """
                INSERT INTO fsm_context(storage_key,state,data_json)
                VALUES(?,?, '{}')
                ON CONFLICT(storage_key) DO UPDATE SET state=excluded.state,updated_at=CURRENT_TIMESTAMP
                """,
                (storage_key, state),
            )

    def _get_state_sync(self, storage_key: str) -> str | None:
        with self._connect() as con:
            row = con.execute("SELECT state FROM fsm_context WHERE storage_key=?", (storage_key,)).fetchone()
            return row["state"] if row else None

    def _set_data_sync(self, storage_key: str, data: dict[str, Any]) -> None:
        payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str)
        with self._connect() as con:
            if not data:
                row = con.execute("SELECT state FROM fsm_context WHERE storage_key=?", (storage_key,)).fetchone()
                if row and row["state"] is None:
                    con.execute("DELETE FROM fsm_context WHERE storage_key=?", (storage_key,))
                    return
            con.execute(
                """
                INSERT INTO fsm_context(storage_key,state,data_json)
                VALUES(?,NULL,?)
                ON CONFLICT(storage_key) DO UPDATE SET data_json=excluded.data_json,updated_at=CURRENT_TIMESTAMP
                """,
                (storage_key, payload),
            )

    def _get_data_sync(self, storage_key: str) -> dict[str, Any]:
        with self._connect() as con:
            row = con.execute("SELECT data_json FROM fsm_context WHERE storage_key=?", (storage_key,)).fetchone()
        if not row or not row["data_json"]:
            return {}
        try:
            value = json.loads(row["data_json"])
        except (TypeError, ValueError):
            return {}
        return value if isinstance(value, dict) else {}

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        resolved = state.state if isinstance(state, State) else state
        await asyncio.to_thread(self._set_state_sync, self._key(key), resolved)

    async def get_state(self, key: StorageKey) -> str | None:
        return await asyncio.to_thread(self._get_state_sync, self._key(key))

    async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        if not isinstance(data, Mapping):
            raise TypeError(f"FSM data must be a mapping, got {type(data).__name__}")
        await asyncio.to_thread(self._set_data_sync, self._key(key), dict(data))

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        return await asyncio.to_thread(self._get_data_sync, self._key(key))

    async def close(self) -> None:
        # Connections are intentionally short-lived; nothing persistent to close.
        return None
