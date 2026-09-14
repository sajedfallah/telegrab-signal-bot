from __future__ import annotations

import sqlite3

import pytest
from fastapi import HTTPException

from app.provider_subscribers_api import (
    CustomerCreateRequest,
    RetailPlanCreateRequest,
    SubscriptionCreateRequest,
    add_customer,
    add_retail_plan,
    add_subscription,
    subscribers,
)
from app.tenancy import TenantRole, grant_membership, init_tenant_schema


def _setup(tmp_path, role: TenantRole):
    path = tmp_path / "provider.db"
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("CREATE TABLE users(telegram_id INTEGER PRIMARY KEY)")
    con.execute("INSERT INTO users VALUES(1001)")
    tenant_id = int(init_tenant_schema(con))
    grant_membership(con, tenant_id=tenant_id, user_id=1001, role=role)
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


def _patch(monkeypatch, path):
    monkeypatch.setattr("app.provider_subscribers_api.db.conn", lambda: Conn(path))
    monkeypatch.setattr("app.provider_panel_api.db.conn", lambda: Conn(path))
    monkeypatch.setattr("app.provider_panel_api._authenticate_provider", lambda _: {"id": 1001})


def test_owner_can_create_customer_plan_subscription_and_list(monkeypatch, tmp_path) -> None:
    path, tenant_id = _setup(tmp_path, TenantRole.OWNER)
    _patch(monkeypatch, path)
    customer = add_customer(CustomerCreateRequest(external_user_id="u1", username="trader"), "signed", tenant_id)
    plan = add_retail_plan(RetailPlanCreateRequest(code="VIP", name="VIP", price_amount=19, price_currency="USD", duration_days=30), "signed", tenant_id)
    sub = add_subscription(SubscriptionCreateRequest(customer_id=customer["customer_id"], plan_id=plan["plan_id"], starts_at="2026-09-01T00:00:00+00:00", expires_at="2099-01-01T00:00:00+00:00"), "signed", tenant_id)
    assert sub["subscription_id"] > 0
    result = subscribers(100, "signed", tenant_id)
    assert result["summary"]["active_subscribers"] == 1
    assert result["items"][0]["username"] == "trader"


def test_publisher_cannot_manage_customers(monkeypatch, tmp_path) -> None:
    path, tenant_id = _setup(tmp_path, TenantRole.PUBLISHER)
    _patch(monkeypatch, path)
    with pytest.raises(HTTPException) as exc:
        add_customer(CustomerCreateRequest(external_user_id="u1"), "signed", tenant_id)
    assert exc.value.status_code == 403


def test_viewer_can_read_subscriber_list(monkeypatch, tmp_path) -> None:
    path, tenant_id = _setup(tmp_path, TenantRole.VIEWER)
    _patch(monkeypatch, path)
    result = subscribers(100, "signed", tenant_id)
    assert result["tenant_id"] == tenant_id
    assert result["count"] == 0
