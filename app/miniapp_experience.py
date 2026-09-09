from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Header

from . import db
from .miniapp_api import _auth_user, _entitlements

router = APIRouter(prefix="/miniapp/api", tags=["NEXUS Mini App Experience"])

EXPIRING_DAYS = max(1, min(int(os.getenv("MINIAPP_EXPIRING_DAYS", "7")), 30))


def _parse_dt(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _segment(vip: bool, autotrade: bool) -> str:
    if vip and autotrade:
        return "BUNDLE"
    if autotrade:
        return "AUTOTRADE"
    if vip:
        return "VIP"
    return "GUEST"


def _navigation(segment: str, lifecycle: str) -> list[dict[str, str]]:
    if lifecycle != "EXPIRED" and segment in {"AUTOTRADE", "BUNDLE"}:
        third = {"route": "trades", "label_fa": "معاملات", "label_en": "Trades", "icon": "◉"}
    elif segment == "VIP" and lifecycle != "EXPIRED":
        third = {"route": "subscriptions", "label_fa": "ارتقا", "label_en": "Upgrade", "icon": "◆"}
    else:
        third = {"route": "subscriptions", "label_fa": "پلن‌ها", "label_en": "Plans", "icon": "◆"}
    return [
        {"route": "home", "label_fa": "خانه", "label_en": "Home", "icon": "⌂"},
        {"route": "signals", "label_fa": "سیگنال‌ها", "label_en": "Signals", "icon": "◈"},
        third,
        {"route": "account", "label_fa": "حساب من", "label_en": "Account", "icon": "◎"},
    ]


def build_experience_context(
    entitlements: dict[str, Any],
    latest_license: dict[str, Any] | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build the customer-facing shell state from server-side subscription truth.

    This function deliberately contains no frontend state and performs no access
    grant. It only translates canonical entitlement/license state into a safe UI
    segment and navigation model.
    """
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)

    vip = bool(entitlements.get("vip"))
    autotrade = bool(entitlements.get("autotrade"))
    segment = _segment(vip, autotrade)

    active_expiries: list[datetime] = []
    if vip:
        dt = _parse_dt(entitlements.get("vip_expires_at"))
        if dt:
            active_expiries.append(dt)
    if autotrade:
        dt = _parse_dt(entitlements.get("autotrade_expires_at"))
        if dt:
            active_expiries.append(dt)

    next_expiry = min(active_expiries) if active_expiries else None
    expiring = bool(next_expiry and current <= next_expiry <= current + timedelta(days=EXPIRING_DAYS))
    lifecycle = "EXPIRING" if expiring else ("ACTIVE" if (vip or autotrade) else "GUEST")

    previous_segment: str | None = None
    last_expiry: datetime | None = None
    if not (vip or autotrade) and latest_license:
        last_vip = bool(latest_license.get("vip_access"))
        last_auto = bool(latest_license.get("autotrade_access"))
        previous_segment = _segment(last_vip, last_auto)
        candidates = [
            _parse_dt(latest_license.get("vip_expires_at")) if last_vip else None,
            _parse_dt(latest_license.get("autotrade_expires_at")) if last_auto else None,
            _parse_dt(latest_license.get("expires_at")),
        ]
        candidates = [x for x in candidates if x is not None]
        last_expiry = max(candidates) if candidates else None
        if previous_segment != "GUEST" and last_expiry and last_expiry <= current:
            lifecycle = "EXPIRED"
            segment = previous_segment

    nav = _navigation(segment, lifecycle)
    return {
        "segment": segment,
        "lifecycle": lifecycle,
        "expiring": expiring,
        "expiring_days": EXPIRING_DAYS,
        "next_expiry_at": next_expiry.isoformat() if next_expiry else None,
        "last_expiry_at": last_expiry.isoformat() if last_expiry else None,
        "entitlements": {"vip": vip, "autotrade": autotrade},
        "navigation": nav,
        "features": {
            "trades": lifecycle != "EXPIRED" and segment in {"AUTOTRADE", "BUNDLE"},
            "plans": not (lifecycle != "EXPIRED" and segment in {"AUTOTRADE", "BUNDLE"}),
        },
    }


@router.get("/experience")
def experience(
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    uid = int(_auth_user(x_telegram_init_data)["id"])
    ent = _entitlements(uid)
    latest = db.latest_license(uid)
    return build_experience_context(ent, dict(latest) if latest is not None else None)
