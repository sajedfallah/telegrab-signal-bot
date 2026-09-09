from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from .miniapp_api import _auth_user
from .services.pricing_service import PricingError, quote_purchase

router = APIRouter(prefix="/miniapp/api", tags=["NEXUS Mini App Checkout"])


class QuoteRequest(BaseModel):
    plan_code: str = Field(min_length=2, max_length=32)


def _money(value: Any) -> str:
    return format(Decimal(str(value)).quantize(Decimal("0.01")), "f")


def serialize_quote(quote: dict[str, Any]) -> dict[str, Any]:
    plan = dict(quote["plan"])
    return {
        "plan": {
            "code": str(plan.get("code") or ""),
            "title_fa": str(plan.get("fa") or plan.get("code") or ""),
            "title_en": str(plan.get("en") or plan.get("code") or ""),
            "days": int(plan.get("days") or plan.get("duration_days") or 0),
            "vip_access": bool(plan.get("vip_access")),
            "autotrade_access": bool(plan.get("autotrade_access")),
        },
        "mode": str(quote["mode"]),
        "base_usdt": _money(quote["base_usdt"]),
        "setup_fee_usdt": _money(quote["setup_fee_usdt"]),
        "upgrade_credit_usdt": _money(quote["upgrade_credit_usdt"]),
        "discount_percent": _money(quote["discount_percent"]),
        "total_usdt": _money(quote["total_usdt"]),
        "duration_days": int(quote["duration_days"]),
    }


@router.post("/quote")
def quote(
    payload: QuoteRequest,
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    uid = int(_auth_user(x_telegram_init_data)["id"])
    try:
        return serialize_quote(quote_purchase(uid, payload.plan_code.upper()))
    except PricingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
