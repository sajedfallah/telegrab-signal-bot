from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qsl

from aiogram import Bot
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from . import db
from .config import settings
from .services.pricing_service import PricingError, create_invoice_quote, invoice_is_valid

router = APIRouter(prefix="/miniapp/api", tags=["NEXUS Mini App"])

MAX_INIT_DATA_AGE = max(60, int(os.getenv("MINIAPP_AUTH_MAX_AGE_SECONDS", "86400")))
MAX_RECEIPT_BYTES = max(250_000, min(int(os.getenv("MINIAPP_MAX_RECEIPT_BYTES", "5000000")), 8_000_000))
BOT_USERNAME = os.getenv("BOT_USERNAME", "").strip().lstrip("@")


class InvoiceRequest(BaseModel):
    plan_code: str = Field(min_length=2, max_length=32)
    payment_method: str = Field(pattern="^(?:usdt|rial)$")


class ReceiptRequest(BaseModel):
    invoice_id: int = Field(gt=0)
    image_data_url: str = Field(min_length=32, max_length=8_000_000)
    transaction_hash: str | None = Field(default=None, max_length=256)


class LanguageRequest(BaseModel):
    language: str = Field(pattern="^(?:fa|en)$")


def _row(row) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def _validate_init_data(init_data: str) -> dict[str, Any]:
    raw = str(init_data or "").strip()
    if not raw:
        raise HTTPException(status_code=401, detail="missing Telegram initData")
    try:
        pairs = parse_qsl(raw, keep_blank_values=True, strict_parsing=True)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="invalid Telegram initData") from exc
    if not pairs or len({k for k, _ in pairs}) != len(pairs):
        raise HTTPException(status_code=401, detail="invalid Telegram initData")
    data = dict(pairs)
    received_hash = str(data.pop("hash", ""))
    if not received_hash:
        raise HTTPException(status_code=401, detail="Telegram initData hash is missing")

    check_string = "\n".join(f"{key}={data[key]}" for key in sorted(data))
    secret_key = hmac.new(b"WebAppData", settings.bot_token.encode("utf-8"), hashlib.sha256).digest()
    calculated = hmac.new(secret_key, check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated, received_hash):
        raise HTTPException(status_code=401, detail="Telegram initData signature is invalid")

    try:
        auth_date = int(data.get("auth_date", "0"))
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Telegram auth_date is invalid") from exc
    now = int(time.time())
    if auth_date <= 0 or auth_date > now + 60 or now - auth_date > MAX_INIT_DATA_AGE:
        raise HTTPException(status_code=401, detail="Telegram initData has expired")

    try:
        user = json.loads(data.get("user", "{}"))
        user_id = int(user["id"])
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=401, detail="Telegram user is missing from initData") from exc
    if user_id <= 0:
        raise HTTPException(status_code=401, detail="Telegram user id is invalid")
    return user


def _auth_user(x_telegram_init_data: str | None) -> dict[str, Any]:
    user = _validate_init_data(x_telegram_init_data or "")
    uid = int(user["id"])
    db.upsert_user(uid, user.get("username"), user.get("first_name"))
    return user


def _entitlements(uid: int) -> dict[str, Any]:
    data = dict(db.current_entitlements(uid))
    lic = db.active_license(uid)
    data["license_key"] = str(lic["license_key"] or "") if lic and bool(data.get("autotrade")) else ""
    return data


