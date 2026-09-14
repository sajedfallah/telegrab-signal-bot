from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any


def _table_exists(con: sqlite3.Connection, table: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _default_period(now_iso: str | None = None, days: int = 30) -> tuple[str, str]:
    now = datetime.fromisoformat(now_iso) if now_iso else datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    start = now - timedelta(days=max(1, int(days)))
    return start.isoformat(), now.isoformat()


def _period(start: str | None, end: str | None, *, now_iso: str | None = None, days: int = 30) -> tuple[str, str]:
    if bool(start) ^ bool(end):
        raise ValueError("start and end must be supplied together")
    if start and end:
        if start >= end:
            raise ValueError("start must be before end")
        return start, end
    return _default_period(now_iso=now_iso, days=days)


def provider_report(
    con: sqlite3.Connection,
    *,
    tenant_id: int,
    start: str | None = None,
    end: str | None = None,
    days: int = 30,
    payment_limit: int = 100,
    now_iso: str | None = None,
) -> dict[str, Any]:
    period_start, period_end = _period(start, end, now_iso=now_iso, days=days)
    if not _table_exists(con, "provider_payment_ledger"):
        return {
            "status": "unavailable",
            "reason": "provider revenue domain not migrated",
            "period": {"start": period_start, "end": period_end},
            "currency": None,
            "total_revenue": None,
            "revenue_by_plan": [],
            "payments": [],
            "signal_metrics": {"total_signals": None, "win_rate": None, "avg_rr": None},
        }

    currencies = [
        str(row[0])
        for row in con.execute(
            "SELECT DISTINCT currency FROM provider_payment_ledger "
            "WHERE tenant_id=? AND status='SETTLED' AND paid_at>=? AND paid_at<=? ORDER BY currency",
            (tenant_id, period_start, period_end),
        ).fetchall()
    ]
    mixed_currency = len(currencies) > 1
    currency = currencies[0] if len(currencies) == 1 else None
    total_revenue = None if mixed_currency else float(
        con.execute(
            "SELECT COALESCE(SUM(amount),0) FROM provider_payment_ledger "
            "WHERE tenant_id=? AND status='SETTLED' AND paid_at>=? AND paid_at<=?",
            (tenant_id, period_start, period_end),
        ).fetchone()[0]
    )

    revenue_by_plan: list[dict[str, Any]] = []
    if not mixed_currency and _table_exists(con, "provider_customer_subscriptions") and _table_exists(con, "provider_retail_plans"):
        rows = con.execute(
            "SELECT COALESCE(p.code,'UNASSIGNED') AS plan_code,COALESCE(p.name,'Unassigned') AS plan_name,"
            "COALESCE(SUM(l.amount),0) AS amount,COUNT(l.id) AS payment_count "
            "FROM provider_payment_ledger l "
            "LEFT JOIN provider_customer_subscriptions s ON s.id=l.subscription_id AND s.tenant_id=l.tenant_id "
            "LEFT JOIN provider_retail_plans p ON p.id=s.plan_id AND p.tenant_id=l.tenant_id "
            "WHERE l.tenant_id=? AND l.status='SETTLED' AND l.paid_at>=? AND l.paid_at<=? "
            "GROUP BY COALESCE(p.code,'UNASSIGNED'),COALESCE(p.name,'Unassigned') ORDER BY amount DESC",
            (tenant_id, period_start, period_end),
        ).fetchall()
        revenue_by_plan = [
            {
                "plan_code": str(row["plan_code"]),
                "plan_name": str(row["plan_name"]),
                "amount": float(row["amount"]),
                "payment_count": int(row["payment_count"]),
            }
            for row in rows
        ]

    payments = [
        dict(row)
        for row in con.execute(
            "SELECT id,customer_id,subscription_id,kind,amount,currency,status,reference,paid_at "
            "FROM provider_payment_ledger WHERE tenant_id=? AND paid_at>=? AND paid_at<=? "
            "ORDER BY paid_at DESC,id DESC LIMIT ?",
            (tenant_id, period_start, period_end, max(1, int(payment_limit))),
        ).fetchall()
    ]

    signal_metrics = {"total_signals": None, "win_rate": None, "avg_rr": None}
    if _table_exists(con, "signals"):
        cols = {str(row[1]) for row in con.execute("PRAGMA table_info(signals)").fetchall()}
        required = {"tenant_id", "created_at", "status", "result_value", "entry_price", "stop_loss", "tp1"}
        if required.issubset(cols):
            signal_rows = con.execute(
                "SELECT status,result_value,entry_price,stop_loss,tp1 FROM signals "
                "WHERE tenant_id=? AND created_at>=? AND created_at<=?",
                (tenant_id, period_start, period_end),
            ).fetchall()
            total_signals = len(signal_rows)
            closed = [r for r in signal_rows if str(r["status"] or "").upper() not in {"ACTIVE", "PENDING"}]
            win_rate: float | None = None
            if closed:
                wins = sum(
                    1
                    for row in closed
                    if str(row["status"] or "").upper().startswith("TP")
                    or (row["result_value"] is not None and float(row["result_value"]) > 0)
                )
                win_rate = round((wins / len(closed)) * 100, 1)
            rr_values: list[float] = []
            for row in signal_rows:
                if row["entry_price"] is None or row["stop_loss"] is None or row["tp1"] is None:
                    continue
                risk = abs(float(row["entry_price"]) - float(row["stop_loss"]))
                reward = abs(float(row["tp1"]) - float(row["entry_price"]))
                if risk > 0:
                    rr_values.append(reward / risk)
            signal_metrics = {
                "total_signals": total_signals,
                "win_rate": win_rate,
                "avg_rr": round(sum(rr_values) / len(rr_values), 2) if rr_values else None,
            }

    return {
        "status": "mixed_currency" if mixed_currency else "ready",
        "reason": "multiple settled payment currencies require explicit reporting currency" if mixed_currency else None,
        "period": {"start": period_start, "end": period_end},
        "currency": currency,
        "total_revenue": total_revenue,
        "revenue_by_plan": revenue_by_plan,
        "payments": payments,
        "signal_metrics": signal_metrics,
    }
