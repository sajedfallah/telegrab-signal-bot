from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.tenancy import (
    TenantRole,
    grant_membership,
    init_tenant_schema,
    resolve_tenant_context,
)
from scripts.phase1_tenant_migration import migrate


def _legacy_db(path: Path) -> None:
    con = sqlite3.connect(path)
    con.executescript(
        """
        PRAGMA foreign_keys=ON;
        CREATE TABLE users(telegram_id INTEGER PRIMARY KEY);
        CREATE TABLE payments(id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_id INTEGER);
        CREATE TABLE licenses(id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_id INTEGER);
        CREATE TABLE signals(id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT);
        CREATE TABLE signal_updates(id INTEGER PRIMARY KEY AUTOINCREMENT, signal_id INTEGER);
        CREATE TABLE subscriptions(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER);
        CREATE TABLE invoices(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER);
        CREATE TABLE autotrade_mt5_accounts(id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_id INTEGER);
        CREATE TABLE autotrade_account_change_requests(id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_id INTEGER);
        CREATE TABLE autotrade_mt5_account_history(id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_id INTEGER);
        CREATE TABLE autotrade_exchange_accounts(id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_id INTEGER);
        CREATE TABLE autotrade_trade_executions(id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_id INTEGER);
        CREATE TABLE autotrade_notifications(id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_id INTEGER);
        INSERT INTO users VALUES(1001);
        INSERT INTO users VALUES(2002);
        INSERT INTO payments(telegram_id) VALUES(1001);
        INSERT INTO licenses(telegram_id) VALUES(1001);
        INSERT INTO signals(symbol) VALUES('XAUUSD');
        """
    )
    con.commit()
    con.close()


def test_migration_backfills_nexus_and_is_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "legacy.db"
    _legacy_db(db)
    first = migrate(db)
    second = migrate(db)
    assert first["row_counts_before"] == first["row_counts_after"]
    assert second["tables_altered"] == []
    con = sqlite3.connect(db)
    nexus_id = con.execute("SELECT id FROM tenants WHERE slug='nexus'").fetchone()[0]
    assert con.execute("SELECT tenant_id FROM signals").fetchone()[0] == nexus_id
    assert con.execute("SELECT tenant_id FROM payments").fetchone()[0] == nexus_id
    assert con.execute("SELECT COUNT(*) FROM tenants WHERE slug='nexus'").fetchone()[0] == 1
    con.close()


def test_dry_run_rolls_back(tmp_path: Path) -> None:
    db = tmp_path / "legacy.db"
    _legacy_db(db)
    migrate(db, dry_run=True)
    con = sqlite3.connect(db)
    assert con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='tenants'").fetchone() is None
    con.close()


def test_membership_is_required_and_roles_are_enforced() -> None:
    con = sqlite3.connect(":memory:")
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("CREATE TABLE users(telegram_id INTEGER PRIMARY KEY)")
    con.executemany("INSERT INTO users VALUES(?)", [(1001,), (2002,)])
    nexus_id = init_tenant_schema(con)
    other_id = con.execute(
        "INSERT INTO tenants(slug,business_name,display_name,status,timezone,locale,created_at,updated_at) VALUES('other','Other','Other','ACTIVE','UTC','en','x','x') RETURNING id"
    ).fetchone()[0]
    grant_membership(con, tenant_id=nexus_id, user_id=1001, role=TenantRole.OWNER)
    ctx = resolve_tenant_context(con, user_id=1001, tenant_id=nexus_id)
    ctx.require(TenantRole.OWNER)
    ctx.require_at_least(TenantRole.ADMIN)
    with pytest.raises(PermissionError):
        resolve_tenant_context(con, user_id=1001, tenant_id=other_id)
    grant_membership(con, tenant_id=other_id, user_id=2002, role=TenantRole.VIEWER)
    viewer = resolve_tenant_context(con, user_id=2002, tenant_id=other_id)
    with pytest.raises(PermissionError):
        viewer.require_at_least(TenantRole.PUBLISHER)
