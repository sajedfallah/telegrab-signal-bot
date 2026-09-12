from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query

from .miniapp_api import _auth_user, _entitlements
from .miniapp_home import PERFORMANCE_PERIODS, _safe_performance
from .miniapp_signals import PUBLIC_CLOSED_VIP_DETAILS
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


def _period_key(value: str) -> str:
    key = str(value or "30").lower()
    if key not in PERFORMANCE_PERIODS:
        raise HTTPException(status_code=400, detail="unsupported performance period")
    return key


def _r_overview(data: dict[str, Any]) -> dict[str, Any]:
    sample = int(data.get("r_sample_size") or 0)
    if sample <= 0:
        return {
            "sample_size": 0,
            "net_r": None,
            "average_r": None,
            "profit_factor": None,
            "current_losing_streak": None,
            "maximum_losing_streak": None,
            "max_drawdown_r": None,
            "equity_curve_r": [],
            "status": "INSUFFICIENT_DATA",
        }
    return {
        "sample_size": sample,
        "net_r": data.get("net_r"),
        "average_r": data.get("average_realized_r"),
        "profit_factor": data.get("profit_factor_r"),
        "current_losing_streak": data.get("current_losing_streak"),
        "maximum_losing_streak": data.get("maximum_losing_streak"),
        "max_drawdown_r": data.get("max_drawdown_r"),
        "equity_curve_r": list(data.get("equity_curve_r") or []),
        "status": "OK",
    }


def _visible_trade(item: dict[str, Any], *, has_vip: bool) -> dict[str, Any]:
    locked = bool(item.get("access") == "VIP" and not has_vip and not PUBLIC_CLOSED_VIP_DETAILS)
    if not locked:
        return {**item, "locked": False}
    return {
        "id": item["id"],
        "code": item.get("code"),
        "symbol": item.get("symbol"),
        "access": "VIP",
        "status": item.get("status"),
        "close_time": item.get("close_time"),
        "result_value": item.get("result_value"),
        "result_unit": item.get("result_unit"),
        "realized_r": item.get("realized_r"),
        "result_source": item.get("result_source"),
        "locked": True,
    }


@router.get("/performance/details")
def performance_details(
    period: str = Query(default="30"),
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    _auth_user(x_telegram_init_data)
    key = _period_key(period)
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


@router.get("/performance/overview")
def performance_overview(
    period: str = Query(default="30"),
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    _auth_user(x_telegram_init_data)
    key = _period_key(period)
    data = analytics_service.overview(key)
    p = data["period"]
    return {
        "period": {"key": p.key, "label_fa": p.label_fa, "label_en": p.label_en},
        "summary": _safe_summary(data),
        "active": int(data.get("active") or 0),
        "risk": _r_overview(data),
        "methodology": analytics_service.methodology(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/performance/trades")
def performance_trades(
    period: str = Query(default="30"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    user = _auth_user(x_telegram_init_data)
    uid = int(user["id"])
    has_vip = bool(_entitlements(uid).get("vip"))
    key = _period_key(period)
    data = analytics_service.trade_history(key, limit=limit, offset=offset)
    return {
        "period": key,
        "total": int(data.get("total") or 0),
        "items": [_visible_trade(item, has_vip=has_vip) for item in data.get("items") or []],
    }


@router.get("/performance/trades/{trade_id}")
def performance_trade_detail(
    trade_id: int,
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    user = _auth_user(x_telegram_init_data)
    uid = int(user["id"])
    item = analytics_service.trade_detail(trade_id)
    if not item:
        raise HTTPException(status_code=404, detail="closed performance trade not found")
    has_vip = bool(_entitlements(uid).get("vip"))
    if item.get("access") == "VIP" and not has_vip and not PUBLIC_CLOSED_VIP_DETAILS:
        raise HTTPException(status_code=403, detail="VIP access is required for premium trade details")
    return {"trade": item, "methodology": analytics_service.methodology()}


@router.get("/performance/methodology")
def performance_methodology(
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    _auth_user(x_telegram_init_data)
    return {
        **analytics_service.methodology(),
        "last_sync_time": datetime.now(timezone.utc).isoformat(),
    }
