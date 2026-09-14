from __future__ import annotations

import sqlite3

from app.provider_reports import provider_report
from app.provider_revenue import init_revenue_schema, record_payment
from app.provider_subscribers import create_customer, create_retail_plan, create_subscription, init_subscriber_schema
from app.tenancy import init_tenant_schema


def _db():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("CREATE TABLE users(telegram_id INTEGER PRIMARY KEY)")
    nexus = int(init_tenant_schema(con))
    other = int(con.execute(
        "INSERT INTO tenants(slug,business_name,display_name,status,timezone,locale,created_at,updated_at) "
        "VALUES('other','Other','Other','ACTIVE','UTC','en','x','x') RETURNING id"
    ).fetchone()[0])
    con.execute(
        "CREATE TABLE signals(id INTEGER PRIMARY KEY,tenant_id INTEGER,created_at TEXT,status TEXT,result_value REAL,entry_price REAL,stop_loss REAL,tp1 REAL)"
    )
    init_subscriber_schema(con)
    init_revenue_schema(con)
    customer = create_customer(con, tenant_id=nexus, display_name="Alice")
    plan = create_retail_plan(con, tenant_id=nexus, code="VIP", name="VIP", price_amount=19, price_currency="USD", duration_days=30)
    sub = create_subscription(con, tenant_id=nexus, customer_id=customer, plan_id=plan, starts_at="2026-09-01T00:00:00+00:00")
    other_customer = create_customer(con, tenant_id=other, display_name="Other")
    other_plan = create_retail_plan(con, tenant_id=other, code="VIP", name="Other VIP")
    other_sub = create_subscription(con, tenant_id=other, customer_id=other_customer, plan_id=other_plan, starts_at="2026-09-01T00:00:00+00:00")
    record_payment(con, tenant_id=nexus, amount=19, currency="USD", paid_at="2026-09-10T00:00:00+00:00", customer_id=customer, subscription_id=sub, reference="nx-1")
    record_payment(con, tenant_id=nexus, amount=5, currency="USD", paid_at="2026-09-11T00:00:00+00:00", customer_id=customer, subscription_id=sub, status="PENDING", reference="nx-pending")
    record_payment(con, tenant_id=other, amount=999, currency="USD", paid_at="2026-09-10T00:00:00+00:00", customer_id=other_customer, subscription_id=other_sub, reference="ot-1")
    con.executemany(
        "INSERT INTO signals VALUES(?,?,?,?,?,?,?,?)",
        [
            (1,nexus,"2026-09-10T00:00:00+00:00","TP_HIT",100,100,90,120),
            (2,nexus,"2026-09-11T00:00:00+00:00","SL_HIT",-50,100,95,110),
            (3,other,"2026-09-10T00:00:00+00:00","TP_HIT",999,100,90,120),
        ],
    )
    con.commit()
    return con, nexus, other


def test_report_is_tenant_scoped_and_period_filtered():
    con, nexus, _ = _db()
    report = provider_report(
        con,
        tenant_id=nexus,
        start="2026-09-01T00:00:00+00:00",
        end="2026-09-30T23:59:59+00:00",
    )
    assert report["status"] == "ready"
    assert report["total_revenue"] == 19.0
    assert report["currency"] == "USD"
    assert report["revenue_by_plan"] == [{"plan_code":"VIP","plan_name":"VIP","amount":19.0,"payment_count":1}]
    assert [p["reference"] for p in report["payments"]] == ["nx-pending", "nx-1"]
    assert report["signal_metrics"]["total_signals"] == 2
    assert report["signal_metrics"]["win_rate"] == 50.0
    assert report["signal_metrics"]["avg_rr"] == 2.0


def test_mixed_currency_blocks_aggregate_revenue():
    con, nexus, _ = _db()
    record_payment(con, tenant_id=nexus, amount=10, currency="EUR", paid_at="2026-09-12T00:00:00+00:00", reference="nx-eur")
    report = provider_report(con, tenant_id=nexus, start="2026-09-01", end="2026-09-30")
    assert report["status"] == "mixed_currency"
    assert report["total_revenue"] is None
    assert report["revenue_by_plan"] == []


def test_report_requires_complete_custom_period():
    con, nexus, _ = _db()
    try:
        provider_report(con, tenant_id=nexus, start="2026-09-01", end=None)
    except ValueError as exc:
        assert "start and end" in str(exc)
    else:
        raise AssertionError("expected ValueError")
