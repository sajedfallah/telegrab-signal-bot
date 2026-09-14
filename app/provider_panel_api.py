from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from . import db
from .provider_credentials import (
    SECRET_KIND_TELEGRAM_BOT_TOKEN,
    load_secret,
    probe_telegram_bot_token,
    store_secret,
)
from .provider_permissions import ProviderPermission, require_permission
from .provider_publish import publish_signal_text
from .signal_domain import get_signal as domain_get_signal, list_signals as domain_list_signals
from .telegram_tenant_domain import (
    create_connection as telegram_create_connection,
    create_destination as telegram_create_destination,
    get_connection_private,
    get_destination as telegram_get_destination,
    list_connections as telegram_list_connections,
    list_destinations as telegram_list_destinations,
    mark_connection_test,
)
from .telegram_webapp_auth import validate_init_data
from .tenancy import TenantContext, resolve_tenant_context

router = APIRouter(prefix="/provider/api", tags=["Provider Panel"])


class TelegramConnectionCreate(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    bot_token: str = Field(min_length=10, max_length=256)


class TelegramDestinationCreate(BaseModel):
    connection_id: int = Field(gt=0)
    destination_key: str = Field(min_length=1, max_length=80)
    chat_id: str = Field(min_length=1, max_length=128)
    kind: str = Field(default="CHANNEL", min_length=1, max_length=20)
    thread_id: int | None = Field(default=None, gt=0)
    display_name: str | None = Field(default=None, max_length=120)


class SignalPublishRequest(BaseModel):
    destination_key: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=4096)


def _columns(con, table: str) -> set[str]:
    return {str(row[1]) for row in con.execute(f"PRAGMA table_info({table})").fetchall()}


def _table_exists(con, table: str) -> bool:
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def _provider_bot_token() -> str:
    return os.getenv("PROVIDER_PANEL_BOT_TOKEN", "").strip() or os.getenv("BOT_TOKEN", "").strip()


def _authenticate_provider(raw: str) -> dict[str, Any]:
    return validate_init_data(raw, bot_token=_provider_bot_token())


def _tenant_context(x_telegram_init_data: str | None, x_tenant_id: int | None) -> TenantContext:
    user = _authenticate_provider(x_telegram_init_data or "")
    user_id = int(user["id"])
    if not x_tenant_id or int(x_tenant_id) <= 0:
        raise HTTPException(status_code=400, detail="X-Tenant-Id is required")
    try:
        with db.conn() as con:
            return resolve_tenant_context(con, user_id=user_id, tenant_id=int(x_tenant_id))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="tenant access denied") from exc


def _require(ctx: TenantContext, permission: ProviderPermission) -> None:
    try:
        require_permission(ctx, permission)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="tenant role is not authorized") from exc


