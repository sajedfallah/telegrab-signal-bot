from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query

from . import db
from .miniapp_api import _auth_user, _autotrade, _entitlements
from .miniapp_experience import _parse_dt, build_experience_context
from .miniapp_signals import _active_truth_clause
from .services import analytics_service

router = APIRouter(prefix="/miniapp/api", tags=["NEXUS Mini App Home"])

AUTOTRADE_STALE_SECONDS = max(120, min(int(os.getenv("MINIAPP_AUTOTRADE_STALE_SECONDS", "300")), 3600))
PERFORMANCE_PERIODS = {"7", "30", "90", "all"}
NEXUS_ENTRY_URL = "https://t.me/nexus_publicc"
CUSTOMER_INACTIVE_STATUSES = {"DRAFT", "REJECTED", "CANCELLED", "EXPIRED", "PUBLISH_FAILED"}


def _safe_performance(key: str) -> dict[str, Any]:
    data = analytics_service.overview(key)
    p = data["period"]
    return {
        "period": p.key,
        "label_fa": p.label_fa,
        "label_en": p.label_en,
        "active": int(data.get("active") or 0),
        "total": int(data.get("total") or 0),
        "wins": int(data.get("wins") or 0),
        "losses": int(data.get("losses") or 0),
        "be": int(data.get("be") or 0),
        "win_rate": float(data.get("win_rate") or 0),
        "disclaimer_fa": "این آمار مربوط به نتایج سیگنال‌های ثبت‌شده NEXUS است و بازده حساب معاملاتی نیست.",
        "disclaimer_en": "These metrics describe recorded NEXUS signal outcomes, not trading-account return.",
    }


def _result_meta(item: dict[str, Any]) -> tuple[str | None, float | None, str | None, str | None]:
    if str(item.get("status") or "").upper() != "CLOSED":
        return None, None, None, None
    raw = item.get("result_value")
    unit = str(item.get("result_unit") or "").strip().upper() or None
    if raw is None:
        return "UNKNOWN", None, unit, "نتیجه ثبت نشده"
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return "UNKNOWN", None, unit, "نتیجه ثبت نشده"
    suffix = f" {unit}" if unit else ""
    if value > 0:
        return "WIN", value, unit, f"سود +{value:g}{suffix}"
    if value < 0:
        return "LOSS", value, unit, f"ضرر {value:g}{suffix}"
    return "BE", value, unit, f"سر‌به‌سر 0{suffix}"


def _safe_signal(row: Any, *, has_vip: bool) -> dict[str, Any]:
    item = dict(row)
    destination = str(item.get("destination") or "FREE").upper()
    status = str(item.get("status") or "").upper()
    closed = status == "CLOSED"
    vip_only = destination == "VIP"
    locked = bool(vip_only and not has_vip and not closed)
    result, result_value, result_unit, result_label_fa = _result_meta(item)
    return {
        "id": int(item["id"]),
        "code": str(item.get("code") or ""),
        "symbol": str(item.get("symbol") or "—"),
        "direction": None if locked else str(item.get("direction") or ""),
        "access": "VIP" if vip_only else "FREE",
        "status": status,
        "published_at": item.get("created_at"),
        "closed_at": item.get("closed_at"),
        "result": result,
        "result_value": result_value,
        "result_unit": result_unit,
        "result_label_fa": result_label_fa,
        "locked": locked,
    }


def _recent_signals(*, has_vip: bool, limit: int = 3) -> list[dict[str, Any]]:
    cycle = db.current_cycle_id()
    visibility = "1=1" if has_vip else "NOT (UPPER(COALESCE(destination,'FREE'))='VIP' AND UPPER(COALESCE(status,''))<>'CLOSED')"
    live_sql, live_args = _active_truth_clause("ACTIVE")
    with db.conn() as con:
        rows = con.execute(
            f"""
            SELECT id,code,symbol,direction,destination,status,created_at,closed_at,result_value,result_unit,
                   issuer_type,issuer_account
            FROM signals
            WHERE COALESCE(cycle_id, ?) = ?
              AND UPPER(COALESCE(status,'')) NOT IN ('DRAFT','REJECTED','CANCELLED','EXPIRED','PUBLISH_FAILED')
              AND {visibility}
              AND (UPPER(COALESCE(status,''))='CLOSED' OR ({live_sql}))
            ORDER BY id DESC
            LIMIT ?
            """,
            (cycle, cycle, *live_args, max(1, min(limit, 10))),
        ).fetchall()
    return [_safe_signal(row, has_vip=has_vip) for row in rows]


