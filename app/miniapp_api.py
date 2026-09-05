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
from .config import settings
from .services import license_service


router = APIRouter(prefix="/api/v1/miniapp", tags=["telegram-miniapp"])


def _row(value: Any) -> dict[str, Any] | None:
    return dict(value) if value is not None else None


def _rows(values: Any) -> list[dict[str, Any]]:
    return [dict(value) for value in values]


def validate_init_data(raw: str, *, max_age: int = 86400) -> dict[str, Any]:
    """Validate Telegram Mini App initData using Telegram's HMAC contract."""
    try:
        pairs = dict(parse_qsl(raw, keep_blank_values=True, strict_parsing=True))
        received_hash = pairs.pop("hash")
        auth_date = int(pairs["auth_date"])
        if abs(int(time.time()) - auth_date) > max_age:
            raise ValueError("expired")
        check = "\n".join(f"{key}={pairs[key]}" for key in sorted(pairs))
        secret = hmac.new(b"WebAppData", settings.bot_token.encode(), hashlib.sha256).digest()
        expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(received_hash, expected):
            raise ValueError("signature")
        user = json.loads(pairs["user"])
        if not isinstance(user, dict) or int(user.get("id", 0)) <= 0:
            raise ValueError("user")
        return user
    except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(401, "Telegram authentication is invalid or expired") from exc


def current_user(x_telegram_init_data: str | None = Header(None)) -> dict[str, Any]:
    if os.getenv("MINIAPP_DEV_BYPASS", "false").lower() in {"1", "true", "yes"} and not x_telegram_init_data:
        uid = int(os.getenv("MINIAPP_DEV_USER_ID", "990000001"))
        user = {"id": uid, "username": "nexus_demo", "first_name": "NEXUS Demo", "language_code": "fa"}
    else:
        if not x_telegram_init_data:
            raise HTTPException(401, "Open the Mini App from the NEXUS Telegram bot")
        user = validate_init_data(x_telegram_init_data)
    db.upsert_user(int(user["id"]), user.get("username"), user.get("first_name"))
    stored = db.get_user(int(user["id"]))
    if stored and "status" in stored.keys() and str(stored["status"]).upper() == "BLOCKED":
        raise HTTPException(403, "This account is blocked")
    return {**user, "id": int(user["id"]), "is_admin": int(user["id"]) in settings.admin_ids}


def admin_user(user=Depends(current_user)):
    if not user["is_admin"]:
        raise HTTPException(403, "Administrator access is required")
    return user


def _license(uid: int) -> dict[str, Any] | None:
    return _row(db.active_license(uid))


def _signals(uid: int, limit: int = 50) -> list[dict[str, Any]]:
    vip = bool(_license(uid) and db.has_entitlement(uid, "vip"))
    local_now = datetime.now(ZoneInfo(settings.timezone))
    local_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    utc_start = local_start.astimezone(timezone.utc).isoformat()
    utc_end = (local_start + timedelta(days=1)).astimezone(timezone.utc).isoformat()
    with db.conn() as con:
        rows = con.execute(
            """SELECT id,code,market_type,symbol,direction,timeframe,order_type,entry_price,stop_loss,
                      status,destination,trailing_code,created_at,closed_at,result_value,result_unit
               FROM signals
               WHERE created_at>=? AND created_at<? AND destination IN ('FREE','VIP','BOTH')
               ORDER BY id DESC LIMIT ?""",
            (utc_start, utc_end, max(1, min(limit, 100))),
        ).fetchall()
        result = []
        for item in rows:
            signal = dict(item)
            is_vip_only = str(signal["destination"]).upper() == "VIP"
            signal["channel"] = "VIP" if is_vip_only else "FREE"
            signal["locked"] = bool(is_vip_only and not vip)
            if signal["locked"]:
                result.append({
                    "id": signal["id"], "symbol": signal["symbol"], "status": signal["status"],
                    "destination": "VIP", "channel": "VIP", "locked": True,
                })
                continue
            signal["targets"] = [dict(x) for x in con.execute(
                "SELECT target_no,price FROM signal_targets WHERE signal_id=? ORDER BY target_no", (item["id"],)
            )]
            result.append(signal)
    return result