def _tenant(ctx: TenantContext) -> dict[str, Any]:
    with db.conn() as con:
        row = con.execute(
            "SELECT id,slug,business_name,display_name,status,timezone,locale FROM tenants WHERE id=?", (ctx.tenant_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="tenant not found")
    return dict(row)


def _telegram_state(con, tenant_id: int) -> dict[str, Any]:
    connections = telegram_list_connections(con, tenant_id=tenant_id)
    destinations = telegram_list_destinations(con, tenant_id=tenant_id)
    active_connections = sum(1 for item in connections if item["status"] == "ACTIVE")
    active_destinations = sum(1 for item in destinations if item["status"] == "ACTIVE")
    if active_connections and active_destinations:
        status, reason = "ready", None
    elif connections:
        status, reason = "not_ready", "no active Telegram connection/destination pair"
    else:
        status, reason = "unconfigured", "tenant Telegram connection is not configured"
    return {
        "status": status,
        "reason": reason,
        "connection_count": len(connections),
        "active_connection_count": active_connections,
        "destination_count": len(destinations),
        "active_destination_count": active_destinations,
    }


def _recovery_state(con, tenant_id: int) -> dict[str, Any]:
    """Read recovery health without creating or mutating schema from a dashboard GET."""
    if not _table_exists(con, "provider_lifecycle_deliveries"):
        return {
            "status": "unavailable",
            "reason": "provider lifecycle delivery schema is not migrated",
            "unknown_delivery_count": 0,
            "claimed_delivery_count": 0,
            "open_reconciliation_count": 0,
            "requires_attention": False,
        }
    unknown_count = int(con.execute(
        "SELECT COUNT(*) FROM provider_lifecycle_deliveries WHERE tenant_id=? AND status='UNKNOWN'",
        (tenant_id,),
    ).fetchone()[0])
    claimed_count = int(con.execute(
        "SELECT COUNT(*) FROM provider_lifecycle_deliveries WHERE tenant_id=? AND status='CLAIMED'",
        (tenant_id,),
    ).fetchone()[0])
    open_count = 0
    if _table_exists(con, "provider_delivery_reconciliations"):
        open_count = int(con.execute(
            "SELECT COUNT(*) FROM provider_delivery_reconciliations WHERE tenant_id=? AND status='OPEN'",
            (tenant_id,),
        ).fetchone()[0])
    requires_attention = bool(unknown_count or claimed_count or open_count)
    return {
        "status": "attention" if requires_attention else "healthy",
        "reason": "delivery recovery requires operator review" if requires_attention else None,
        "unknown_delivery_count": unknown_count,
        "claimed_delivery_count": claimed_count,
        "open_reconciliation_count": open_count,
        "requires_attention": requires_attention,
    }


def _dashboard(ctx: TenantContext) -> dict[str, Any]:
    with db.conn() as con:
        signal_count = 0
        recent_signals: list[dict[str, Any]] = []
        win_rate: float | None = None
        distribution: list[dict[str, Any]] = []
        if _table_exists(con, "signals") and "tenant_id" in _columns(con, "signals"):
            signal_count = int(con.execute("SELECT COUNT(*) FROM signals WHERE tenant_id=?", (ctx.tenant_id,)).fetchone()[0])
            rows = con.execute(
                "SELECT id,code,market_type,symbol,direction,entry_price,stop_loss,tp1,status,result_value,result_unit,created_at,closed_at "
                "FROM signals WHERE tenant_id=? ORDER BY id DESC LIMIT 8", (ctx.tenant_id,)
            ).fetchall()
            recent_signals = [dict(row) for row in rows]
            closed = con.execute(
                "SELECT status,result_value,market_type FROM signals WHERE tenant_id=? AND status NOT IN ('ACTIVE','PENDING')",
                (ctx.tenant_id,),
            ).fetchall()
            if closed:
                wins = sum(
                    1
                    for row in closed
                    if str(row["status"] or "").upper().startswith("TP")
                    or (row["result_value"] is not None and float(row["result_value"]) > 0)
                )
                win_rate = round((wins / len(closed)) * 100, 1)
            groups = con.execute(
                "SELECT COALESCE(NULLIF(market_type,''),'Other') AS market_type,COUNT(*) AS count FROM signals "
                "WHERE tenant_id=? GROUP BY COALESCE(NULLIF(market_type,''),'Other') ORDER BY count DESC", (ctx.tenant_id,)
            ).fetchall()
            distribution = [{"label": str(row["market_type"]), "count": int(row["count"])} for row in groups]
        telegram_state = _telegram_state(con, ctx.tenant_id)
        recovery_state = _recovery_state(con, ctx.tenant_id)
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
                "telegram": telegram_state,
                "recovery": recovery_state,
                "mt5": {"status": "unavailable", "reason": "tenant TradingConnection domain pending"},
                "copy_trade": {"status": "unavailable", "reason": "tenant Copy Trade domain pending"},
                "subscription": {"status": "unavailable", "reason": "provider subscription domain pending"},
            },
            "availability": {
                "active_subscribers": False,
                "monthly_revenue": False,
                "revenue_series": False,
                "signals": True,
                "telegram": True,
                "recovery": recovery_state["status"] != "unavailable",
            },
        }


@router.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "service": "provider-panel-api", "version": "0.7"}


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
    return _dashboard(_tenant_context(x_telegram_init_data, x_tenant_id))


@router.get("/signals")
def signals(
    limit: int = Query(default=50, ge=1, le=200),
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
    x_tenant_id: int | None = Header(default=None, alias="X-Tenant-Id"),
) -> dict[str, Any]:
    ctx = _tenant_context(x_telegram_init_data, x_tenant_id)
    with db.conn() as con:
        rows = domain_list_signals(con, tenant_id=ctx.tenant_id, limit=limit)
    return {"tenant_id": ctx.tenant_id, "items": rows, "count": len(rows), "mode": "read_only"}


@router.get("/signals/{signal_id}")
def signal_detail(
    signal_id: int,
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
    x_tenant_id: int | None = Header(default=None, alias="X-Tenant-Id"),
) -> dict[str, Any]:
    ctx = _tenant_context(x_telegram_init_data, x_tenant_id)
    with db.conn() as con:
        item = domain_get_signal(con, tenant_id=ctx.tenant_id, signal_id=signal_id)
    if item is None:
        raise HTTPException(status_code=404, detail="signal not found")
    return {"tenant_id": ctx.tenant_id, "signal": item, "mode": "read_only"}


@router.post("/signals/{signal_id}/publish")
def publish_signal(
    signal_id: int,
    payload: SignalPublishRequest,
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
    x_tenant_id: int | None = Header(default=None, alias="X-Tenant-Id"),
) -> dict[str, Any]:
    ctx = _tenant_context(x_telegram_init_data, x_tenant_id)
    _require(ctx, ProviderPermission.PUBLISH_SIGNAL)
    try:
        with db.conn() as con:
            receipt = publish_signal_text(
                con,
                tenant_id=ctx.tenant_id,
                signal_id=signal_id,
                destination_key=payload.destination_key,
                text=payload.text,
            )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail="signal already published to destination") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        message = str(exc)
        if "credential" in message.lower() or "publish-ready" in message.lower():
            raise HTTPException(status_code=409, detail="Telegram connection is not publish-ready") from exc
        raise HTTPException(status_code=502, detail="Telegram publish failed") from exc
    return {"tenant_id": ctx.tenant_id, "publication": receipt}


