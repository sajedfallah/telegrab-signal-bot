from __future__ import annotations

import sqlite3

import pytest
from fastapi import HTTPException

from app.provider_reports_api import reports
from app.provider_revenue import init_revenue_schema, record_payment
from app.tenancy import TenantContext, TenantRole, init_tenant_schema


def test_reports_api_reads_only_requested_tenant(monkeypatch, tmp_path):
    path = tmp_path / "provider.db"
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("CREATE TABLE users(telegram_id INTEGER PRIMARY KEY)")
    tenant = int(init_tenant_schema(con))
    init_revenue_schema(con)
    record_payment(con, tenant_id=tenant, amount=25, currency="USD", paid_at="2026-09-10T00:00:00+00:00", reference="r1")
    con.commit(); con.close()

    class Conn:
        def __enter__(self):
            self.con = sqlite3.connect(path)
            self.con.row_factory = sqlite3.Row
            return self.con
        def __exit__(self, *_):
            self.con.close()

    monkeypatch.setattr("app.provider_reports_api.db.conn", lambda: Conn())
    monkeypatch.setattr("app.provider_reports_api._tenant_context", lambda *_: TenantContext(tenant, 1001, TenantRole.VIEWER))
    result = reports(days=30, start="2026-09-01", end="2026-09-30", payment_limit=50, x_telegram_init_data="signed", x_tenant_id=tenant)
    assert result["tenant_id"] == tenant
    assert result["report"]["total_revenue"] == 25.0


def test_reports_api_maps_bad_period_to_422(monkeypatch):
    monkeypatch.setattr("app.provider_reports_api._tenant_context", lambda *_: TenantContext(7, 1001, TenantRole.OWNER))
    class Conn:
        def __enter__(self):
            con = sqlite3.connect(":memory:")
            con.row_factory = sqlite3.Row
            self.con = con
            return con
        def __exit__(self, *_):
            self.con.close()
    monkeypatch.setattr("app.provider_reports_api.db.conn", lambda: Conn())
    with pytest.raises(HTTPException) as exc:
        reports(days=30, start="2026-09-30", end="2026-09-01", payment_limit=50, x_telegram_init_data="signed", x_tenant_id=7)
    assert exc.value.status_code == 422