def _plans() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for code, plan in (db.plan_map(active_only=True) or settings.plans).items():
        vip = bool(plan.get("vip_access"))
        auto = bool(plan.get("autotrade_access"))
        if vip and auto:
            category = "bundle"
        elif auto:
            category = "autotrade"
        else:
            category = "vip"
        raw_price = str(plan.get("price_usdt", plan.get("usdt", "0"))).strip()
        try:
            price = float(raw_price)
        except ValueError:
            continue
        if price <= 0:
            continue
        result.append({
            "code": str(code),
            "title_fa": str(plan.get("fa") or code),
            "title_en": str(plan.get("en") or code),
            "days": int(plan.get("duration_days") or plan.get("days") or 0),
            "price_usdt": raw_price,
            "setup_fee_usdt": str(plan.get("setup_fee_usdt", "0")),
            "setup_fee_discount_percent": float(plan.get("setup_fee_discount_percent", 0) or 0),
            "renewal_discount_percent": float(plan.get("renewal_discount_percent", 0) or 0),
            "vip_access": vip,
            "autotrade_access": auto,
            "category": category,
        })
    return result


def _autotrade(uid: int) -> dict[str, Any]:
    ent = _entitlements(uid)
    with db.conn() as con:
        mt5 = con.execute(
            "SELECT account_number,broker,server,status,ea_version,bound_at,last_seen_at "
            "FROM autotrade_mt5_accounts WHERE telegram_id=? LIMIT 1", (uid,),
        ).fetchone()
        exchange = con.execute(
            "SELECT exchange,account_label,status,bound_at,last_seen_at "
            "FROM autotrade_exchange_accounts WHERE telegram_id=? LIMIT 1", (uid,),
        ).fetchone()
        history = con.execute(
            "SELECT id,ticket,event_type,symbol,direction,volume,entry_price,exit_price,profit,status,created_at "
            "FROM autotrade_trade_executions WHERE telegram_id=? ORDER BY id DESC LIMIT 20", (uid,),
        ).fetchall()
    positions: list[dict[str, Any]] = []
    orders: list[dict[str, Any]] = []
    if mt5 and mt5["account_number"]:
        try:
            positions = db.mt5_live_positions(str(mt5["account_number"]), nexus_only=True)
            orders = db.mt5_live_orders(str(mt5["account_number"]), nexus_only=True)
        except Exception:
            positions, orders = [], []
    return {
        "entitled": bool(ent.get("autotrade")),
        "expires_at": ent.get("autotrade_expires_at"),
        "license_key": ent.get("license_key") or "",
        "mt5": _row(mt5),
        "exchange": _row(exchange),
        "open_positions": positions,
        "pending_orders": orders,
        "history": [dict(r) for r in history],
    }


def _payments(uid: int, limit: int = 20) -> list[dict[str, Any]]:
    return [dict(r) for r in db.user_payments(uid, "all", limit=max(1, min(limit, 50)))]


def _referral(uid: int) -> dict[str, Any]:
    user = db.get_user(uid)
    stats = db.referral_stats(uid)
    code = str(user["referral_code"] or "") if user else ""
    url = f"https://t.me/{BOT_USERNAME}?start=ref_{code}" if BOT_USERNAME and code else ""
    return {**stats, "code": code, "url": url}


def _admin_markup(payment_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ تأیید", callback_data=f"payok:{payment_id}"),
        InlineKeyboardButton(text="❌ رد", callback_data=f"payno:{payment_id}"),
    ]])


def _decode_receipt(data_url: str) -> tuple[bytes, str]:
    if "," not in data_url:
        raise HTTPException(status_code=400, detail="receipt image is invalid")
    meta, encoded = data_url.split(",", 1)
    meta = meta.lower()
    allowed = {
        "data:image/jpeg;base64": "receipt.jpg",
        "data:image/jpg;base64": "receipt.jpg",
        "data:image/png;base64": "receipt.png",
        "data:image/webp;base64": "receipt.webp",
    }
    filename = allowed.get(meta)
    if not filename:
        raise HTTPException(status_code=400, detail="receipt must be JPG, PNG or WEBP")
    try:
        content = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=400, detail="receipt image encoding is invalid") from exc
    if not content or len(content) > MAX_RECEIPT_BYTES:
        raise HTTPException(status_code=413, detail="receipt image is too large")
    return content, filename


@router.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "service": "nexus-miniapp", "version": "1.0"}