@router.get("/telegram")
def telegram_routing(
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
    x_tenant_id: int | None = Header(default=None, alias="X-Tenant-Id"),
) -> dict[str, Any]:
    ctx = _tenant_context(x_telegram_init_data, x_tenant_id)
    with db.conn() as con:
        connections = telegram_list_connections(con, tenant_id=ctx.tenant_id)
        destinations = telegram_list_destinations(con, tenant_id=ctx.tenant_id)
        state = _telegram_state(con, ctx.tenant_id)
    return {
        "tenant_id": ctx.tenant_id,
        "connections": connections,
        "destinations": destinations,
        "health": state,
        "mutations_enabled": True,
        "publish_enabled": state["status"] == "ready",
    }


@router.post("/telegram/connections", status_code=201)
def create_telegram_connection(
    payload: TelegramConnectionCreate,
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
    x_tenant_id: int | None = Header(default=None, alias="X-Tenant-Id"),
) -> dict[str, Any]:
    ctx = _tenant_context(x_telegram_init_data, x_tenant_id)
    _require(ctx, ProviderPermission.MANAGE_TELEGRAM)
    try:
        with db.conn() as con:
            secret_ref = store_secret(
                con,
                tenant_id=ctx.tenant_id,
                kind=SECRET_KIND_TELEGRAM_BOT_TOKEN,
                plaintext=payload.bot_token,
            )
            connection_id = telegram_create_connection(
                con,
                tenant_id=ctx.tenant_id,
                label=payload.label,
                secret_ref=secret_ref,
                status="PENDING",
            )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Provider credential encryption is not configured") from exc
    except Exception as exc:
        if "UNIQUE constraint failed" in str(exc):
            raise HTTPException(status_code=409, detail="Telegram connection label already exists") from exc
        raise
    return {
        "tenant_id": ctx.tenant_id,
        "connection_id": connection_id,
        "status": "PENDING",
        "credential_stored": True,
    }


@router.post("/telegram/connections/{connection_id}/test", name="probe_telegram_connection")
def probe_telegram_connection(
    connection_id: int,
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
    x_tenant_id: int | None = Header(default=None, alias="X-Tenant-Id"),
) -> dict[str, Any]:
    ctx = _tenant_context(x_telegram_init_data, x_tenant_id)
    _require(ctx, ProviderPermission.MANAGE_TELEGRAM)
    try:
        with db.conn() as con:
            connection = get_connection_private(con, tenant_id=ctx.tenant_id, connection_id=connection_id)
            secret_ref = connection.get("secret_ref")
            if not secret_ref:
                raise HTTPException(status_code=409, detail="Telegram credential is not configured")
            token = load_secret(con, tenant_id=ctx.tenant_id, secret_ref=str(secret_ref))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Telegram connection not found") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Provider credential encryption is not configured") from exc

    result = probe_telegram_bot_token(token)
    with db.conn() as con:
        mark_connection_test(
            con,
            tenant_id=ctx.tenant_id,
            connection_id=connection_id,
            ok=bool(result.get("ok")),
            bot_username=result.get("username") if result.get("ok") else None,
            error=result.get("error") if not result.get("ok") else None,
        )
    return {"tenant_id": ctx.tenant_id, "connection_id": connection_id, **result}


@router.post("/telegram/destinations", status_code=201)
def create_telegram_destination(
    payload: TelegramDestinationCreate,
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
    x_tenant_id: int | None = Header(default=None, alias="X-Tenant-Id"),
) -> dict[str, Any]:
    ctx = _tenant_context(x_telegram_init_data, x_tenant_id)
    _require(ctx, ProviderPermission.MANAGE_TELEGRAM)
    try:
        with db.conn() as con:
            destination_id = telegram_create_destination(
                con,
                tenant_id=ctx.tenant_id,
                connection_id=payload.connection_id,
                destination_key=payload.destination_key,
                chat_id=payload.chat_id,
                kind=payload.kind,
                thread_id=payload.thread_id,
                display_name=payload.display_name,
            )
            destination = telegram_get_destination(con, tenant_id=ctx.tenant_id, destination_id=destination_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Telegram connection not found") from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=409,
            detail="Telegram connection must be tested successfully before adding destinations",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        if "UNIQUE constraint failed" in str(exc):
            raise HTTPException(status_code=409, detail="Telegram destination key already exists") from exc
        raise
    return {"tenant_id": ctx.tenant_id, "destination": destination, "publish_enabled": True}
