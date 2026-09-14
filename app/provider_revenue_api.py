from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from . import db
from .provider_panel_api import _require, _tenant_context
from .provider_permissions import ProviderPermission
from .provider_revenue import list_payments, record_payment, revenue_summary

router = APIRouter(prefix="/provider/api", tags=["Provider Revenue"])


class PaymentCreateRequest(BaseModel):
    amount: float = Field(ge=0)
    currency: str = Field(min_length=1, max_length=12)
    paid_at: str = Field(min_length=1, max_length=64)
    customer_id: int | None = Field(default=None, gt=0)
    subscription_id: int | None = Field(default=None, gt=0)
    kind: str = Field(default="SUBSCRIPTION", min_length=1, max_length=32)
    status: str = Field(default="SETTLED", min_length=1, max_length=32)
    reference: str | None = Field(default=None, max_length=160)


@router.get("/revenue")
def revenue(
    months: int = Query(default=12, ge=1, le=36),
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
    x_tenant_id: int | None = Header(default=None, alias="X-Tenant-Id"),
) -> dict[str, Any]:
    ctx = _tenant_context(x_telegram_init_data, x_tenant_id)
    _require(ctx, ProviderPermission.VIEW)
    with db.conn() as con:
        summary = revenue_summary(con, tenant_id=ctx.tenant_id, months=months)
        items = list_payments(con, tenant_id=ctx.tenant_id, limit=100)
    return {"tenant_id": ctx.tenant_id, "summary": summary, "items": items, "count": len(items)}


@router.post("/revenue/payments", status_code=201)
def add_payment(
    request: PaymentCreateRequest,
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
    x_tenant_id: int | None = Header(default=None, alias="X-Tenant-Id"),
) -> dict[str, Any]:
    ctx = _tenant_context(x_telegram_init_data, x_tenant_id)
    _require(ctx, ProviderPermission.MANAGE_BILLING)
    try:
        with db.conn() as con:
            payment_id = record_payment(
                con,
                tenant_id=ctx.tenant_id,
                amount=request.amount,
                currency=request.currency,
                paid_at=request.paid_at,
                customer_id=request.customer_id,
                subscription_id=request.subscription_id,
                kind=request.kind,
                status=request.status,
                reference=request.reference,
            )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="customer or subscription not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        if "UNIQUE constraint failed" in str(exc):
            raise HTTPException(status_code=409, detail="payment reference already exists") from exc
        raise
    return {"tenant_id": ctx.tenant_id, "payment_id": payment_id}
