from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qsl
from zoneinfo import ZoneInfo

from aiogram import Bot
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from . import db
from .autotrade import risk_firewall
from .config import settings

router = APIRouter(prefix="/api/v1/miniapp", tags=["telegram-miniapp"])


def ensure_schema() -> None:
    with db.conn() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS support_tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                subject TEXT NOT NULL,
                message TEXT NOT NULL,
                priority TEXT NOT NULL DEFAULT 'NORMAL',
                status TEXT NOT NULL DEFAULT 'OPEN',
                assigned_to INTEGER,
                admin_reply TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(telegram_id) REFERENCES users(telegram_id)
            );
            CREATE INDEX IF NOT EXISTS idx_support_tickets_user_time
                ON support_tickets(telegram_id, created_at DESC);
            """
        )


def validate_init_data(raw: str, *, max_age: int = 3600) -> dict[str, Any]:
    """Validate Telegram WebApp initData using Telegram's HMAC contract."""
    try:
        pairs = dict(parse_qsl(raw, keep_blank_values=True, strict_parsing=True))
        received_hash = pairs.pop("hash")
        auth_date = int(pairs["auth_date"])
        now = int(time.time())
        if auth_date > now + 60 or now - auth_date > int(max_age):
            raise ValueError("expired")
        check = "\n".join(f"{key}={pairs[key]}" for key in sorted(pairs))
        secret = hmac.new(b"WebAppData", settings.bot_token.encode("utf-8"), hashlib.sha256).digest()
        expected = hmac.new(secret, check.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(received_hash, expected):
            raise ValueError("signature")
        user = json.loads(pairs["user"])
        if not isinstance(user, dict) or int(user.get("id", 0)) <= 0:
            raise ValueError("user")
        return user
    except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=401, detail="Telegram authentication is invalid or expired") from exc


def _development_identity() -> dict[str, Any] | None:
    enabled = os.getenv("MINIAPP_DEV_BYPASS", "false").strip().lower() in {"1", "true", "yes", "on"}
    if not enabled:
        return None
    env = os.getenv("NEXUS_ENV", "production").strip().lower()
    if env not in {"dev", "development", "test"}:
        raise HTTPException(status_code=503, detail="Mini App development bypass is forbidden in production")
    uid = int(os.getenv("MINIAPP_DEV_USER_ID", "990000001"))
    return {
        "id": uid,
        "username": "nexus_demo",
        "first_name": "NEXUS Demo",
        "language_code": "fa",
    }


def current_user(x_telegram_init_data: str | None = Header(None)) -> dict[str, Any]:
    user = None
    if not x_telegram_init_data:
        user = _development_identity()
    if user is None:
        if not x_telegram_init_data:
            raise HTTPException(status_code=401, detail="Open the Mini App from the NEXUS Telegram bot")
        user = validate_init_data(x_telegram_init_data)

    uid = int(user["id"])
    db.upsert_user(uid, user.get("username"), user.get("first_name"))
    stored = db.get_user(uid)
    if stored and "status" in stored.keys() and str(stored["status"] or "").upper() == "BLOCKED":
        raise HTTPException(status_code=403, detail="This account is blocked")
    return {**user, "id": uid, "is_admin": uid in settings.admin_ids}


def admin_user(user=Depends(current_user)):
    if not user["is_admin"]:
        raise HTTPException(status_code=403, detail="Administrator access is required")
    return user


def _row(value: Any) -> dict[str, Any] | None:
    return dict(value) if value is not None else None


def _rows(values: Any) -> list[dict[str, Any]]:
    return [dict(value) for value in values]


def _license(uid: int):
    return db.active_license(uid)


def _today_bounds() -> tuple[str, str]:
    local_now = datetime.now(ZoneInfo(settings.timezone))
    local_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    utc_start = local_start.astimezone(timezone.utc)
    return utc_start.isoformat(), (utc_start + timedelta(days=1)).isoformat()


