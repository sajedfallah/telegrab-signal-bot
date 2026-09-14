from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Header, HTTPException

from . import db
from .telegram_webapp_auth import validate_init_data
from .tenancy import TenantContext, resolve_tenant_context


router = APIRouter(prefix="/provider/api", tags=["Provider Panel"])


def _columns(con, table: str) -> set[str]:
    return {str(row[1]) for row in con.execute(f"PRAGMA table_info({table})").fetchall()}


def _table_exists(con, table: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _provider_bot_token() -> str:
    # V1 can reuse BOT_TOKEN, while a dedicated provider bot can be introduced
    # without coupling this module back to the global NEXUS Settings object.
    return os.getenv("PROVIDER_PANEL_BOT_TOKEN", "").strip() or os.getenv("BOT_TOKEN", "").strip()


def _authenticate_provider(raw: str) -> dict[str, Any]:
    return validate_init_data(raw, bot_token=_provider_bot_token())


def _tenant_context(
    x_telegram_init_data: str | None,
    x_tenant_id: int | None,
) -> TenantContext:
    user = _authenticate_provider(x_telegram_init_data or "")
    user_id = int(user["id"])
    if not x_tenant_id or int(x_tenant_id) <= 0:
        raise HTTPException(status_code=400, detail="X-Tenant-Id is required")
    try:
        with db.conn() as con:
            return resolve_tenant_context(con, user_id=user_id, tenant_id=int(x_tenant_id))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="tenant access denied") from exc


def _tenant(ctx: TenantContext) -> dict[str, Any]:
    with db.conn() as con:
        row = con.execute(
            "SELECT id,slug,business_name,display_name,status,timezone,locale "
            "FROM tenants WHERE id=?",
            (ctx.tenant_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="tenant not found")
    return dict(row)


def _dashboard(ctx: TenantContext) -> dict[str, Any]:
    """Return only tenant-scoped values backed by current persisted data.

    Metrics whose SaaS domain does not exist yet are explicit null/unavailable values;
    fixture values are never promoted to production truth.
    """
    with db.conn() as con:
        signal_count = 0
        recent_signals: list[dict[str, Any]] = []
        win_rate: float | None = None
        distribution: list[dict[str, Any]] = []

        if _table_exists(con, "signals") and "tenant_id" in _columns(con, "signals"):
            signal_count = int(
                con.execute("SELECT COUNT(*) FROM signals WHERE tenant_id=?", (ctx.tenant_id,)).fetchone()[0]
            )
            rows = con.execute(
                "SELECT id,code,market_type,symbol,direction,entry_price,stop_loss,tp1,status,"
                "result_value,result_unit,created_at,closed_at "
                "FROM signals WHERE tenant_id=? ORDER BY id DESC LIMIT 8",
                (ctx.tenant_id,),
            ).fetchall()
            recent_signals = [dict(row) for row in rows]

            closed = con.execute(
                "SELECT status,result_value,market_type FROM signals WHERE tenant_id=? "
                "AND status NOT IN ('ACTIVE','PENDING')",
                (ctx.tenant_id,),
            ).fetchall()
            if closed:
                wins = sum(
                    1 for row in closed
                    if str(row["status"] or "").upper().startswith("TP")
                    or (row["result_value"] is not None and float(row["result_value"]) > 0)
                )
                win_rate = round((wins / len(closed)) * 100, 1)

            groups = con.execute(
                "SELECT COALESCE(NULLIF(market_type,''),'Other') AS market_type,COUNT(*) AS count "
                "FROM signals WHERE tenant_id=? GROUP BY COALESCE(NULLIF(market_type,''),'Other') "
                "ORDER BY count DESC",
                (ctx.tenant_id,),
            ).fetchall()
            distribution = [{"label": str(row["market_type"]), "count": int(row["count"])} for row in groups]

        return {
            "source": "live_database",
            "tenant_id": ctx.tenant_id,
            "kpis": {
                "active_subscribers": None,
                "monthly_revenue": None,
                "total_signals": signal_count,
                "win_rate": win_rate,
            },
            "revenue_series": [],
            "signal_distribution": distribution,
            "recent_signals": recent_signals,
            "health": {
                "telegram": {"status": "unavailable", "reason": "tenant TelegramConnection domain pending"},
                "mt5": {"status": "unavailable", "reason": "tenant TradingConnection domain pending"},
                "copy_trade": {"status": "unavailable", "reason": "tenant Copy Trade domain pending"},
                "subscription": {"status": "unavailable", "reason": "provider subscription domain pending"},
            },
            "availability": {
                "active_subscribers": False,
                "monthly_revenue": False,
                "revenue_series": False,
                "signals": True,
            },
        }


@router.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "service": "provider-panel-api", "version": "0.1"}


@router.get("/bootstrap")
def bootstrap(
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
    x_tenant_id: int | None = Header(default=None, alias="X-Tenant-Id"),
) -> dict[str, Any]:
    ctx = _tenant_context(x_telegram_init_data, x_tenant_id)
    return {
        "tenant": _tenant(ctx),
        "membership": {"user_id": ctx.user_id, "role": ctx.role.value},
        "dashboard": _dashboard(ctx),
    }


@router.get("/dashboard")
def dashboard(
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
    x_tenant_id: int | None = Header(default=None, alias="X-Tenant-Id"),
) -> dict[str, Any]:
    ctx = _tenant_context(x_telegram_init_data, x_tenant_id)
    return _dashboard(ctx)
