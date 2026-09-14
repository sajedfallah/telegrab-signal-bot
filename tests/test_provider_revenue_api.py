from __future__ import annotations

import sqlite3

import pytest
from fastapi import HTTPException

from app.provider_revenue import init_revenue_schema
from app.provider_revenue_api import PaymentCreateRequest, add_payment, revenue
from app.provider_subscribers import init_subscriber_schema
from app.tenancy import TenantContext, TenantRole, init_tenant_schema


def _path(tmp_path):
    path = tmp_path / "provider.db"
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("CREATE TABLE users(telegram_id INTEGER PRIMARY KEY)")
    tenant_id = int(init_tenant_schema(con))
    init_subscriber_schema(con)
    init_revenue_schema(con)
    con.commit()
    con.close()
    return path, tenant_id


class Conn:
    def __init__(self, path):
        self.path = path
    def __enter__(self):
        self.con = sqlite3.connect(self.path)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA foreign_keys=ON")
        return self.con
    def __exit__(self, exc_type, *_):
        if exc_type is None:
            self.con.commit()
        else:
            self.con.rollback()
        self.con.close()


def test_owner_can_record_payment_and_viewer_can_read(monkeypatch, tmp_path) -> None:
    path, tenant_id = _path(tmp_path)
    monkeypatch.setattr("app.provider_revenue_api.db.conn", lambda: Conn(path))
    monkeypatch.setattr(
        "app.provider_revenue_api._tenant_context",
        lambda *_: TenantContext(tenant_id, 1001, TenantRole.OWNER),
    )
    created = add_payment(
        PaymentCreateRequest(
            amount=19,
            currency="USD",
            paid_at="2026-09-15T00:00:00+00:00",
            reference="pay-1",
        ),
        "signed",
        tenant_id,
    )
    assert created["payment_id"] > 0

    monkeypatch.setattr(
        "app.provider_revenue_api._tenant_context",
        lambda *_: TenantContext(tenant_id, 2002, TenantRole.VIEWER),
    )
    data = revenue(12, "signed", tenant_id)
    assert data["summary"]["monthly_revenue"] == 19.0
    assert data["summary"]["currency"] == "USD"
    assert data["count"] == 1


def test_viewer_cannot_record_payment(monkeypatch, tmp_path) -> None:
    path, tenant_id = _path(tmp_path)
    monkeypatch.setattr("app.provider_revenue_api.db.conn", lambda: Conn(path))
    monkeypatch.setattr(
        "app.provider_revenue_api._tenant_context",
        lambda *_: TenantContext(tenant_id, 2002, TenantRole.VIEWER),
    )
    with pytest.raises(HTTPException) as exc:
        add_payment(
            PaymentCreateRequest(amount=19, currency="USD", paid_at="2026-09-15T00:00:00+00:00"),
            "signed",
            tenant_id,
        )
    assert exc.value.status_code == 403


def test_admin_cannot_manage_billing_when_policy_is_owner_only(monkeypatch, tmp_path) -> None:
    path, tenant_id = _path(tmp_path)
    monkeypatch.setattr("app.provider_revenue_api.db.conn", lambda: Conn(path))
    monkeypatch.setattr(
        "app.provider_revenue_api._tenant_context",
        lambda *_: TenantContext(tenant_id, 3003, TenantRole.ADMIN),
    )
    with pytest.raises(HTTPException) as exc:
        add_payment(
            PaymentCreateRequest(amount=19, currency="USD", paid_at="2026-09-15T00:00:00+00:00"),
            "signed",
            tenant_id,
        )
    assert exc.value.status_code == 403
