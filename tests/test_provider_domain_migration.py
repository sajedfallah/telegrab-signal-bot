from __future__ import annotations

import sqlite3
from pathlib import Path

from app.tenancy import init_tenant_schema
from scripts.provider_domain_migration import PROVIDER_TABLES, migrate


def _table_exists(con: sqlite3.Connection, table: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _legacy_db(path: Path) -> int:
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("CREATE TABLE users(telegram_id INTEGER PRIMARY KEY)")
    tenant_id = int(init_tenant_schema(con))
    con.execute(
        "CREATE TABLE signals(id INTEGER PRIMARY KEY,tenant_id INTEGER,free_message_id INTEGER,vip_message_id INTEGER)"
    )
    con.execute(
        "INSERT INTO signals(id,tenant_id,free_message_id,vip_message_id) VALUES(1,?,?,NULL)",
        (tenant_id, 501),
    )
    con.commit()
    con.close()
    return tenant_id


def test_provider_migration_dry_run_rolls_back_schema(tmp_path) -> None:
    path = tmp_path / "provider.db"
    _legacy_db(path)
    report = migrate(path, dry_run=True)
    assert report["dry_run"] is True
    assert report["legacy_publications_backfilled"] == 1

    con = sqlite3.connect(path)
    for table in PROVIDER_TABLES:
        assert not _table_exists(con, table)
    assert con.execute("SELECT free_message_id FROM signals WHERE id=1").fetchone()[0] == 501
    con.close()


def test_provider_migration_is_additive_and_idempotent(tmp_path) -> None:
    path = tmp_path / "provider.db"
    tenant_id = _legacy_db(path)

    first = migrate(path)
    assert first["legacy_publications_backfilled"] == 1
    assert first["nexus_tenant_id"] == tenant_id

    con = sqlite3.connect(path)
    for table in PROVIDER_TABLES:
        assert _table_exists(con, table)
    publication = con.execute(
        "SELECT tenant_id,signal_id,destination_key,root_message_id,last_message_id FROM signal_publications"
    ).fetchone()
    assert tuple(publication) == (tenant_id, 1, "FREE", 501, 501)
    con.close()

    second = migrate(path)
    assert second["legacy_publications_backfilled"] == 0
    assert second["row_counts_before"] == second["row_counts_after"]
