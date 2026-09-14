from __future__ import annotations

import sqlite3

import pytest

from app.provider_revenue import init_revenue_schema, record_payment, revenue_summary
from app.provider_subscribers import create_customer, create_retail_plan, create_subscription, init_subscriber_schema
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
    init_revenue_schema(con)
    return con, nexus, other


def test_revenue_summary_is_strictly_tenant_scoped() -> None:
    con, nexus, other = _db()
    record_payment(con, tenant_id=nexus, amount=19, currency="USD", paid_at="2026-09-10T10:00:00+00:00", reference="nx-1")
    record_payment(con, tenant_id=other, amount=999, currency="USD", paid_at="2026-09-11T10:00:00+00:00", reference="ot-1")
    summary = revenue_summary(con, tenant_id=nexus, now_iso="2026-09-15T00:00:00+00:00")
    assert summary["status"] == "ready"
    assert summary["currency"] == "USD"
    assert summary["monthly_revenue"] == 19.0
    assert summary["series"] == [{"month": "2026-09", "amount": 19.0}]


def test_pending_failed_and_refunded_payments_are_not_revenue() -> None:
    con, nexus, _ = _db()
    record_payment(con, tenant_id=nexus, amount=19, currency="USD", paid_at="2026-09-01T00:00:00+00:00", status="PENDING", reference="p")
    record_payment(con, tenant_id=nexus, amount=20, currency="USD", paid_at="2026-09-02T00:00:00+00:00", status="FAILED", reference="f")
    record_payment(con, tenant_id=nexus, amount=21, currency="USD", paid_at="2026-09-03T00:00:00+00:00", status="REFUNDED", reference="r")
    record_payment(con, tenant_id=nexus, amount=22, currency="USD", paid_at="2026-09-04T00:00:00+00:00", status="SETTLED", reference="s")
    summary = revenue_summary(con, tenant_id=nexus, now_iso="2026-09-15T00:00:00+00:00")
    assert summary["monthly_revenue"] == 22.0


def test_cross_tenant_customer_reference_is_rejected() -> None:
    con, nexus, other = _db()
    customer = create_customer(con, tenant_id=other, external_user_id="other-user")
    with pytest.raises(LookupError):
        record_payment(
            con,
            tenant_id=nexus,
            customer_id=customer,
            amount=19,
            currency="USD",
            paid_at="2026-09-10T00:00:00+00:00",
        )


def test_subscription_reference_must_belong_to_same_tenant() -> None:
    con, nexus, other = _db()
    customer = create_customer(con, tenant_id=other, external_user_id="u")
    plan = create_retail_plan(con, tenant_id=other, code="VIP", name="VIP", price_amount=19, price_currency="USD")
    subscription = create_subscription(con, tenant_id=other, customer_id=customer, plan_id=plan, starts_at="2026-09-01T00:00:00+00:00")
    with pytest.raises(LookupError):
        record_payment(
            con,
            tenant_id=nexus,
            subscription_id=subscription,
            amount=19,
            currency="USD",
            paid_at="2026-09-10T00:00:00+00:00",
        )


def test_mixed_currency_revenue_is_not_silently_summed() -> None:
    con, nexus, _ = _db()
    record_payment(con, tenant_id=nexus, amount=19, currency="USD", paid_at="2026-09-01T00:00:00+00:00", reference="usd")
    record_payment(con, tenant_id=nexus, amount=20, currency="EUR", paid_at="2026-09-02T00:00:00+00:00", reference="eur")
    summary = revenue_summary(con, tenant_id=nexus, now_iso="2026-09-15T00:00:00+00:00")
    assert summary["status"] == "mixed_currency"
    assert summary["monthly_revenue"] is None
    assert summary["series"] == []


def test_summary_is_unavailable_before_revenue_migration() -> None:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    assert revenue_summary(con, tenant_id=1)["status"] == "unavailable"