@router.get("/session")
def session(user=Depends(current_user)):
    ensure_schema()
    uid = int(user["id"])
    lic = _license(uid)
    return {
        "user": {
            "telegram_id": uid,
            "username": user.get("username"),
            "first_name": user.get("first_name"),
            "is_admin": bool(user["is_admin"]),
        },
        "entitlements": {
            "vip": db.has_entitlement(uid, "vip") if lic else False,
            "autotrade": db.has_entitlement(uid, "autotrade") if lic else False,
        },
        "license": _row(lic),
        "level": db.user_level(uid),
        "referral": db.referral_stats(uid),
        "mt5": _row(db.mt5_account(uid)),
        "waitlist": db.is_on_autotrade_waitlist(uid),
        "links": {
            "public": settings.public_channel_url,
            "free": settings.free_channel_url,
            "support": settings.support_url,
        },
        "capabilities": {
            "signal_view": True,
            "signal_issue": False,
            "signal_publish": False,
        },
    }


@router.get("/signals")
def signals(limit: int = Query(50, ge=1, le=100), user=Depends(current_user)):
    uid = int(user["id"])
    vip = bool(_license(uid) and db.has_entitlement(uid, "vip"))
    start, end = _today_bounds()
    with db.conn() as con:
        rows = con.execute(
            """SELECT id,code,market_type,symbol,direction,timeframe,order_type,entry_price,stop_loss,
                      status,destination,trailing_code,created_at,closed_at,result_value,result_unit
               FROM signals
               WHERE created_at>=? AND created_at<? AND destination IN ('FREE','VIP','BOTH')
               ORDER BY id DESC LIMIT ?""",
            (start, end, int(limit)),
        ).fetchall()
        result: list[dict[str, Any]] = []
        for item in rows:
            signal = dict(item)
            destination = str(signal["destination"] or "BOTH").upper()
            vip_only = destination == "VIP"
            signal["channel"] = "VIP" if vip_only else "FREE"
            signal["locked"] = bool(vip_only and not vip)
            if signal["locked"]:
                result.append({
                    "id": signal["id"],
                    "symbol": signal["symbol"],
                    "status": signal["status"],
                    "destination": "VIP",
                    "channel": "VIP",
                    "locked": True,
                })
                continue
            signal["targets"] = [
                dict(row)
                for row in con.execute(
                    "SELECT target_no,price FROM signal_targets WHERE signal_id=? ORDER BY target_no",
                    (int(item["id"]),),
                ).fetchall()
            ]
            result.append(signal)
    return {"items": result, "timezone": settings.timezone}


@router.post("/vip-channel-link")
async def vip_channel_link(user=Depends(current_user)):
    uid = int(user["id"])
    lic = _license(uid)
    if not lic or not db.has_entitlement(uid, "vip"):
        raise HTTPException(status_code=402, detail="VIP subscription is required")
    active = db.active_invites_for_user(uid)
    if active:
        return {"url": str(active[-1]["invite_link"])}
    async with Bot(settings.bot_token) as bot:
        invite = await bot.create_chat_invite_link(
            settings.vip_channel_id,
            name=f"NEXUS-MINIAPP-{uid}-{int(lic['id'])}",
            creates_join_request=True,
        )
    db.save_invite(uid, int(lic["id"]), invite.invite_link)
    db.add_audit(uid, "miniapp_vip_invite_created", int(lic["id"]), None)
    return {"url": invite.invite_link}


@router.get("/autotrade")
def autotrade(user=Depends(current_user)):
    uid = int(user["id"])
    account = db.mt5_account(uid)
    start = _utc_day_start()
    return {
        "account": _row(account),
        "open": _rows(db.autotrade_user_signal_receipts(uid, limit=100, open_only=True)),
        "history": _rows(db.autotrade_user_signal_receipts(uid, limit=100)),
        "today": db.autotrade_user_daily_stats(uid, start.isoformat(), (start + timedelta(days=1)).isoformat()),
        "risk": risk_firewall._profile(uid),
        "global_kill_switch": risk_firewall.global_kill_switch(),
    }


def _utc_day_start() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


class RiskWrite(BaseModel):
    daily_loss_limit_r: float | None = Field(None, ge=0.25, le=20)
    dynamic_risk_enabled: bool | None = None
    min_risk_multiplier: float | None = Field(None, ge=0.10, le=1.0)
    max_loss_streak: int | None = Field(None, ge=1, le=10)
    kill_switch: bool | None = None


