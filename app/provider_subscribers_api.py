from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from . import db
from .provider_panel_api import _require, _tenant_context
from .provider_permissions import ProviderPermission
from .provider_subscribers import (
    create_customer,
    create_retail_plan,
    create_subscription,
    list_subscribers,
    subscriber_summary,
)

router = APIRouter(prefix="/provider/api", tags=["Provider Subscribers"])


class CustomerCreateRequest(BaseModel):
    external_user_id: str | None = Field(default=None, max_length=120)
    display_name: str | None = Field(default=None, max_length=160)
    username: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=254)


class RetailPlanCreateRequest(BaseModel):
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=160)
    price_amount: float | None = Field(default=None, ge=0)
    price_currency: str | None = Field(default=None, max_length=12)
    duration_days: int | None = Field(default=None, gt=0)


class SubscriptionCreateRequest(BaseModel):
    customer_id: int = Field(gt=0)
    plan_id: int = Field(gt=0)
    starts_at: str = Field(min_length=1, max_length=64)
    expires_at: str | None = Field(default=None, max_length=64)


@router.get("/subscribers")
def subscribers(
    limit: int = Query(default=100, ge=1, le=500),
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
    x_tenant_id: int | None = Header(default=None, alias="X-Tenant-Id"),
) -> dict[str, Any]:
    ctx = _tenant_context(x_telegram_init_data, x_tenant_id)
    _require(ctx, ProviderPermission.VIEW)
    with db.conn() as con:
        summary = subscriber_summary(con, tenant_id=ctx.tenant_id)
        items = list_subscribers(con, tenant_id=ctx.tenant_id, limit=limit)
    return {"tenant_id": ctx.tenant_id, "summary": summary, "items": items, "count": len(items)}


@router.post("/customers", status_code=201)
def add_customer(
    request: CustomerCreateRequest,
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
    x_tenant_id: int | None = Header(default=None, alias="X-Tenant-Id"),
) -> dict[str, Any]:
    ctx = _tenant_context(x_telegram_init_data, x_tenant_id)
    _require(ctx, ProviderPermission.MANAGE_MEMBERS)
    try:
        with db.conn() as con:
            customer_id = create_customer(
                con,
                tenant_id=ctx.tenant_id,
                external_user_id=request.external_user_id,
                display_name=request.display_name,
                username=request.username,
                email=request.email,
            )
    except Exception as exc:
        if "UNIQUE constraint failed" in str(exc):
            raise HTTPException(status_code=409, detail="customer already exists") from exc
        raise
    return {"tenant_id": ctx.tenant_id, "customer_id": customer_id}


@router.post("/retail-plans", status_code=201)
def add_retail_plan(
    request: RetailPlanCreateRequest,
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
    x_tenant_id: int | None = Header(default=None, alias="X-Tenant-Id"),
) -> dict[str, Any]:
    ctx = _tenant_context(x_telegram_init_data, x_tenant_id)
    _require(ctx, ProviderPermission.MANAGE_MEMBERS)
    try:
        with db.conn() as con:
            plan_id = create_retail_plan(
                con,
                tenant_id=ctx.tenant_id,
                code=request.code,
                name=request.name,
                price_amount=request.price_amount,
                price_currency=request.price_currency,
                duration_days=request.duration_days,
            )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        if "UNIQUE constraint failed" in str(exc):
            raise HTTPException(status_code=409, detail="retail plan code already exists") from exc
        raise
    return {"tenant_id": ctx.tenant_id, "plan_id": plan_id}


@router.post("/subscriptions", status_code=201)
def add_subscription(
    request: SubscriptionCreateRequest,
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
    x_tenant_id: int | None = Header(default=None, alias="X-Tenant-Id"),
) -> dict[str, Any]:
    ctx = _tenant_context(x_telegram_init_data, x_tenant_id)
    _require(ctx, ProviderPermission.MANAGE_MEMBERS)
    try:
        with db.conn() as con:
            subscription_id = create_subscription(
                con,
                tenant_id=ctx.tenant_id,
                customer_id=request.customer_id,
                plan_id=request.plan_id,
                starts_at=request.starts_at,
                expires_at=request.expires_at,
            )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="customer or retail plan not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"tenant_id": ctx.tenant_id, "subscription_id": subscription_id}