@router.get("/session")
def session(user=Depends(current_user)):
    uid = user["id"]
    stored = _row(db.get_user(uid)) or {}
    lic = _license(uid)
    account = _row(db.mt5_account(uid))
    exchange = _row(db.exchange_account(uid))
    return {
        "user": {**stored, "telegram_id": uid, "is_admin": user["is_admin"]},
        "license": lic,
        "entitlements": {"vip": db.has_entitlement(uid, "vip") if lic else False, "autotrade": db.has_entitlement(uid, "autotrade") if lic else False},
        "level": db.user_level(uid),
        "referral": db.referral_stats(uid),
        "mt5": account,
        "exchange": exchange,
        "waitlist": db.is_on_autotrade_waitlist(uid),
        "links": {"public": settings.public_channel_url, "free": settings.free_channel_url, "support": settings.support_url},
    }


@router.post("/vip-channel-link")
async def vip_channel_link(user=Depends(current_user)):
    uid = user["id"]
    lic = _license(uid)
    if not lic or not db.has_entitlement(uid, "vip"):
        raise HTTPException(402, "VIP subscription is required")
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


@router.get("/signals")
def signals(limit: int = Query(50, ge=1, le=100), user=Depends(current_user)):
    return {"items": _signals(user["id"], limit)}


@router.get("/autotrade")
def autotrade(user=Depends(current_user)):
    uid = user["id"]
    now = datetime.now(timezone.utc)
    start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    with db.conn() as con:
        pref = con.execute("SELECT * FROM user_risk_preferences WHERE telegram_id=?", (uid,)).fetchone()
    return {
        "account": _row(db.mt5_account(uid)),
        "open": _rows(db.autotrade_user_signal_receipts(uid, limit=100, open_only=True)),
        "history": _rows(db.autotrade_user_signal_receipts(uid, limit=100)),
        "today": db.autotrade_user_daily_stats(uid, start.isoformat(), (start + timedelta(days=1)).isoformat()),
        "risk": _row(pref) or {"management_mode": "SELF", "risk_percent": 1, "max_daily_loss": 3, "max_open_trades": 3, "max_daily_trades": 10, "fixed_lot": None, "emergency_stop": 0},
    }


class RiskWrite(BaseModel):
    management_mode: str = Field(pattern="^(SELF|ADMIN)$")
    risk_percent: float = Field(ge=0.1, le=10)
    max_daily_loss: float = Field(ge=0.5, le=25)
    max_open_trades: int = Field(ge=1, le=20)
    max_daily_trades: int = Field(ge=1, le=100)
    fixed_lot: float | None = Field(None, gt=0, le=100)
    emergency_stop: bool = False


@router.put("/risk")
def save_risk(req: RiskWrite, user=Depends(current_user)):
    uid = user["id"]
    with db.conn() as con:
        con.execute(
            """INSERT INTO user_risk_preferences(telegram_id,management_mode,risk_percent,max_daily_loss,max_open_trades,max_daily_trades,fixed_lot,emergency_stop,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(telegram_id) DO UPDATE SET management_mode=excluded.management_mode,
               risk_percent=excluded.risk_percent,max_daily_loss=excluded.max_daily_loss,max_open_trades=excluded.max_open_trades,
               max_daily_trades=excluded.max_daily_trades,fixed_lot=excluded.fixed_lot,emergency_stop=excluded.emergency_stop,updated_at=excluded.updated_at""",
            (uid, req.management_mode, req.risk_percent, req.max_daily_loss, req.max_open_trades, req.max_daily_trades, req.fixed_lot, int(req.emergency_stop), db.now_iso()),
        )
    db.add_audit(uid, "miniapp_risk_updated", uid, req.model_dump_json())
    return {"ok": True}


@router.get("/commerce")
def commerce(user=Depends(current_user)):
    plans = []
    for code, plan in db.plan_map(active_only=True).items():
        category = "bundle" if plan["vip_access"] and plan["autotrade_access"] else ("autotrade" if plan["autotrade_access"] else "vip")
        plans.append({"code": code, "category": category, **plan})
    return {
        "plans": plans,
        "payments": _rows(db.user_payments(user["id"])),
        "license": _license(user["id"]),
        "payment": {
            "card": settings.payment_card,
            "owner": settings.payment_owner,
            "usdt_wallet": settings.usdt_wallet,
            "usdt_network": settings.usdt_network,
        },
    }


class PaymentWrite(BaseModel):
    plan_code: str = Field(min_length=2, max_length=64)
    method: str = Field(pattern="^(CARD|USDT)$")
    reference: str = Field(min_length=4, max_length=256)