@router.put("/risk")
def save_risk(req: RiskWrite, user=Depends(current_user)):
    uid = int(user["id"])
    try:
        profile = risk_firewall.set_user_profile(uid, **req.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.add_audit(uid, "miniapp_risk_updated", uid, req.model_dump_json())
    return profile


@router.get("/commerce")
def commerce(user=Depends(current_user)):
    plans = []
    for code, plan in db.plan_map(active_only=True).items():
        category = (
            "bundle" if plan["vip_access"] and plan["autotrade_access"]
            else "autotrade" if plan["autotrade_access"]
            else "vip"
        )
        plans.append({"code": code, "category": category, **plan})
    return {
        "plans": plans,
        "payments": _rows(db.user_payments(int(user["id"]))),
        "license": _row(_license(int(user["id"]))),
        "payment": {
            "card": settings.payment_card,
            "owner": settings.payment_owner,
            "usdt_wallet": settings.usdt_wallet,
            "usdt_network": settings.usdt_network,
        },
    }


@router.get("/referral")
def referral(user=Depends(current_user)):
    stored = db.get_user(int(user["id"]))
    return {
        "stats": db.referral_stats(int(user["id"])),
        "code": stored["referral_code"] if stored else None,
        "bot_username": os.getenv("BOT_USERNAME", "").strip(),
    }


class AccountChangeWrite(BaseModel):
    new_account_number: str = Field(min_length=3, max_length=32)
    broker: str | None = Field(None, max_length=128)
    server: str | None = Field(None, max_length=128)
    reason: str | None = Field(None, max_length=500)


@router.post("/autotrade/account-change", status_code=201)
def account_change(req: AccountChangeWrite, user=Depends(current_user)):
    try:
        row = db.request_mt5_account_change(
            int(user["id"]), req.new_account_number, req.broker, req.server, req.reason
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.add_audit(int(user["id"]), "miniapp_mt5_account_change", int(row["id"]), req.new_account_number)
    return dict(row)


class WaitlistWrite(BaseModel):
    active: bool


@router.put("/autotrade/waitlist")
def waitlist(req: WaitlistWrite, user=Depends(current_user)):
    uid = int(user["id"])
    (db.join_autotrade_waitlist if req.active else db.leave_autotrade_waitlist)(uid)
    return {"ok": True, "active": req.active}


class SupportWrite(BaseModel):
    subject: str = Field(min_length=2, max_length=160)
    message: str = Field(min_length=2, max_length=4000)
    priority: str = Field(default="NORMAL", pattern="^(LOW|NORMAL|HIGH|URGENT)$")


@router.get("/support")
def support(user=Depends(current_user)):
    ensure_schema()
    with db.conn() as con:
        rows = con.execute(
            """SELECT id,subject,message,priority,status,admin_reply,created_at,updated_at
               FROM support_tickets WHERE telegram_id=? ORDER BY id DESC""",
            (int(user["id"]),),
        ).fetchall()
    return {"items": _rows(rows), "support_url": settings.support_url}


@router.post("/support", status_code=201)
def create_support(req: SupportWrite, user=Depends(current_user)):
    ensure_schema()
    now = db.now_iso()
    with db.conn() as con:
        cur = con.execute(
            """INSERT INTO support_tickets(telegram_id,subject,message,priority,status,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?)""",
            (int(user["id"]), req.subject, req.message, req.priority, "OPEN", now, now),
        )
    return {"id": int(cur.lastrowid), "ok": True}


@router.get("/admin/overview")
def admin_overview(user=Depends(admin_user)):
    # Mini App admin remains a monitoring/control companion. Signal issuance is
    # intentionally absent and contract-tested elsewhere.
    return {
        "stats": db.stats(),
        "entitlements": db.entitlement_counts(),
        "waitlist": db.autotrade_waitlist_count(),
        "global_kill_switch": risk_firewall.global_kill_switch(),
        "signal_issue": False,
    }
