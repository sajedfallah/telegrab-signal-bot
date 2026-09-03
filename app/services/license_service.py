from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .. import db


@dataclass(frozen=True)
class AccessSnapshot:
    active: bool
    vip: bool
    autotrade: bool
    plan_code: str | None
    source: str | None
    expires_at: str | None
    license_id: int | None
    starts_at: str | None = None
    vip_expires_at: str | None = None
    autotrade_expires_at: str | None = None


def _iso_or_none(value: Any) -> str | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)).isoformat()
    except Exception:
        return None


def snapshot(user_id: int) -> AccessSnapshot:
    lic = db.active_license(user_id)
    if not lic:
        return AccessSnapshot(False, False, False, None, None, None, None)

    keys = set(lic.keys())
    now = datetime.now(timezone.utc)

    def raw_value(name: str) -> Any:
        return lic[name] if name in keys else None

    def alive(name: str, fallback_flag: str) -> bool:
        raw = raw_value(name)
        if not raw:
            raw = raw_value("expires_at") if bool(raw_value(fallback_flag)) else None
        if not raw:
            return False
        try:
            return datetime.fromisoformat(str(raw)) > now
        except Exception:
            return False

    vip = alive("vip_expires_at", "vip_access")
    auto = alive("autotrade_expires_at", "autotrade_access")

    vip_exp = _iso_or_none(raw_value("vip_expires_at"))
    auto_exp = _iso_or_none(raw_value("autotrade_expires_at"))
    global_exp = _iso_or_none(raw_value("expires_at"))
    starts_at = _iso_or_none(raw_value("starts_at"))

    exp_candidates: list[datetime] = []
    for raw in (vip_exp, auto_exp, global_exp):
        if not raw:
            continue
        try:
            exp_candidates.append(datetime.fromisoformat(raw))
        except Exception:
            pass
    exp = max(exp_candidates).isoformat() if exp_candidates else None

    return AccessSnapshot(
        active=bool(vip or auto),
        vip=vip,
        autotrade=auto,
        plan_code=str(raw_value("plan_code")) if raw_value("plan_code") else None,
        source=str(raw_value("source")) if raw_value("source") else None,
        expires_at=exp,
        license_id=int(raw_value("id")),
        starts_at=starts_at,
        vip_expires_at=vip_exp or (global_exp if bool(raw_value("vip_access")) else None),
        autotrade_expires_at=auto_exp or (global_exp if bool(raw_value("autotrade_access")) else None),
    )


def has_vip(user_id: int) -> bool:
    return snapshot(user_id).vip


def has_autotrade(user_id: int) -> bool:
    return snapshot(user_id).autotrade


def plan_access_label(plan: Any, lang: str = "fa") -> str:
    vip = bool(plan["vip_access"]) if "vip_access" in plan.keys() else True
    auto = bool(plan["autotrade_access"]) if "autotrade_access" in plan.keys() else True
    if lang == "fa":
        items = []
        if vip:
            items.append("VIP")
        if auto:
            items.append("معاملات خودکار")
        return " + ".join(items) if items else "بدون دسترسی کانال"
    items = []
    if vip:
        items.append("VIP")
    if auto:
        items.append("Auto Trade")
    return " + ".join(items) if items else "No channel entitlement"


def activate_payment(payment_row):
    plan = db.get_plan(str(payment_row["plan_code"]))
    vip = bool(plan["vip_access"]) if plan and "vip_access" in plan.keys() else True
    auto = bool(plan["autotrade_access"]) if plan and "autotrade_access" in plan.keys() else True
    return db.create_or_extend_license(
        int(payment_row["telegram_id"]),
        int(payment_row["id"]),
        int(payment_row["days"]),
        plan_code=str(payment_row["plan_code"]),
        source="payment",
        vip_access=vip,
        autotrade_access=auto,
    )


def grant_admin(user_id: int, days: int, admin_id: int, plan_code: str | None = None):
    plan = db.get_plan(plan_code) if plan_code else None
    vip = bool(plan["vip_access"]) if plan and "vip_access" in plan.keys() else True
    auto = bool(plan["autotrade_access"]) if plan and "autotrade_access" in plan.keys() else True
    return db.create_or_extend_license(
        user_id,
        None,
        days,
        plan_code=plan_code,
        source="admin",
        granted_by=admin_id,
        vip_access=vip,
        autotrade_access=auto,
    )