@router.get("/bootstrap")
def bootstrap(x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data")) -> dict[str, Any]:
    tg_user = _auth_user(x_telegram_init_data)
    uid = int(tg_user["id"])
    user = db.get_user(uid)
    ent = _entitlements(uid)
    return {
        "user": {
            "id": uid,
            "first_name": tg_user.get("first_name") or (user["first_name"] if user else ""),
            "last_name": tg_user.get("last_name") or "",
            "username": tg_user.get("username") or (user["username"] if user else ""),
            "language": str(user["language"] or "fa") if user else "fa",
            "level": db.user_level(uid),
        },
        "entitlements": ent,
        "plans": _plans(),
        "payments": _payments(uid, 10),
        "referral": _referral(uid),
        "autotrade": _autotrade(uid),
        "links": {
            "public_channel": settings.public_channel_url,
            "free_signals": settings.free_channel_url,
            "support": settings.support_url,
            "autotrade_channel": settings.autotrade_channel_url,
            "guide_intro": settings.guide_intro_video_url,
            "guide_mt5": settings.guide_mt5_video_url,
        },
    }


@router.get("/plans")
def plans(x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data")) -> dict[str, Any]:
    _auth_user(x_telegram_init_data)
    return {"plans": _plans()}


@router.get("/payments")
def payments(x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data")) -> dict[str, Any]:
    uid = int(_auth_user(x_telegram_init_data)["id"])
    return {"payments": _payments(uid, 30)}


@router.get("/autotrade")
def autotrade(x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data")) -> dict[str, Any]:
    uid = int(_auth_user(x_telegram_init_data)["id"])
    return _autotrade(uid)


@router.post("/language")
def set_language(payload: LanguageRequest, x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data")) -> dict[str, Any]:
    uid = int(_auth_user(x_telegram_init_data)["id"])
    db.set_language(uid, payload.language)
    return {"ok": True, "language": payload.language}


@router.post("/invoices")
async def create_invoice(payload: InvoiceRequest, x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data")) -> dict[str, Any]:
    uid = int(_auth_user(x_telegram_init_data)["id"])
    try:
        quote = await create_invoice_quote(uid, payload.plan_code.upper(), payload.payment_method)
    except PricingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    response = {
        "invoice_id": int(quote["invoice_id"]),
        "plan": quote["plan"],
        "mode": quote["mode"],
        "payment_method": quote["payment_method"],
        "total_usdt": str(quote["total_usdt"]),
        "final_amount_rial": quote["final_amount_rial"],
        "usdt_rial_rate": str(quote["usdt_rial_rate"]) if quote["usdt_rial_rate"] is not None else None,
        "expires_at": quote["expires_at"],
    }
    if payload.payment_method == "usdt":
        response["payment"] = {"wallet": settings.usdt_wallet, "network": settings.usdt_network}
    else:
        response["payment"] = {"card": settings.payment_card, "owner": settings.payment_owner}
    return response


@router.post("/receipts")
async def submit_receipt(payload: ReceiptRequest, x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data")) -> dict[str, Any]:
    uid = int(_auth_user(x_telegram_init_data)["id"])
    invoice = db.get_invoice(payload.invoice_id)
    if not invoice or int(invoice["user_id"]) != uid:
        raise HTTPException(status_code=404, detail="invoice not found")
    if not invoice_is_valid(invoice):
        raise HTTPException(status_code=409, detail="invoice is no longer payable")
    with db.conn() as con:
        existing = con.execute(
            "SELECT id,status FROM payments WHERE invoice_id=? AND telegram_id=? AND status IN ('pending','approved') ORDER BY id DESC LIMIT 1",
            (payload.invoice_id, uid),
        ).fetchone()
    if existing:
        return {"ok": True, "payment_id": int(existing["id"]), "status": str(existing["status"]), "duplicate": True}

    image, filename = _decode_receipt(payload.image_data_url)
    plan_code = str(invoice["code"])
    days = int(invoice["days"] or 0)
    method = str(invoice["payment_method"])
    total_usdt = str(invoice["base_amount_usdt"] or "0")
    final_rial = int(invoice["final_amount_rial"] or 0) if invoice["final_amount_rial"] is not None else None
    tx_hash = str(payload.transaction_hash or "").strip().lower() or None
    try:
        payment_id = db.create_payment(
            telegram_id=uid,
            plan_code=plan_code,
            days=days,
            price_label=(f"{total_usdt} USDT" if method == "usdt" else f"{final_rial or 0:,} IRR"),
            payment_method=("irr" if method == "rial" else "usdt"),
            receipt_file_id=f"miniapp:{payload.invoice_id}:pending",
            receipt_type="photo",
            final_amount_irr=final_rial,
            txid=tx_hash,
            invoice_id=int(invoice["id"]),
            amount_usdt=total_usdt,
            amount_rial=final_rial,
            transaction_hash=tx_hash,
            payment_reference=f"MINIAPP-{payload.invoice_id}",
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    caption = (
        "🧾 NEXUS MINI APP PAYMENT\n\n"
        f"Payment ID: {payment_id}\n"
        f"Telegram ID: {uid}\n"
        f"Plan: {plan_code}\n"
        f"Method: {method.upper()}\n"
        f"Amount: {total_usdt} USDT\n"
        + (f"Rial: {final_rial:,}\n" if final_rial else "")
        + (f"TX: {tx_hash}\n" if tx_hash else "")
    )
    bot = Bot(settings.bot_token)
    sent_any = False
    first_file_id = ""
    first_message_id: int | None = None
    errors: list[str] = []
    try:
        for admin_id in settings.admin_ids:
            try:
                msg = await bot.send_photo(
                    chat_id=admin_id,
                    photo=BufferedInputFile(image, filename=filename),
                    caption=caption,
                    reply_markup=_admin_markup(payment_id),
                )
                sent_any = True
                if not first_file_id and msg.photo:
                    first_file_id = msg.photo[-1].file_id
                    first_message_id = int(msg.message_id)
                with db.conn() as con:
                    con.execute(
                        "INSERT OR REPLACE INTO admin_receipts(payment_id,admin_id,message_id,created_at) VALUES(?,?,?,?)",
                        (payment_id, int(admin_id), int(msg.message_id), db.now_iso()),
                    )
            except Exception as exc:
                errors.append(f"{admin_id}:{type(exc).__name__}")
    finally:
        await bot.session.close()

    with db.conn() as con:
        if sent_any:
            con.execute(
                "UPDATE payments SET receipt_file_id=?,receipt_message_id=? WHERE id=?",
                (first_file_id or f"miniapp:{payload.invoice_id}", first_message_id, payment_id),
            )
        else:
            con.execute(
                "UPDATE payments SET status='failed',admin_note=? WHERE id=?",
                ("Mini App admin delivery failed: " + ",".join(errors[:5]), payment_id),
            )
    if not sent_any:
        raise HTTPException(status_code=503, detail="receipt saved but admin delivery failed; retry is allowed")
    return {"ok": True, "payment_id": payment_id, "status": "pending"}


@router.post("/vip/access-link")
async def vip_access_link(x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data")) -> dict[str, Any]:
    uid = int(_auth_user(x_telegram_init_data)["id"])
    if not db.has_entitlement(uid, "vip"):
        raise HTTPException(status_code=403, detail="active VIP subscription is required")
    bot = Bot(settings.bot_token)
    try:
        link = await bot.create_chat_invite_link(
            chat_id=settings.vip_channel_id,
            expire_date=datetime.now(timezone.utc) + timedelta(minutes=10),
            member_limit=1,
            name=f"NEXUS MiniApp {uid}",
        )
        return {"url": link.invite_link, "expires_in_seconds": 600}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="VIP access link could not be created") from exc
    finally:
        await bot.session.close()