def _today() -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    cycle = db.current_cycle_id()
    live_sql, live_args = _active_truth_clause("ACTIVE")
    with db.conn() as con:
        active = int(con.execute(
            f"""SELECT COUNT(*) FROM signals
               WHERE UPPER(COALESCE(status,'')) NOT IN ('DRAFT','CLOSED','REJECTED','CANCELLED','EXPIRED','PUBLISH_FAILED')
                 AND ({live_sql})
                 AND COALESCE(cycle_id,?)=?""",
            (*live_args, cycle, cycle),
        ).fetchone()[0])
        closed = int(con.execute(
            "SELECT COUNT(*) FROM signals WHERE UPPER(COALESCE(status,''))='CLOSED' AND closed_at>=? AND COALESCE(cycle_id,?)=?",
            (start, cycle, cycle),
        ).fetchone()[0])
    return {"active_signals": active, "closed_signals": closed, "as_of": now.isoformat()}


def _autotrade_health(auto: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any] | None:
    if not auto.get("entitled"):
        return None
    current = now or datetime.now(timezone.utc)
    mt5 = auto.get("mt5") or None
    if not mt5:
        return {
            "state": "NEEDS_ATTENTION",
            "reason": "SETUP_INCOMPLETE",
            "mt5_account": None,
            "last_sync_at": None,
            "stale_after_seconds": AUTOTRADE_STALE_SECONDS,
        }
    last_seen = _parse_dt(mt5.get("last_seen_at"))
    status = str(mt5.get("status") or "").upper()
    if not last_seen:
        state, reason = "NEEDS_ATTENTION", "NO_HEARTBEAT"
    elif current.astimezone(timezone.utc) - last_seen > timedelta(seconds=AUTOTRADE_STALE_SECONDS):
        state, reason = "DISCONNECTED", "HEARTBEAT_STALE"
    elif status in {"ERROR", "DISABLED", "BLOCKED", "EXPIRED"}:
        state, reason = "NEEDS_ATTENTION", "ACCOUNT_STATUS"
    else:
        state, reason = "HEALTHY", None
    return {
        "state": state,
        "reason": reason,
        "mt5_account": str(mt5.get("account_number") or ""),
        "broker": str(mt5.get("broker") or ""),
        "server": str(mt5.get("server") or ""),
        "ea_version": str(mt5.get("ea_version") or ""),
        "last_sync_at": last_seen.isoformat() if last_seen else None,
        "stale_after_seconds": AUTOTRADE_STALE_SECONDS,
        "open_trades": len(auto.get("open_positions") or []),
        "pending_orders": len(auto.get("pending_orders") or []),
    }


def _attention(experience: dict[str, Any], health: dict[str, Any] | None) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if health and health["state"] in {"DISCONNECTED", "NEEDS_ATTENTION"}:
        items.append({
            "priority": 100,
            "kind": "AUTOTRADE",
            "title_fa": "اتصال AutoTrade نیاز به بررسی دارد",
            "title_en": "AutoTrade needs attention",
            "cta_fa": "بررسی اتصال",
            "cta_en": "Check connection",
            "destination": "trades",
            "reason": health.get("reason"),
        })
    if experience.get("lifecycle") == "EXPIRING":
        items.append({
            "priority": 80,
            "kind": "EXPIRY",
            "title_fa": "اشتراک شما به پایان دوره نزدیک است",
            "title_en": "Your subscription is nearing expiry",
            "cta_fa": "تمدید اشتراک",
            "cta_en": "Renew",
            "destination": "subscriptions",
            "expires_at": experience.get("next_expiry_at"),
        })
    return sorted(items, key=lambda item: int(item["priority"]), reverse=True)


def _spotlight(experience: dict[str, Any], health: dict[str, Any] | None) -> dict[str, Any]:
    segment = str(experience.get("segment") or "GUEST")
    lifecycle = str(experience.get("lifecycle") or "GUEST")
    if health and health.get("state") in {"DISCONNECTED", "NEEDS_ATTENTION"}:
        return {
            "kind": "OPERATIONAL",
            "title_fa": "AutoTrade شما نیاز به بررسی دارد",
            "subtitle_fa": "وضعیت اتصال و آخرین Sync را بررسی کنید.",
            "cta_fa": "مشاهده وضعیت",
            "destination": "trades",
        }
    if lifecycle == "EXPIRING":
        return {
            "kind": "RENEWAL",
            "title_fa": "زمان تمدید NEXUS نزدیک است",
            "subtitle_fa": "تاریخ پایان دسترسی را بررسی و در صورت نیاز تمدید کنید.",
            "cta_fa": "مشاهده تمدید",
            "destination": "subscriptions",
        }
    if lifecycle == "EXPIRED":
        return {
            "kind": "REACTIVATION",
            "title_fa": "دسترسی NEXUS شما پایان یافته است",
            "subtitle_fa": "نتایج اخیر را ببینید و در صورت نیاز سرویس را دوباره فعال کنید.",
            "cta_fa": "فعال‌سازی مجدد",
            "destination": "subscriptions",
        }
    if segment == "GUEST":
        return {
            "kind": "TRUST",
            "title_fa": "قبل از انتخاب اشتراک، عملکرد NEXUS را ببینید",
            "subtitle_fa": "نتایج ثبت‌شده و سیگنال‌های اخیر را شفاف بررسی کنید.",
            "cta_fa": "مشاهده نتایج",
            "destination": "performance",
        }
    if segment == "VIP":
        return {
            "kind": "USE",
            "title_fa": "سیگنال‌های NEXUS در دسترس شماست",
            "subtitle_fa": "سیگنال‌های فعال و نتایج اخیر را از مرکز سیگنال‌ها دنبال کنید.",
            "cta_fa": "مشاهده سیگنال‌ها",
            "destination": "signals",
        }
    return {
        "kind": "MONITOR",
        "title_fa": "مرکز اجرای AutoTrade شما",
        "subtitle_fa": "وضعیت اتصال و معاملات واقعی حساب متصل را بررسی کنید.",
        "cta_fa": "معاملات من",
        "destination": "trades",
    }


