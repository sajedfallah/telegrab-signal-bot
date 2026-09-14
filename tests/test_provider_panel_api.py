from __future__ import annotations

import sqlite3

import pytest
from fastapi import HTTPException

from app.provider_panel_api import _dashboard, _tenant_context
from app.tenancy import TenantContext, TenantRole, grant_membership, init_tenant_schema


def test_dashboard_is_strictly_tenant_scoped(monkeypatch, tmp_path):
    path = tmp_path / "provider.db"
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("CREATE TABLE users(telegram_id INTEGER PRIMARY KEY)")
    con.executemany("INSERT INTO users VALUES(?)", [(1001,), (2002,)])
    nexus_id = init_tenant_schema(con)
    other_id = con.execute(
        "INSERT INTO tenants(slug,business_name,display_name,status,timezone,locale,created_at,updated_at) "
        "VALUES('other','Other','Other','ACTIVE','UTC','en','x','x') RETURNING id"
    ).fetchone()[0]
    con.execute(
        "CREATE TABLE signals(id INTEGER PRIMARY KEY,tenant_id INTEGER,code TEXT,market_type TEXT,symbol TEXT,"
        "direction TEXT,entry_price REAL,stop_loss REAL,tp1 REAL,status TEXT,result_value REAL,result_unit TEXT,"
        "created_at TEXT,closed_at TEXT)"
    )
    con.executemany(
        "INSERT INTO signals VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            (1, nexus_id, 'NX1', 'Gold', 'XAUUSD', 'BUY', 1, 0, 2, 'TP_HIT', 100, 'USD', 'x', 'x'),
            (2, other_id, 'OT1', 'Crypto', 'BTCUSDT', 'SELL', 1, 2, 0, 'SL_HIT', -50, 'USD', 'x', 'x'),
        ],
    )
    con.commit()
    con.close()

    class Conn:
        def __enter__(self):
            self.con = sqlite3.connect(path)
            self.con.row_factory = sqlite3.Row
            return self.con
        def __exit__(self, *_):
            self.con.close()

    monkeypatch.setattr("app.provider_panel_api.db.conn", lambda: Conn())
    data = _dashboard(TenantContext(nexus_id, 1001, TenantRole.OWNER))
    assert data["kpis"]["total_signals"] == 1
    assert data["recent_signals"][0]["symbol"] == "XAUUSD"
    assert all(row["symbol"] != "BTCUSDT" for row in data["recent_signals"])
    assert data["kpis"]["monthly_revenue"] is None
    assert data["availability"]["monthly_revenue"] is False


def test_tenant_header_is_not_authorization(monkeypatch, tmp_path):
    path = tmp_path / "provider.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE users(telegram_id INTEGER PRIMARY KEY)")
    con.executemany("INSERT INTO users VALUES(?)", [(1001,), (2002,)])
    nexus_id = init_tenant_schema(con)
    other_id = con.execute(
        "INSERT INTO tenants(slug,business_name,display_name,status,timezone,locale,created_at,updated_at) "
        "VALUES('other','Other','Other','ACTIVE','UTC','en','x','x') RETURNING id"
    ).fetchone()[0]
    grant_membership(con, tenant_id=nexus_id, user_id=1001, role=TenantRole.OWNER)
    con.commit()
    con.close()

    class Conn:
        def __enter__(self):
            self.con = sqlite3.connect(path)
            self.con.row_factory = sqlite3.Row
            return self.con
        def __exit__(self, *_):
            self.con.close()

    monkeypatch.setattr("app.provider_panel_api.db.conn", lambda: Conn())
    monkeypatch.setattr("app.provider_panel_api._authenticate_provider", lambda _: {"id": 1001})

    ok = _tenant_context("signed", nexus_id)
    assert ok.tenant_id == nexus_id
    with pytest.raises(HTTPException) as exc:
        _tenant_context("signed", other_id)
    assert exc.value.status_code == 403
