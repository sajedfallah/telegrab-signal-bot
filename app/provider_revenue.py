from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any


PAYMENT_STATUSES = {"PENDING", "SETTLED", "FAILED", "REFUNDED", "VOID"}
REVENUE_KINDS = {"SUBSCRIPTION", "COPY_TRADE", "ADJUSTMENT", "OTHER"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_revenue_schema(con: sqlite3.Connection) -> None:
    statements = (
        """CREATE TABLE IF NOT EXISTS provider_payment_ledger(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            customer_id INTEGER,
            subscription_id INTEGER,
            kind TEXT NOT NULL DEFAULT 'SUBSCRIPTION'
                CHECK(kind IN ('SUBSCRIPTION','COPY_TRADE','ADJUSTMENT','OTHER')),
            amount REAL NOT NULL CHECK(amount >= 0),
            currency TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'SETTLED'
                CHECK(status IN ('PENDING','SETTLED','FAILED','REFUNDED','VOID')),
            reference TEXT,
            paid_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(tenant_id,reference),
            FOREIGN KEY(tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
            FOREIGN KEY(customer_id) REFERENCES provider_customers(id) ON DELETE SET NULL,
            FOREIGN KEY(subscription_id) REFERENCES provider_customer_subscriptions(id) ON DELETE SET NULL
        )""",
        "CREATE INDEX IF NOT EXISTS idx_provider_payment_ledger_tenant_paid ON provider_payment_ledger(tenant_id,status,paid_at,id)",
        "CREATE INDEX IF NOT EXISTS idx_provider_payment_ledger_customer ON provider_payment_ledger(tenant_id,customer_id,id)",
    )
    for statement in statements:
        con.execute(statement)


def _require_owned_optional(
    con: sqlite3.Connection,
    *,
    table: str,
    row_id: int | None,
    tenant_id: int,
) -> None:
    if row_id is None:
        return
    row = con.execute(f"SELECT 1 FROM {table} WHERE id=? AND tenant_id=?", (row_id, tenant_id)).fetchone()
    if row is None:
        raise LookupError(f"{table} resource not found")


def record_payment(
    con: sqlite3.Connection,
    *,
    tenant_id: int,
    amount: float,
    currency: str,
    paid_at: str,
    customer_id: int | None = None,
    subscription_id: int | None = None,
    kind: str = "SUBSCRIPTION",
    status: str = "SETTLED",
    reference: str | None = None,
) -> int:
    init_revenue_schema(con)
    if amount < 0:
        raise ValueError("amount must be non-negative")
    normalized_currency = currency.strip().upper()
    if not normalized_currency or len(normalized_currency) > 12:
        raise ValueError("currency is required")
    normalized_kind = kind.strip().upper()
    normalized_status = status.strip().upper()
    if normalized_kind not in REVENUE_KINDS:
        raise ValueError("invalid revenue kind")
    if normalized_status not in PAYMENT_STATUSES:
        raise ValueError("invalid payment status")
    if not paid_at.strip():
        raise ValueError("paid_at is required")
    _require_owned_optional(con, table="provider_customers", row_id=customer_id, tenant_id=tenant_id)
    _require_owned_optional(
        con,
        table="provider_customer_subscriptions",
        row_id=subscription_id,
        tenant_id=tenant_id,
    )
    now = _now()
    cur = con.execute(
        "INSERT INTO provider_payment_ledger(tenant_id,customer_id,subscription_id,kind,amount,currency,status,reference,paid_at,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (
            tenant_id,
            customer_id,
            subscription_id,
            normalized_kind,
            float(amount),
            normalized_currency,
            normalized_status,
            (reference or "").strip() or None,
            paid_at.strip(),
            now,
            now,
        ),
    )
    return int(cur.lastrowid)


def revenue_summary(
    con: sqlite3.Connection,
    *,
    tenant_id: int,
    now_iso: str | None = None,
    months: int = 12,
) -> dict[str, Any]:
    exists = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='provider_payment_ledger'"
    ).fetchone()
    if exists is None:
        return {
            "status": "unavailable",
            "reason": "provider revenue domain not migrated",
            "currency": None,
            "monthly_revenue": None,
            "series": [],
        }

    now_value = now_iso or _now()
    month_key = now_value[:7]
    currencies = [
        str(row[0])
        for row in con.execute(
            "SELECT DISTINCT currency FROM provider_payment_ledger WHERE tenant_id=? AND status='SETTLED' ORDER BY currency",
            (tenant_id,),
        ).fetchall()
    ]
    if len(currencies) > 1:
        return {
            "status": "mixed_currency",
            "reason": "multiple settled payment currencies require explicit reporting currency",
            "currency": None,
            "monthly_revenue": None,
            "series": [],
        }
    currency = currencies[0] if currencies else None
    monthly_revenue = float(
        con.execute(
            "SELECT COALESCE(SUM(amount),0) FROM provider_payment_ledger WHERE tenant_id=? AND status='SETTLED' AND substr(paid_at,1,7)=?",
            (tenant_id, month_key),
        ).fetchone()[0]
    )

    rows = con.execute(
        "SELECT substr(paid_at,1,7) AS month,COALESCE(SUM(amount),0) AS amount "
        "FROM provider_payment_ledger WHERE tenant_id=? AND status='SETTLED' "
        "GROUP BY substr(paid_at,1,7) ORDER BY month DESC LIMIT ?",
        (tenant_id, max(1, int(months))),
    ).fetchall()
    series = [
        {"month": str(row["month"]), "amount": float(row["amount"])}
        for row in reversed(rows)
    ]
    return {
        "status": "ready",
        "reason": None,
        "currency": currency,
        "monthly_revenue": monthly_revenue,
        "series": series,
    }


def list_payments(con: sqlite3.Connection, *, tenant_id: int, limit: int = 100) -> list[dict[str, Any]]:
    summary = revenue_summary(con, tenant_id=tenant_id)
    if summary["status"] == "unavailable":
        return []
    rows = con.execute(
        "SELECT id,customer_id,subscription_id,kind,amount,currency,status,reference,paid_at,created_at "
        "FROM provider_payment_ledger WHERE tenant_id=? ORDER BY paid_at DESC,id DESC LIMIT ?",
        (tenant_id, int(limit)),
    ).fetchall()
    return [dict(row) for row in rows]
