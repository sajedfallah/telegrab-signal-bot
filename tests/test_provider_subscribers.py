from __future__ import annotations

import sqlite3

import pytest

from app.provider_subscribers import (
    create_customer,
    create_retail_plan,
    create_subscription,
    init_subscriber_schema,
    list_subscribers,
    subscriber_summary,
)
from app.tenancy import init_tenant_schema


def _db() -> tuple[sqlite3.Connection, int, int]:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("CREATE TABLE users(telegram_id INTEGER PRIMARY KEY)")
    nexus = int(init_tenant_schema(con))
    other = int(con.execute(
        "INSERT INTO tenants(slug,business_name,display_name,status,timezone,locale,created_at,updated_at) "
        "VALUES('other','Other','Other','ACTIVE','UTC','en','x','x') RETURNING id"
    ).fetchone()[0])
    init_subscriber_schema(con)
    return con, nexus, other


def test_subscriber_summary_is_strictly_tenant_scoped() -> None:
    con, nexus, other = _db()
    nx_customer = create_customer(con, tenant_id=nexus, external_user_id="100", username="nx")
    nx_plan = create_retail_plan(con, tenant_id=nexus, code="VIP", name="VIP", price_amount=19, price_currency="USD")
    create_subscription(con, tenant_id=nexus, customer_id=nx_customer, plan_id=nx_plan, starts_at="2026-09-01T00:00:00+00:00", expires_at="2026-10-01T00:00:00+00:00")
    ot_customer = create_customer(con, tenant_id=other, external_user_id="200", username="ot")
    ot_plan = create_retail_plan(con, tenant_id=other, code="VIP", name="VIP")
    create_subscription(con, tenant_id=other, customer_id=ot_customer, plan_id=ot_plan, starts_at="2026-09-01T00:00:00+00:00", expires_at="2026-10-01T00:00:00+00:00")

    nx = subscriber_summary(con, tenant_id=nexus, now_iso="2026-09-15T00:00:00+00:00")
    ot = subscriber_summary(con, tenant_id=other, now_iso="2026-09-15T00:00:00+00:00")
    assert nx["active_subscribers"] == 1
    assert ot["active_subscribers"] == 1
    assert [row["username"] for row in list_subscribers(con, tenant_id=nexus)] == ["nx"]


def test_expired_subscription_is_not_counted_active() -> None:
    con, nexus, _ = _db()
    customer = create_customer(con, tenant_id=nexus, external_user_id="100")
    plan = create_retail_plan(con, tenant_id=nexus, code="VIP", name="VIP")
    create_subscription(con, tenant_id=nexus, customer_id=customer, plan_id=plan, starts_at="2026-08-01", expires_at="2026-09-01")
    summary = subscriber_summary(con, tenant_id=nexus, now_iso="2026-09-15")
    assert summary["active_subscribers"] == 0


def test_cross_tenant_subscription_references_are_rejected() -> None:
    con, nexus, other = _db()
    customer = create_customer(con, tenant_id=nexus, external_user_id="100")
    other_plan = create_retail_plan(con, tenant_id=other, code="VIP", name="VIP")
    with pytest.raises(LookupError):
        create_subscription(con, tenant_id=nexus, customer_id=customer, plan_id=other_plan, starts_at="2026-09-01")


def test_summary_is_truthfully_unavailable_before_migration() -> None:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    result = subscriber_summary(con, tenant_id=1)
    assert result["status"] == "unavailable"
    assert result["active_subscribers"] is None
