from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from . import db
from .provider_branding import get_branding, save_branding
from .provider_panel_api import _require, _tenant_context
from .provider_permissions import ProviderPermission

router = APIRouter(prefix="/provider/api", tags=["Provider Branding"])


class BrandingUpdateRequest(BaseModel):
    brand_name: str | None = Field(default=None, max_length=160)
    tagline: str | None = Field(default=None, max_length=240)
    primary_color: str | None = Field(default=None, max_length=7)
    secondary_color: str | None = Field(default=None, max_length=7)
    accent_color: str | None = Field(default=None, max_length=7)
    background_color: str | None = Field(default=None, max_length=7)
    logo_url: str | None = Field(default=None, max_length=1000)
    favicon_url: str | None = Field(default=None, max_length=1000)


@router.get("/branding")
def branding(
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
    x_tenant_id: int | None = Header(default=None, alias="X-Tenant-Id"),
) -> dict[str, Any]:
    ctx = _tenant_context(x_telegram_init_data, x_tenant_id)
    _require(ctx, ProviderPermission.VIEW)
    with db.conn() as con:
        data = get_branding(con, tenant_id=ctx.tenant_id)
    return {"tenant_id": ctx.tenant_id, "branding": data}


@router.put("/branding")
def update_branding(
    request: BrandingUpdateRequest,
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
    x_tenant_id: int | None = Header(default=None, alias="X-Tenant-Id"),
) -> dict[str, Any]:
    ctx = _tenant_context(x_telegram_init_data, x_tenant_id)
    _require(ctx, ProviderPermission.MANAGE_BRANDING)
    try:
        with db.conn() as con:
            data = save_branding(
                con,
                tenant_id=ctx.tenant_id,
                updated_by_user_id=ctx.user_id,
                brand_name=request.brand_name,
                tagline=request.tagline,
                primary_color=request.primary_color,
                secondary_color=request.secondary_color,
                accent_color=request.accent_color,
                background_color=request.background_color,
                logo_url=request.logo_url,
                favicon_url=request.favicon_url,
            )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="tenant not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"tenant_id": ctx.tenant_id, "branding": data}
