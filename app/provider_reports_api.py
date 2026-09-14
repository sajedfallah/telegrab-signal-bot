from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query

from . import db
from .provider_panel_api import _require, _tenant_context
from .provider_permissions import ProviderPermission
from .provider_reports import provider_report

router = APIRouter(prefix="/provider/api", tags=["Provider Reports"])


@router.get("/reports")
def reports(
    days: int = Query(default=30, ge=1, le=366),
    start: str | None = Query(default=None, max_length=64),
    end: str | None = Query(default=None, max_length=64),
    payment_limit: int = Query(default=100, ge=1, le=500),
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
    x_tenant_id: int | None = Header(default=None, alias="X-Tenant-Id"),
) -> dict[str, Any]:
    ctx = _tenant_context(x_telegram_init_data, x_tenant_id)
    _require(ctx, ProviderPermission.VIEW)
    try:
        with db.conn() as con:
            report = provider_report(
                con,
                tenant_id=ctx.tenant_id,
                start=start,
                end=end,
                days=days,
                payment_limit=payment_limit,
            )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"tenant_id": ctx.tenant_id, "report": report}