def _offer(experience: dict[str, Any]) -> dict[str, Any] | None:
    segment = str(experience.get("segment") or "GUEST")
    lifecycle = str(experience.get("lifecycle") or "GUEST")
    if lifecycle in {"EXPIRING", "EXPIRED"}:
        return {"kind": "RENEW", "title_fa": "تمدید دسترسی NEXUS", "cta_fa": "مشاهده پلن‌های تمدید", "destination": "subscriptions"}
    if segment == "GUEST":
        return {"kind": "NEW_CUSTOMER", "title_fa": "VIP، AutoTrade یا Bundle؟", "cta_fa": "مقایسه پلن‌ها", "destination": "subscriptions"}
    if segment == "VIP":
        return {"kind": "UPGRADE", "title_fa": "اجرای خودکار را به تجربه VIP اضافه کنید", "cta_fa": "مشاهده AutoTrade و Bundle", "destination": "subscriptions"}
    if segment == "AUTOTRADE":
        return {"kind": "UPGRADE", "title_fa": "دسترسی VIP را به AutoTrade اضافه کنید", "cta_fa": "مشاهده VIP و Bundle", "destination": "subscriptions"}
    return None


def _section_order(experience: dict[str, Any], attention: list[dict[str, Any]]) -> list[str]:
    segment = str(experience.get("segment") or "GUEST")
    lifecycle = str(experience.get("lifecycle") or "GUEST")
    if lifecycle == "EXPIRED":
        order = ["spotlight", "offer", "performance", "recent_signals", "community"]
    elif segment == "GUEST":
        order = ["spotlight", "performance", "recent_signals", "why_nexus", "offer", "community"]
    elif segment == "VIP":
        order = ["recent_signals", "performance", "offer", "subscription"]
    else:
        order = ["autotrade_health", "trades_preview", "recent_signals", "today", "subscription"]
    if attention:
        order.insert(0, "needs_attention")
    return order


def build_home_payload(uid: int) -> dict[str, Any]:
    ent = _entitlements(uid)
    latest = db.latest_license(uid)
    experience = build_experience_context(ent, dict(latest) if latest is not None else None)
    auto = _autotrade(uid) if experience["segment"] in {"AUTOTRADE", "BUNDLE"} else {"entitled": False}
    health = _autotrade_health(auto)
    attention = _attention(experience, health)
    return {
        "experience": experience,
        "enter_nexus_url": NEXUS_ENTRY_URL,
        "section_order": _section_order(experience, attention),
        "needs_attention": attention,
        "spotlight": _spotlight(experience, health),
        "today": _today(),
        "performance": _safe_performance("30"),
        "recent_signals": _recent_signals(has_vip=bool(ent.get("vip")), limit=3),
        "offer": _offer(experience),
        "autotrade_health": health,
        "trades_preview": {
            "open": (auto.get("open_positions") or [])[:2],
            "history": (auto.get("history") or [])[:2],
        } if auto.get("entitled") else None,
        "subscription": {
            "vip": bool(ent.get("vip")),
            "vip_expires_at": ent.get("vip_expires_at"),
            "autotrade": bool(ent.get("autotrade")),
            "autotrade_expires_at": ent.get("autotrade_expires_at"),
        },
    }


@router.get("/home")
def home(x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data")) -> dict[str, Any]:
    uid = int(_auth_user(x_telegram_init_data)["id"])
    return build_home_payload(uid)


@router.get("/performance")
def performance(
    period: str = Query(default="30"),
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    _auth_user(x_telegram_init_data)
    key = str(period or "30").lower()
    if key not in PERFORMANCE_PERIODS:
        raise HTTPException(status_code=400, detail="unsupported performance period")
    return _safe_performance(key)