@router.post("/payments", status_code=201)
def submit_payment(req: PaymentWrite, user=Depends(current_user)):
    plans = db.plan_map(active_only=True)
    plan = plans.get(req.plan_code)
    if not plan:
        raise HTTPException(404, "Plan is not available")
    reference = req.reference.strip()
    try:
        payment_id = db.create_payment(
            telegram_id=user["id"],
            plan_code=req.plan_code,
            days=int(plan["days"]),
            price_label=str(plan["price_usdt"]),
            payment_method=req.method,
            receipt_file_id=f"miniapp:{reference}",
            receipt_type="miniapp_reference",
            amount_usdt=plan["price_usdt"],
            transaction_hash=reference if req.method == "USDT" else None,
            payment_reference=reference,
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    db.add_audit(user["id"], "miniapp_payment_submitted", payment_id, req.model_dump_json())
    return {"ok": True, "payment_id": payment_id, "status": "pending"}


@router.get("/referral")
def referral(user=Depends(current_user)):
    stored = db.get_user(user["id"])
    return {"stats": db.referral_stats(user["id"]), "code": stored["referral_code"] if stored else None, "bot_username": os.getenv("BOT_USERNAME", "")}


class AccountChangeWrite(BaseModel):
    new_account_number: str = Field(min_length=3, max_length=32)
    broker: str | None = Field(None, max_length=128)
    server: str | None = Field(None, max_length=128)
    reason: str | None = Field(None, max_length=500)


@router.post("/autotrade/account-change", status_code=201)
def account_change(req: AccountChangeWrite, user=Depends(current_user)):
    try:
        row = db.request_mt5_account_change(user["id"], req.new_account_number, req.broker, req.server, req.reason)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    db.add_audit(user["id"], "miniapp_mt5_account_change", int(row["id"]), req.new_account_number)
    return dict(row)


class WaitlistWrite(BaseModel):
    active: bool


@router.put("/autotrade/waitlist")
def waitlist(req: WaitlistWrite, user=Depends(current_user)):
    (db.join_autotrade_waitlist if req.active else db.leave_autotrade_waitlist)(user["id"])
    return {"ok": True, "active": req.active}


class SupportWrite(BaseModel):
    subject: str = Field(min_length=2, max_length=160)
    message: str = Field(min_length=2, max_length=4000)
    priority: str = Field(default="NORMAL", pattern="^(LOW|NORMAL|HIGH|URGENT)$")


@router.get("/support")
def support(user=Depends(current_user)):
    with db.conn() as con:
        rows = con.execute("SELECT id,subject,message,priority,status,admin_reply,created_at,updated_at FROM support_tickets WHERE telegram_id=? ORDER BY id DESC", (user["id"],)).fetchall()
    return {"items": _rows(rows), "support_url": settings.support_url}


@router.post("/support", status_code=201)
def create_support(req: SupportWrite, user=Depends(current_user)):
    now = db.now_iso()
    with db.conn() as con:
        cur = con.execute("INSERT INTO support_tickets(telegram_id,subject,message,priority,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)", (user["id"], req.subject, req.message, req.priority, "OPEN", now, now))
    return {"id": cur.lastrowid, "ok": True}


@router.get("/admin/overview")
def admin_overview(user=Depends(admin_user)):
    with db.conn() as con:
        pending_changes = con.execute("SELECT COUNT(*) FROM autotrade_account_change_requests WHERE status='PENDING'").fetchone()[0]
    return {"dashboard": db.dashboard_stats(), "stats": db.stats(), "signal_stats": db.mt5_signal_stats(), "waitlist": db.autotrade_waitlist_count(), "account_changes": pending_changes}


@router.get("/admin/data")
def admin_data(user=Depends(admin_user)):
    with db.conn() as con:
        payments = con.execute("SELECT * FROM payments ORDER BY id DESC LIMIT 100").fetchall()
        users = con.execute("SELECT telegram_id,username,first_name,language,role,status,points_balance,created_at FROM users ORDER BY updated_at DESC LIMIT 200").fetchall()
        signals = con.execute("SELECT id,code,symbol,direction,status,destination,trailing_code,created_at FROM signals ORDER BY id DESC LIMIT 100").fetchall()
    return {"users": _rows(users), "payments": _rows(payments), "signals": _rows(signals), "plans": _rows(db.list_plans(active_only=False)), "discounts": _rows(db.list_discounts()), "campaigns": _rows(db.list_campaigns()), "account_changes": _rows(db.pending_mt5_account_change_requests()), "audit": _rows(db.recent_audits(100))}


class AdminUserAction(BaseModel):
    action: str = Field(pattern="^(ADD_POINTS|EXTEND|TRIAL|CANCEL|BLOCK|UNBLOCK)$")
    value: int = Field(default=30, ge=1, le=100000)


@router.post("/admin/users/{telegram_id}/action")
def admin_user_action(telegram_id: int, req: AdminUserAction, admin=Depends(admin_user)):
    if not db.get_user(telegram_id):
        raise HTTPException(404, "User not found")
    if req.action == "ADD_POINTS": db.add_points(telegram_id, req.value, "miniapp_admin", str(admin["id"]))
    elif req.action == "EXTEND": db.admin_extend_license(telegram_id, req.value, admin["id"])
    elif req.action == "TRIAL":
        if not db.grant_trial(telegram_id, min(req.value, 30), admin["id"]): raise HTTPException(409, "Trial already used")
    elif req.action == "CANCEL": db.cancel_active_license(telegram_id)
    else:
        with db.conn() as con: con.execute("UPDATE users SET status=?,updated_at=? WHERE telegram_id=?", ("BLOCKED" if req.action == "BLOCK" else "ACTIVE", db.now_iso(), telegram_id))
    db.add_audit(admin["id"], f"miniapp_{req.action.lower()}", telegram_id, f"value={req.value}")
    return {"ok": True}


class PaymentReview(BaseModel):
    approve: bool
    note: str | None = Field(None, max_length=500)


@router.post("/admin/payments/{payment_id}/review")
def review_payment(payment_id: int, req: PaymentReview, admin=Depends(admin_user)):
    pay = db.get_payment(payment_id)
    if not pay: raise HTTPException(404, "Payment not found")
    status = "approved" if req.approve else "rejected"
    if not db.review_payment(payment_id, status, admin["id"], req.note): raise HTTPException(409, "Payment already reviewed or invoice expired")
    if req.approve:
        license_service.activate_payment(pay)
        if db.has_entitlement(int(pay["telegram_id"]), "autotrade"):
            db.prepare_autotrade_license_pending(int(pay["telegram_id"]))
    else:
        if int(pay["points_used"] or 0): db.refund_points(pay["telegram_id"], int(pay["points_used"]), "payment_rejected_refund", str(payment_id))
        if pay["promo_code"]: db.release_discount_use(payment_id)
        if pay["campaign_id"]: db.release_campaign_use(payment_id)
    db.add_audit(admin["id"], f"miniapp_payment_{status}", int(pay["telegram_id"]), f"payment={payment_id}")
    return {"ok": True, "status": status, "notification_pending": True}


class AccountReview(BaseModel):
    approve: bool
    reason: str | None = Field(None, max_length=500)


@router.post("/admin/account-changes/{request_id}/review")
def review_account_change(request_id: int, req: AccountReview, admin=Depends(admin_user)):
    try: row = db.review_mt5_account_change(request_id, admin["id"], req.approve, req.reason)
    except ValueError as exc: raise HTTPException(409, str(exc)) from exc
    db.add_audit(admin["id"], "miniapp_mt5_account_review", request_id, str(row["status"]))
    return dict(row)


class TradeCommand(BaseModel):
    signal_id: int
    command: str = Field(pattern="^(CLOSE_SIGNAL|CANCEL_PENDING|MOVE_SL_TO_ENTRY|PARTIAL_CLOSE|UPDATE_SL|UPDATE_TP|ACTIVATE_TRAILING)$")
    value: str | None = Field(None, max_length=128)
    account_number: str | None = Field(None, max_length=32)


@router.post("/admin/trade-command", status_code=202)
def trade_command(req: TradeCommand, admin=Depends(admin_user)):
    command_id = db.create_autotrade_command(req.signal_id, req.command, {"value": req.value} if req.value else {}, actor_type="TELEGRAM_MINIAPP", actor_id=admin["id"], account_number=req.account_number)
    db.add_audit(admin["id"], "miniapp_trade_command", req.signal_id, f"{req.command}; command={command_id}")
    return {"id": command_id, "status": "QUEUED"}
