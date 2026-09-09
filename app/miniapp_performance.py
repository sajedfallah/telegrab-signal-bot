from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query

from .miniapp_api import _auth_user
from .miniapp_home import PERFORMANCE_PERIODS, _safe_performance
from .services import analytics_service

router = APIRouter(prefix="/miniapp/api", tags=["NEXUS Mini App Performance"])


def _safe_summary(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "total": int(data.get("total") or 0),
        "wins": int(data.get("wins") or 0),
        "losses": int(data.get("losses") or 0),
        "be": int(data.get("be") or 0),
        "win_rate": float(data.get("win_rate") or 0),
    }


@router.get("/performance/details")
def performance_details(
    period: str = Query(default="30"),
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    _auth_user(x_telegram_init_data)
    key = str(period or "30").lower()
    if key not in PERFORMANCE_PERIODS:
        raise HTTPException(status_code=400, detail="unsupported performance period")
    summary = _safe_performance(key)
    symbol_rows = analytics_service.symbols(key, limit=12)
    channel_rows = analytics_service.channels(key)
    return {
        "summary": summary,
        "symbols": [
            {"symbol": str(item.get("symbol") or "—"), **_safe_summary(item)}
            for item in symbol_rows
        ],
        "channels": {name: _safe_summary(values) for name, values in channel_rows.items()},
        "methodology": {
            "scope": "published_nexus_signals",
            "account_return": False,
            "losses_are_retained": True,
            "message_fa": "Track Record بر پایه سیگنال‌های CLOSED ثبت‌شده NEXUS است؛ بازده حساب معاملاتی کاربر نیست.",
        },
    }
