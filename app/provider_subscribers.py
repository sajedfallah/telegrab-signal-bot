from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any


CUSTOMER_STATUSES = {"ACTIVE", "INACTIVE", "BLOCKED"}
PLAN_STATUSES = {"ACTIVE", "INACTIVE"}
SUBSCRIPTION_STATUSES = {"ACTIVE", "EXPIRED", "CANCELLED", "PAUSED"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_subscriber_schema(con: sqlite3.Connection) -> None:
    statements = (
        """CREATE TABLE IF NOT EXISTS provider_customers(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            external_user_id TEXT,
            display_name TEXT,
            username TEXT,
            email TEXT,
            status TEXT NOT NULL DEFAULT 'ACTIVE'
                CHECK(status IN ('ACTIVE','INACTIVE','BLOCKED')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(tenant_id,external_user_id),
            FOREIGN KEY(tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
        )""",
        "CREATE INDEX IF NOT EXISTS idx_provider_customers_tenant_status ON provider_customers(tenant_id,status,id)",
        """CREATE TABLE IF NOT EXISTS provider_retail_plans(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            code TEXT NOT NULL,
            name TEXT NOT NULL,
            price_amount REAL,
            price_currency TEXT,
            duration_days INTEGER,
            status TEXT NOT NULL DEFAULT 'ACTIVE'
                CHECK(status IN ('ACTIVE','INACTIVE')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(tenant_id,code),
            FOREIGN KEY(tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
        )""",
        "CREATE INDEX IF NOT EXISTS idx_provider_retail_plans_tenant_status ON provider_retail_plans(tenant_id,status,id)",
        """CREATE TABLE IF NOT EXISTS provider_customer_subscriptions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            customer_id INTEGER NOT NULL,
            plan_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'ACTIVE'
                CHECK(status IN ('ACTIVE','EXPIRED','CANCELLED','PAUSED')),
            starts_at TEXT NOT NULL,
            expires_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
            FOREIGN KEY(customer_id) REFERENCES provider_customers(id) ON DELETE CASCADE,
            FOREIGN KEY(plan_id) REFERENCES provider_retail_plans(id) ON DELETE RESTRICT
        )""",
        "CREATE INDEX IF NOT EXISTS idx_provider_subscriptions_tenant_status ON provider_customer_subscriptions(tenant_id,status,expires_at,id)",
        "CREATE INDEX IF NOT EXISTS idx_provider_subscriptions_customer ON provider_customer_subscriptions(tenant_id,customer_id,id)",
    )
    for statement in statements:
        con.execute(statement)


def _require_tenant_row(con: sqlite3.Connection, table: str, row_id: int, tenant_id: int) -> sqlite3.Row:
    row = con.execute(f"SELECT * FROM {table} WHERE id=? AND tenant_id=?", (row_id, tenant_id)).fetchone()
    if row is None:
        raise LookupError(f"{table} resource not found")
    return row


def create_customer(
    con: sqlite3.Connection,
    *,
    tenant_id: int,
    external_user_id: str | None = None,
    display_name: str | None = None,
    username: str | None = None,
    email: str | None = None,
    status: str = "ACTIVE",
) -> int:
    init_subscriber_schema(con)
    normalized_status = status.upper()
    if normalized_status not in CUSTOMER_STATUSES:
        raise ValueError("invalid customer status")
    now = _now()
    cur = con.execute(
        "INSERT INTO provider_customers(tenant_id,external_user_id,display_name,username,email,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
        (tenant_id, (external_user_id or "").strip() or None, (display_name or "").strip() or None, (username or "").strip() or None, (email or "").strip() or None, normalized_status, now, now),
    )
    return int(cur.lastrowid)


def create_retail_plan(
    con: sqlite3.Connection,
    *,
    tenant_id: int,
    code: str,
    name: str,
    price_amount: float | None = None,
    price_currency: str | None = None,
    duration_days: int | None = None,
    status: str = "ACTIVE",
) -> int:
    init_subscriber_schema(con)
    normalized_status = status.upper()
    if normalized_status not in PLAN_STATUSES:
        raise ValueError("invalid retail plan status")
    if not code.strip() or not name.strip():
        raise ValueError("plan code and name are required")
    if duration_days is not None and duration_days <= 0:
        raise ValueError("duration_days must be positive")
    now = _now()
    cur = con.execute(
        "INSERT INTO provider_retail_plans(tenant_id,code,name,price_amount,price_currency,duration_days,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
        (tenant_id, code.strip().upper(), name.strip(), price_amount, (price_currency or "").strip().upper() or None, duration_days, normalized_status, now, now),
    )
    return int(cur.lastrowid)


def create_subscription(
    con: sqlite3.Connection,
    *,
    tenant_id: int,
    customer_id: int,
    plan_id: int,
    starts_at: str,
    expires_at: str | None = None,
    status: str = "ACTIVE",
) -> int:
    init_subscriber_schema(con)
    normalized_status = status.upper()
    if normalized_status not in SUBSCRIPTION_STATUSES:
        raise ValueError("invalid subscription status")
    _require_tenant_row(con, "provider_customers", customer_id, tenant_id)
    _require_tenant_row(con, "provider_retail_plans", plan_id, tenant_id)
    if not starts_at.strip():
        raise ValueError("starts_at is required")
    now = _now()
    cur = con.execute(
        "INSERT INTO provider_customer_subscriptions(tenant_id,customer_id,plan_id,status,starts_at,expires_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
        (tenant_id, customer_id, plan_id, normalized_status, starts_at.strip(), (expires_at or "").strip() or None, now, now),
    )
    return int(cur.lastrowid)


def subscriber_summary(con: sqlite3.Connection, *, tenant_id: int, now_iso: str | None = None) -> dict[str, Any]:
    required = {"provider_customers", "provider_retail_plans", "provider_customer_subscriptions"}
    present = {
        str(row[0])
        for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    if not required.issubset(present):
        return {
            "status": "unavailable",
            "reason": "provider subscriber domain not migrated",
            "active_subscribers": None,
            "total_customers": None,
            "active_plans": None,
        }
    now_value = now_iso or _now()
    total_customers = int(con.execute("SELECT COUNT(*) FROM provider_customers WHERE tenant_id=?", (tenant_id,)).fetchone()[0])
    active_plans = int(con.execute("SELECT COUNT(*) FROM provider_retail_plans WHERE tenant_id=? AND status='ACTIVE'", (tenant_id,)).fetchone()[0])
    active_subscribers = int(con.execute(
        "SELECT COUNT(DISTINCT customer_id) FROM provider_customer_subscriptions WHERE tenant_id=? AND status='ACTIVE' AND (expires_at IS NULL OR expires_at>?)",
        (tenant_id, now_value),
    ).fetchone()[0])
    return {
        "status": "ready",
        "reason": None,
        "active_subscribers": active_subscribers,
        "total_customers": total_customers,
        "active_plans": active_plans,
    }


def list_subscribers(con: sqlite3.Connection, *, tenant_id: int, limit: int = 100) -> list[dict[str, Any]]:
    summary = subscriber_summary(con, tenant_id=tenant_id)
    if summary["status"] != "ready":
        return []
    rows = con.execute(
        "SELECT c.id AS customer_id,c.external_user_id,c.display_name,c.username,c.email,c.status AS customer_status,"
        "s.id AS subscription_id,s.status AS subscription_status,s.starts_at,s.expires_at,"
        "p.id AS plan_id,p.code AS plan_code,p.name AS plan_name,p.price_amount,p.price_currency "
        "FROM provider_customers c "
        "LEFT JOIN provider_customer_subscriptions s ON s.id=(SELECT s2.id FROM provider_customer_subscriptions s2 WHERE s2.tenant_id=c.tenant_id AND s2.customer_id=c.id ORDER BY s2.id DESC LIMIT 1) "
        "LEFT JOIN provider_retail_plans p ON p.id=s.plan_id AND p.tenant_id=c.tenant_id "
        "WHERE c.tenant_id=? ORDER BY c.id DESC LIMIT ?",
        (tenant_id, int(limit)),
    ).fetchall()
    return [dict(row) for row in rows]
