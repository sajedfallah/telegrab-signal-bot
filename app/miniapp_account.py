from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Header

from . import db
from .config import settings
from .miniapp_api import _auth_user, _autotrade, _entitlements
from .miniapp_experience import EXPIRING_DAYS, _parse_dt
from .miniapp_home import _autotrade_health

router = APIRouter(prefix="/miniapp/api", tags=["NEXUS Mini App Account"])


def _service_status(*, active: bool, expires_at: Any, existed_before: bool, previous_expiry: Any) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    expiry = _parse_dt(expires_at) if active else _parse_dt(previous_expiry)
    if active:
        remaining = max(0, math.ceil((expiry - now).total_seconds() / 86400)) if expiry else None
        state = "EXPIRING" if remaining is not None and remaining <= EXPIRING_DAYS else "ACTIVE"
    elif existed_before and expiry and expiry <= now:
        remaining = 0
        state = "EXPIRED"
    else:
        remaining = None
        state = "INACTIVE"
    return {
        "state": state,
        "active": active,
        "expires_at": expiry.isoformat() if expiry else None,
        "remaining_days": remaining,
    }


def _autotrade_customer_state(uid: int, auto_status: dict[str, Any]) -> dict[str, Any]:
    active = bool(auto_status.get("active"))
    if not active:
        expired = str(auto_status.get("state") or "").upper() == "EXPIRED"
        return {
            "setup_state": "EXPIRED" if expired else "NO_SUBSCRIPTION",
            "headline_fa": "AutoTrade غیرفعال است",
            "message_fa": "اشتراک AutoTrade شما منقضی شده است." if expired else "اشتراک AutoTrade ندارید.",
            "cta_fa": "فعال‌سازی مجدد AutoTrade" if expired else "خرید AutoTrade",
            "cta_action": "plans",
        }

    auto = _autotrade(uid)
    health = _autotrade_health(auto)
    mt5 = auto.get("mt5") or None
    license_row = db.active_license(uid)
    license_valid = bool(license_row is not None and int(license_row["autotrade_access"] or 0) == 1)

    if not license_valid:
        return {
            "setup_state": "LICENSE_REQUIRED",
            "headline_fa": "AutoTrade نیاز به راه‌اندازی دارد",
            "message_fa": "اشتراک فعال است اما لایسنس معتبر AutoTrade پیدا نشد.",
            "cta_fa": "راه‌اندازی AutoTrade",
            "cta_action": "guide",
            "license_valid": False,
            "health": health,
        }
    if not mt5:
        return {
            "setup_state": "MT5_REQUIRED",
            "headline_fa": "AutoTrade نیاز به راه‌اندازی دارد",
            "message_fa": "اشتراک و لایسنس فعال‌اند؛ حساب MT5 هنوز متصل نشده است.",
            "cta_fa": "راه‌اندازی AutoTrade",
            "cta_action": "guide",
            "license_valid": True,
            "health": health,
        }
    if health and health.get("state") in {"DISCONNECTED", "NEEDS_ATTENTION"}:
        return {
            "setup_state": "CONNECTION_ISSUE",
            "headline_fa": "اتصال AutoTrade نیاز به بررسی دارد",
            "message_fa": "اشتراک و MT5 ثبت شده‌اند اما وضعیت اتصال فعلی سالم نیست.",
            "cta_fa": "رفع مشکل اتصال",
            "cta_action": "trades",
            "license_valid": True,
            "health": health,
        }
    return {
        "setup_state": "CONNECTED",
        "headline_fa": "AutoTrade متصل و فعال است",
        "message_fa": "اشتراک، لایسنس و اتصال MT5 آماده هستند.",
        "cta_fa": "معاملات من",
        "cta_action": "trades",
        "license_valid": True,
        "health": health,
    }


def build_account_status(uid: int) -> dict[str, Any]:
    ent = _entitlements(uid)
    latest = db.latest_license(uid)
    old = dict(latest) if latest is not None else {}
    vip = _service_status(
        active=bool(ent.get("vip")),
        expires_at=ent.get("vip_expires_at"),
        existed_before=bool(old.get("vip_access")),
        previous_expiry=old.get("vip_expires_at") or old.get("expires_at"),
    )
    auto = _service_status(
        active=bool(ent.get("autotrade")),
        expires_at=ent.get("autotrade_expires_at"),
        existed_before=bool(old.get("autotrade_access")),
        previous_expiry=old.get("autotrade_expires_at") or old.get("expires_at"),
    )
    with db.conn() as con:
        mt5 = con.execute(
            "SELECT account_number,broker,server,status,ea_version,last_seen_at FROM autotrade_mt5_accounts WHERE telegram_id=? LIMIT 1",
            (uid,),
        ).fetchone()
        payment_count = int(con.execute("SELECT COUNT(*) FROM payments WHERE telegram_id=?", (uid,)).fetchone()[0])
    mt5_data = dict(mt5) if mt5 is not None else None
    auto_state = _autotrade_customer_state(uid, auto)
    return {
        "vip": vip,
        "autotrade": {
            **auto,
            **auto_state,
            "mt5_bound": bool(mt5_data and mt5_data.get("account_number")),
            "mt5_account_masked": f"****{str(mt5_data.get('account_number'))[-4:]}" if mt5_data and mt5_data.get("account_number") else None,
            "broker": mt5_data.get("broker") if mt5_data else None,
            "server": mt5_data.get("server") if mt5_data else None,
            "ea_status": str(mt5_data.get("status") or "") if mt5_data else "",
            "ea_version": str(mt5_data.get("ea_version") or "") if mt5_data else "",
            "last_seen_at": mt5_data.get("last_seen_at") if mt5_data else None,
        },
        "payments_count": payment_count,
        "is_admin": uid in settings.admin_ids,
    }


@router.get("/account/status")
def account_status(
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    uid = int(_auth_user(x_telegram_init_data)["id"])
    return build_account_status(uid)
