from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from . import db
from .provider_panel_api import _require, _tenant_context
from .provider_permissions import ProviderPermission
from .provider_reconciliation import list_reconciliation_queue, reconciliation_health, resolve_delivery

router = APIRouter(prefix="/provider/api", tags=["Provider Delivery Reconciliation"])


class DeliveryResolutionRequest(BaseModel):
    resolution: str = Field(min_length=1, max_length=40)
    note: str | None = Field(default=None, max_length=1000)
    telegram_message_id: int | None = Field(default=None, gt=0)
    payload: dict[str, Any] | None = None


@router.get("/deliveries/reconciliation/health")
def reconciliation_health_status(
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
    x_tenant_id: int | None = Header(default=None, alias="X-Tenant-Id"),
) -> dict[str, Any]:
    ctx = _tenant_context(x_telegram_init_data, x_tenant_id)
    _require(ctx, ProviderPermission.MANAGE_TELEGRAM)
    with db.conn() as con:
        health = reconciliation_health(con, tenant_id=ctx.tenant_id)
    return {"tenant_id": ctx.tenant_id, "recovery": health}


@router.get("/deliveries/reconciliation")
def reconciliation_queue(
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
    x_tenant_id: int | None = Header(default=None, alias="X-Tenant-Id"),
) -> dict[str, Any]:
    ctx = _tenant_context(x_telegram_init_data, x_tenant_id)
    _require(ctx, ProviderPermission.MANAGE_TELEGRAM)
    with db.conn() as con:
        items = list_reconciliation_queue(con, tenant_id=ctx.tenant_id)
    return {"tenant_id": ctx.tenant_id, "items": items, "count": len(items)}


@router.post("/deliveries/{delivery_id}/resolve")
def resolve_reconciliation(
    delivery_id: int,
    request: DeliveryResolutionRequest,
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
    x_tenant_id: int | None = Header(default=None, alias="X-Tenant-Id"),
) -> dict[str, Any]:
    ctx = _tenant_context(x_telegram_init_data, x_tenant_id)
    _require(ctx, ProviderPermission.MANAGE_TELEGRAM)
    try:
        with db.conn() as con:
            result = resolve_delivery(
                con,
                tenant_id=ctx.tenant_id,
                delivery_id=delivery_id,
                resolution=request.resolution,
                resolved_by_user_id=ctx.user_id,
                note=request.note,
                telegram_message_id=request.telegram_message_id,
                payload=request.payload,
            )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"tenant_id": ctx.tenant_id, "reconciliation": result}
