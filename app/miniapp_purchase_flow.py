from __future__ import annotations

import asyncio
import json
import mimetypes
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from aiogram import Bot
from aiogram.types import BufferedInputFile
from fastapi import APIRouter, Header, HTTPException, Query, Response
from pydantic import BaseModel, Field

from . import db
from .config import settings
from .miniapp_api import ReceiptRequest, _admin_markup, _auth_user, _decode_receipt
from .miniapp_product_intelligence import _ensure_schema as _ensure_product_schema
from .services import license_service
from .services.pricing_service import PricingError, create_invoice_quote, invoice_is_valid

router = APIRouter(prefix="/miniapp/api", tags=["NEXUS Mini App Purchase Flow"])

RECEIPT_DIR = Path(__file__).resolve().parent.parent / "data" / "miniapp_receipts"
MT_VALIDATOR_URL = os.getenv("NEXUS_MT_VALIDATOR_URL", "").strip()
MT_VALIDATOR_TOKEN = os.getenv("NEXUS_MT_VALIDATOR_TOKEN", "").strip()
MT5_TERMINAL_PATH = os.getenv("NEXUS_MT5_TERMINAL_PATH", "").strip()


class AdminReviewIn(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class AdminRejectIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class MetaAccountIn(BaseModel):
    payment_id: int = Field(gt=0)
    platform: str = Field(pattern="^(?:MT4|MT5)$")
    account_number: str = Field(min_length=3, max_length=20, pattern=r"^[0-9]+$")
    server: str = Field(min_length=2, max_length=160)
    investor_password: str = Field(min_length=1, max_length=256)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_schema() -> None:
    _ensure_product_schema()
    with db.conn() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS miniapp_receipt_files (
                payment_id INTEGER PRIMARY KEY,
                relative_path TEXT NOT NULL,
                mime_type TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(payment_id) REFERENCES payments(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS miniapp_meta_onboarding (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                payment_id INTEGER NOT NULL,
                license_id INTEGER,
                platform TEXT NOT NULL,
                account_number TEXT NOT NULL,
                server TEXT NOT NULL,
                broker TEXT,
                status TEXT NOT NULL DEFAULT 'PENDING',
                status_code TEXT,
                status_message_fa TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                validated_at TEXT,
                UNIQUE(telegram_id,payment_id),
                FOREIGN KEY(telegram_id) REFERENCES users(telegram_id),
                FOREIGN KEY(payment_id) REFERENCES payments(id),
                FOREIGN KEY(license_id) REFERENCES licenses(id)
            );
            CREATE INDEX IF NOT EXISTS idx_meta_onboarding_user
                ON miniapp_meta_onboarding(telegram_id,updated_at);
            CREATE INDEX IF NOT EXISTS idx_meta_onboarding_status
                ON miniapp_meta_onboarding(status,updated_at);
            """
        )


def _require_admin(init_data: str | None) -> int:
    uid = int(_auth_user(init_data)["id"])
    if uid not in settings.admin_ids:
        raise HTTPException(status_code=403, detail="دسترسی ادمین لازم است")
    return uid


def _plan_flags(plan_code: str) -> tuple[bool, bool]:
    plan = db.get_plan(str(plan_code))
    if plan is not None:
        keys = set(plan.keys())
        return bool(plan["vip_access"]) if "vip_access" in keys else True, bool(plan["autotrade_access"]) if "autotrade_access" in keys else False
    fallback = settings.plans.get(str(plan_code), {})
    return bool(fallback.get("vip_access", True)), bool(fallback.get("autotrade_access", False))


def _invoice_response(quote: dict[str, Any]) -> dict[str, Any]:
    method = str(quote["payment_method"])
    response: dict[str, Any] = {
        "invoice_id": int(quote["invoice_id"]),
        "plan": quote["plan"],
        "mode": quote["mode"],
        "payment_method": method,
        "total_usdt": str(quote["total_usdt"]),
        "final_amount_rial": quote["final_amount_rial"],
        "usdt_rial_rate": str(quote["usdt_rial_rate"]) if quote["usdt_rial_rate"] is not None else None,
        "expires_at": quote["expires_at"],
        "server_time": _now(),
        "timezone": settings.timezone,
    }
    if method == "usdt":
        response["payment"] = {"wallet": settings.usdt_wallet, "network": settings.usdt_network}
    else:
        response["payment"] = {"card": settings.payment_card, "owner": settings.payment_owner}
    return response


def _store_receipt(payment_id: int, content: bytes, filename: str) -> None:
    _ensure_schema()
    RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
    suffix = Path(filename).suffix.lower() or ".jpg"
    final = RECEIPT_DIR / f"payment-{int(payment_id)}{suffix}"
    temp = RECEIPT_DIR / f".payment-{int(payment_id)}{suffix}.tmp"
    temp.write_bytes(content)
    temp.replace(final)
    mime = mimetypes.guess_type(final.name)[0] or "image/jpeg"
    with db.conn() as con:
        con.execute(
            "INSERT OR REPLACE INTO miniapp_receipt_files(payment_id,relative_path,mime_type,size_bytes,created_at) VALUES(?,?,?,?,?)",
            (int(payment_id), final.name, mime, len(content), _now()),
        )


def _notification(uid: int, kind: str, title: str, body: str, destination: str = "account") -> None:
    _ensure_schema()
    with db.conn() as con:
        con.execute(
            "INSERT INTO miniapp_notifications(telegram_id,kind,title_fa,body_fa,destination,created_at) VALUES(?,?,?,?,?,?)",
            (int(uid), str(kind)[:40], str(title)[:160], str(body)[:500], str(destination)[:64], _now()),
        )


async def _telegram_notice(uid: int, text: str) -> None:
    bot = Bot(settings.bot_token)
    try:
        await bot.send_message(int(uid), text)
    except Exception:
        # Mini App notification remains the durable customer-facing source of truth.
        pass
    finally:
        await bot.session.close()


def _license_for_payment(uid: int, payment_id: int):
    with db.conn() as con:
        return con.execute(
            "SELECT * FROM licenses WHERE telegram_id=? AND payment_id=? ORDER BY id DESC LIMIT 1",
            (int(uid), int(payment_id)),
        ).fetchone()


def _license_payload(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    item = dict(row)
    return {
        "id": int(item["id"]),
        "plan_code": item.get("plan_code"),
        "license_key": item.get("license_key"),
        "status": item.get("status"),
        "starts_at": item.get("starts_at"),
        "expires_at": item.get("expires_at"),
        "vip_expires_at": item.get("vip_expires_at"),
        "autotrade_expires_at": item.get("autotrade_expires_at"),
        "vip_access": bool(item.get("vip_access")),
        "autotrade_access": bool(item.get("autotrade_access")),
    }


def _meta_payload(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    item = dict(row)
    return {
        "id": int(item["id"]),
        "platform": item.get("platform"),
        "account_number": item.get("account_number"),
        "server": item.get("server"),
        "broker": item.get("broker"),
        "status": item.get("status"),
        "status_code": item.get("status_code"),
        "message_fa": item.get("status_message_fa"),
        "updated_at": item.get("updated_at"),
        "validated_at": item.get("validated_at"),
    }


def _payment_payload(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    item = dict(row)
    vip, auto = _plan_flags(str(item.get("plan_code") or ""))
    return {
        "id": int(item["id"]),
        "plan_code": item.get("plan_code"),
        "status": str(item.get("status") or "").lower(),
        "payment_method": item.get("payment_method"),
        "amount_usdt": item.get("amount_usdt"),
        "amount_rial": item.get("amount_rial") or item.get("final_amount_irr"),
        "created_at": item.get("created_at"),
        "reviewed_at": item.get("reviewed_at"),
        "rejection_reason": item.get("admin_note") if str(item.get("status") or "").lower() == "rejected" else None,
        "vip_access": vip,
        "autotrade_access": auto,
        "requires_meta_account": auto,
    }


def _latest_payment(uid: int):
    with db.conn() as con:
        return con.execute("SELECT * FROM payments WHERE telegram_id=? ORDER BY id DESC LIMIT 1", (int(uid),)).fetchone()


def _purchase_context(uid: int, payment_id: int | None = None) -> dict[str, Any]:
    _ensure_schema()
    pay = db.get_payment(int(payment_id)) if payment_id else _latest_payment(uid)
    if pay is not None and int(pay["telegram_id"]) != int(uid):
        raise HTTPException(status_code=404, detail="پرداخت پیدا نشد")
    lic = _license_for_payment(uid, int(pay["id"])) if pay is not None and str(pay["status"]).lower() == "approved" else None
    meta = None
    if pay is not None:
        with db.conn() as con:
            meta = con.execute(
                "SELECT * FROM miniapp_meta_onboarding WHERE telegram_id=? AND payment_id=? LIMIT 1",
                (int(uid), int(pay["id"])),
            ).fetchone()
    payment = _payment_payload(pay)
    license_data = _license_payload(lic)
    meta_data = _meta_payload(meta)
    if not payment:
        next_step = "SELECT_PLAN"
    elif payment["status"] == "pending":
        next_step = "WAITING_PAYMENT_REVIEW"
    elif payment["status"] == "rejected":
        next_step = "RESUBMIT_RECEIPT"
    elif payment["status"] != "approved":
        next_step = "PAYMENT_ERROR"
    elif payment["requires_meta_account"] and (not meta_data or meta_data.get("status") != "VALID"):
        next_step = "META_ACCOUNT"
    else:
        next_step = "COMPLETE"
    return {
        "server_time": _now(),
        "timezone": settings.timezone,
        "is_admin": int(uid) in settings.admin_ids,
        "payment": payment,
        "license": license_data,
        "meta_account": meta_data,
        "next_step": next_step,
    }


async def _deliver_receipt_to_admins(payment_id: int, uid: int, plan_code: str, method: str, total_usdt: str, final_rial: int | None, tx_hash: str | None, image: bytes, filename: str) -> tuple[bool, str | None, int | None]:
    caption = (
        "🧾 NEXUS MINI APP PAYMENT\n\n"
        f"Payment ID: {payment_id}\nTelegram ID: {uid}\nPlan: {plan_code}\nMethod: {method.upper()}\nAmount: {total_usdt} USDT\n"
        + (f"Rial: {final_rial:,}\n" if final_rial else "")
        + (f"TX: {tx_hash}\n" if tx_hash else "")
        + "\nReceipt is also available in the Mini App admin review panel."
    )
    bot = Bot(settings.bot_token)
    sent = False
    first_file_id: str | None = None
    first_message_id: int | None = None
    try:
        for admin_id in settings.admin_ids:
            try:
                msg = await bot.send_photo(
                    chat_id=int(admin_id),
                    photo=BufferedInputFile(image, filename=filename),
                    caption=caption,
                    reply_markup=_admin_markup(payment_id),
                )
                sent = True
                if first_file_id is None and msg.photo:
                    first_file_id = msg.photo[-1].file_id
                    first_message_id = int(msg.message_id)
                with db.conn() as con:
                    con.execute(
                        "INSERT OR REPLACE INTO admin_receipts(payment_id,admin_id,message_id,created_at) VALUES(?,?,?,?)",
                        (int(payment_id), int(admin_id), int(msg.message_id), _now()),
                    )
            except Exception:
                continue
    finally:
        await bot.session.close()
    return sent, first_file_id, first_message_id


@router.post("/purchase/receipts")
async def submit_receipt_v4(payload: ReceiptRequest, x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data")) -> dict[str, Any]:
    uid = int(_auth_user(x_telegram_init_data)["id"])
    invoice = db.get_invoice(payload.invoice_id)
    if not invoice or int(invoice["user_id"]) != uid:
        raise HTTPException(status_code=404, detail="فاکتور پیدا نشد")
    if not invoice_is_valid(invoice):
        raise HTTPException(status_code=409, detail="اعتبار این فاکتور به پایان رسیده است")
    with db.conn() as con:
        existing = con.execute(
            "SELECT id,status FROM payments WHERE invoice_id=? AND telegram_id=? AND status IN ('pending','approved') ORDER BY id DESC LIMIT 1",
            (int(payload.invoice_id), uid),
        ).fetchone()
    if existing:
        return {"ok": True, "payment_id": int(existing["id"]), "status": str(existing["status"]), "duplicate": True, "context": _purchase_context(uid, int(existing["id"]))}

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
            receipt_file_id=f"miniappv4:{payload.invoice_id}:pending",
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

    _store_receipt(payment_id, image, filename)
    delivered, file_id, message_id = await _deliver_receipt_to_admins(payment_id, uid, plan_code, method, total_usdt, final_rial, tx_hash, image, filename)
    with db.conn() as con:
        con.execute(
            "UPDATE payments SET receipt_file_id=?,receipt_message_id=?,admin_note=? WHERE id=?",
            (file_id or f"miniappv4:{payload.invoice_id}", message_id, None if delivered else "Receipt saved; Telegram admin delivery unavailable", int(payment_id)),
        )
    _notification(uid, "PAYMENT_PENDING", "رسید شما ثبت شد", "رسید برای بررسی ادمین ارسال شد. نتیجه بررسی داخل NEXUS اعلام می‌شود.", "account")
    return {"ok": True, "payment_id": int(payment_id), "status": "pending", "admin_delivery": delivered, "context": _purchase_context(uid, payment_id)}


@router.get("/purchase/status")
def purchase_status(payment_id: int | None = Query(default=None, gt=0), x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data")) -> dict[str, Any]:
    uid = int(_auth_user(x_telegram_init_data)["id"])
    return _purchase_context(uid, payment_id)


@router.post("/purchase/payments/{payment_id}/retry")
async def retry_payment(payment_id: int, x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data")) -> dict[str, Any]:
    uid = int(_auth_user(x_telegram_init_data)["id"])
    pay = db.get_payment(payment_id)
    if not pay or int(pay["telegram_id"]) != uid:
        raise HTTPException(status_code=404, detail="پرداخت پیدا نشد")
    if str(pay["status"]).lower() != "rejected":
        raise HTTPException(status_code=409, detail="فقط رسید ردشده قابل ارسال مجدد است")
    method = "rial" if str(pay["payment_method"] or "").lower() in {"irr", "rial"} else "usdt"
    try:
        quote = await create_invoice_quote(uid, str(pay["plan_code"]).upper(), method)
    except PricingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _invoice_response(quote)


@router.get("/admin/purchase/payments")
def admin_payments(status: str = Query(default="pending"), limit: int = Query(default=30, ge=1, le=100), x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data")) -> dict[str, Any]:
    _require_admin(x_telegram_init_data)
    _ensure_schema()
    key = str(status or "pending").lower()
    if key not in {"pending", "approved", "rejected", "all"}:
        raise HTTPException(status_code=400, detail="وضعیت پرداخت نامعتبر است")
    where = "" if key == "all" else "WHERE p.status=?"
    args: tuple[Any, ...] = () if key == "all" else (key,)
    with db.conn() as con:
        rows = con.execute(
            f"""
            SELECT p.*,u.username,u.first_name,
                   CASE WHEN rf.payment_id IS NULL THEN 0 ELSE 1 END AS has_receipt_file
            FROM payments p
            LEFT JOIN users u ON u.telegram_id=p.telegram_id
            LEFT JOIN miniapp_receipt_files rf ON rf.payment_id=p.id
            {where}
            ORDER BY CASE p.status WHEN 'pending' THEN 0 ELSE 1 END,p.created_at ASC
            LIMIT ?
            """,
            (*args, int(limit)),
        ).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        items.append({
            **_payment_payload(row),
            "telegram_id": int(item["telegram_id"]),
            "username": item.get("username"),
            "first_name": item.get("first_name"),
            "price_label": item.get("price_label"),
            "transaction_hash": item.get("transaction_hash") or item.get("txid"),
            "admin_note": item.get("admin_note"),
            "has_receipt_file": bool(item.get("has_receipt_file")),
        })
    return {"items": items, "server_time": _now(), "timezone": settings.timezone}


@router.get("/admin/purchase/payments/{payment_id}/receipt")
def admin_payment_receipt(payment_id: int, x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data")) -> Response:
    _require_admin(x_telegram_init_data)
    _ensure_schema()
    with db.conn() as con:
        row = con.execute("SELECT relative_path,mime_type FROM miniapp_receipt_files WHERE payment_id=?", (int(payment_id),)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="تصویر رسید در سرور پیدا نشد")
    path = RECEIPT_DIR / Path(str(row["relative_path"])).name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="فایل رسید در سرور پیدا نشد")
    return Response(content=path.read_bytes(), media_type=str(row["mime_type"] or "image/jpeg"), headers={"Cache-Control": "private, no-store"})


@router.post("/admin/purchase/payments/{payment_id}/approve")
async def admin_approve_payment(payment_id: int, payload: AdminReviewIn, x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data")) -> dict[str, Any]:
    admin_id = _require_admin(x_telegram_init_data)
    pay = db.get_payment(payment_id)
    if not pay:
        raise HTTPException(status_code=404, detail="پرداخت پیدا نشد")
    if not db.review_payment(payment_id, "approved", admin_id, payload.note):
        raise HTTPException(status_code=409, detail="این پرداخت قبلاً بررسی شده است")
    try:
        lic = license_service.activate_payment(pay)
        vip, auto = _plan_flags(str(pay["plan_code"]))
        if auto:
            db.prepare_autotrade_license_pending(int(pay["telegram_id"]))
            lic = _license_for_payment(int(pay["telegram_id"]), payment_id) or lic
    except Exception as exc:
        with db.conn() as con:
            con.execute("UPDATE payments SET admin_note=COALESCE(admin_note,'') || ? WHERE id=?", (f" | LICENSE_ACTIVATION_ERROR:{type(exc).__name__}", int(payment_id)))
        raise HTTPException(status_code=500, detail="پرداخت تأیید شد اما فعال‌سازی لایسنس با خطا مواجه شد؛ نیاز به بررسی ادمین دارد") from exc

    uid = int(pay["telegram_id"])
    vip, auto = _plan_flags(str(pay["plan_code"]))
    if auto:
        body = "پرداخت تأیید شد. اشتراک فعال است؛ برای صدور لایسنس AutoTrade اطلاعات حساب MT5 را داخل Mini App تکمیل کنید."
    elif vip:
        body = "پرداخت تأیید شد و دسترسی VIP شما فعال گردید. جزئیات لایسنس در حساب من قابل مشاهده است."
    else:
        body = "پرداخت تأیید شد و اشتراک شما فعال گردید."
    _notification(uid, "PAYMENT_APPROVED", "پرداخت تأیید شد", body, "account")
    await _telegram_notice(uid, f"✅ NEXUS\n\n{body}")
    db.add_audit(admin_id, "miniapp_approve_payment", uid, f"payment_id={payment_id}")
    return {"ok": True, "context": _purchase_context(uid, payment_id)}


@router.post("/admin/purchase/payments/{payment_id}/reject")
async def admin_reject_payment(payment_id: int, payload: AdminRejectIn, x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data")) -> dict[str, Any]:
    admin_id = _require_admin(x_telegram_init_data)
    pay = db.get_payment(payment_id)
    if not pay:
        raise HTTPException(status_code=404, detail="پرداخت پیدا نشد")
    reason = payload.reason.strip()
    if not db.review_payment(payment_id, "rejected", admin_id, reason):
        raise HTTPException(status_code=409, detail="این پرداخت قبلاً بررسی شده است")
    keys = set(pay.keys())
    if "points_used" in keys and int(pay["points_used"] or 0) > 0:
        db.refund_points(int(pay["telegram_id"]), int(pay["points_used"]), "payment_rejected_refund", str(payment_id))
    if "promo_code" in keys and pay["promo_code"]:
        db.release_discount_use(payment_id)
    try:
        db.release_campaign_use(payment_id)
    except Exception:
        pass
    uid = int(pay["telegram_id"])
    body = f"رسید پرداخت رد شد. دلیل: {reason} برای ارسال مجدد رسید، وضعیت پرداخت را در Mini App باز کنید."
    _notification(uid, "PAYMENT_REJECTED", "رسید پرداخت رد شد", body, "account")
    await _telegram_notice(uid, f"❌ NEXUS\n\n{body}")
    db.add_audit(admin_id, "miniapp_reject_payment", uid, f"payment_id={payment_id};reason={reason[:120]}")
    return {"ok": True, "context": _purchase_context(uid, payment_id)}


async def _remote_validate(platform: str, account_number: str, server: str, password: str) -> dict[str, Any] | None:
    if not MT_VALIDATOR_URL:
        return None
    headers = {"Content-Type": "application/json"}
    if MT_VALIDATOR_TOKEN:
        headers["Authorization"] = f"Bearer {MT_VALIDATOR_TOKEN}"
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=8.0)) as client:
        response = await client.post(
            MT_VALIDATOR_URL,
            headers=headers,
            json={"platform": platform, "account_number": account_number, "server": server, "investor_password": password},
        )
    if response.status_code >= 400:
        return {"ok": False, "code": f"VALIDATOR_HTTP_{response.status_code}", "message_fa": "سرویس بررسی حساب اتصال را تأیید نکرد."}
    try:
        data = response.json()
    except json.JSONDecodeError:
        return {"ok": False, "code": "VALIDATOR_BAD_RESPONSE", "message_fa": "پاسخ سرویس بررسی حساب معتبر نبود."}
    return {
        "ok": bool(data.get("ok")),
        "code": str(data.get("code") or ("VALID" if data.get("ok") else "INVALID_CREDENTIALS")),
        "message_fa": str(data.get("message_fa") or ("اتصال حساب با موفقیت تأیید شد." if data.get("ok") else "اطلاعات حساب تأیید نشد.")),
        "broker": str(data.get("broker") or "") or None,
        "autotrade_compatible": bool(data.get("autotrade_compatible", platform == "MT5")),
    }


def _local_mt5_validate(account_number: str, server: str, password: str) -> dict[str, Any] | None:
    try:
        import MetaTrader5 as mt5  # type: ignore
    except Exception:
        return None
    kwargs: dict[str, Any] = {"login": int(account_number), "password": password, "server": server}
    if MT5_TERMINAL_PATH:
        kwargs["path"] = MT5_TERMINAL_PATH
    initialized = False
    try:
        initialized = bool(mt5.initialize(**kwargs))
        if not initialized:
            err = mt5.last_error()
            return {"ok": False, "code": "MT5_LOGIN_FAILED", "message_fa": f"اتصال MT5 تأیید نشد. کد خطا: {err[0] if err else 'unknown'}"}
        info = mt5.account_info()
        if info is None or int(getattr(info, "login", 0) or 0) != int(account_number):
            return {"ok": False, "code": "MT5_ACCOUNT_MISMATCH", "message_fa": "شماره حساب پاسخ‌داده‌شده با اطلاعات واردشده مطابقت ندارد."}
        return {
            "ok": True,
            "code": "VALID",
            "message_fa": "اتصال MetaTrader 5 با موفقیت تأیید شد.",
            "broker": str(getattr(info, "company", "") or "") or None,
            "autotrade_compatible": True,
        }
    finally:
        if initialized:
            try:
                mt5.shutdown()
            except Exception:
                pass


async def _validate_meta(platform: str, account_number: str, server: str, password: str) -> dict[str, Any]:
    remote = await _remote_validate(platform, account_number, server, password)
    if remote is not None:
        return remote
    if platform == "MT5":
        local = await asyncio.to_thread(_local_mt5_validate, account_number, server, password)
        if local is not None:
            return local
        return {"ok": False, "code": "MT5_VALIDATOR_UNAVAILABLE", "message_fa": "ماژول بررسی MT5 روی سرور فعال نیست. تنظیمات Validator یا MetaTrader5 را تکمیل کنید."}
    return {"ok": False, "code": "MT4_BRIDGE_REQUIRED", "message_fa": "برای اعتبارسنجی MT4 باید Bridge امن NEXUS_MT_VALIDATOR_URL روی سرور تنظیم شود."}


@router.post("/purchase/meta-account")
async def meta_account(payload: MetaAccountIn, x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data")) -> dict[str, Any]:
    uid = int(_auth_user(x_telegram_init_data)["id"])
    _ensure_schema()
    pay = db.get_payment(payload.payment_id)
    if not pay or int(pay["telegram_id"]) != uid:
        raise HTTPException(status_code=404, detail="پرداخت پیدا نشد")
    if str(pay["status"]).lower() != "approved":
        raise HTTPException(status_code=409, detail="ابتدا باید پرداخت توسط ادمین تأیید شود")
    vip, auto = _plan_flags(str(pay["plan_code"]))
    if not auto:
        raise HTTPException(status_code=409, detail="برای پلن VIP-only ثبت رمز MetaTrader لازم نیست")
    lic = _license_for_payment(uid, payload.payment_id)
    if lic is None:
        raise HTTPException(status_code=409, detail="لایسنس فعال پرداخت پیدا نشد")

    now = _now()
    with db.conn() as con:
        con.execute(
            """
            INSERT INTO miniapp_meta_onboarding(telegram_id,payment_id,license_id,platform,account_number,server,status,status_code,status_message_fa,created_at,updated_at)
            VALUES(?,?,?,?,?,?,'VALIDATING','VALIDATING','در حال بررسی اتصال حساب...',?,?)
            ON CONFLICT(telegram_id,payment_id) DO UPDATE SET
                license_id=excluded.license_id,platform=excluded.platform,account_number=excluded.account_number,server=excluded.server,
                broker=NULL,status='VALIDATING',status_code='VALIDATING',status_message_fa='در حال بررسی اتصال حساب...',updated_at=excluded.updated_at,validated_at=NULL
            """,
            (uid, payload.payment_id, int(lic["id"]), payload.platform, payload.account_number, payload.server.strip(), now, now),
        )

    result = await _validate_meta(payload.platform, payload.account_number, payload.server.strip(), payload.investor_password)
    ok = bool(result.get("ok"))
    if ok and auto and not bool(result.get("autotrade_compatible", payload.platform == "MT5")):
        ok = False
        result = {"ok": False, "code": "PLATFORM_NOT_AUTOTRADE_COMPATIBLE", "message_fa": "حساب تأیید شد اما Validator این اتصال را برای AutoTrade سازگار اعلام نکرد."}

    status = "VALID" if ok else "INVALID"
    with db.conn() as con:
        con.execute(
            "UPDATE miniapp_meta_onboarding SET broker=?,status=?,status_code=?,status_message_fa=?,updated_at=?,validated_at=? WHERE telegram_id=? AND payment_id=?",
            (result.get("broker"), status, result.get("code"), result.get("message_fa"), _now(), _now() if ok else None, uid, payload.payment_id),
        )

    if not ok:
        return {"ok": False, "validation": result, "context": _purchase_context(uid, payload.payment_id)}

    if payload.platform == "MT5":
        try:
            current = _license_for_payment(uid, payload.payment_id)
            if current is not None and not str(current["license_key"] or "").strip():
                db.issue_autotrade_license_for_account(uid, payload.account_number, result.get("broker"), payload.server.strip())
        except ValueError as exc:
            with db.conn() as con:
                con.execute(
                    "UPDATE miniapp_meta_onboarding SET status='INVALID',status_code='LICENSE_BIND_FAILED',status_message_fa=?,updated_at=? WHERE telegram_id=? AND payment_id=?",
                    (f"اتصال تأیید شد اما صدور لایسنس انجام نشد: {str(exc)}", _now(), uid, payload.payment_id),
                )
            return {"ok": False, "validation": {"ok": False, "code": "LICENSE_BIND_FAILED", "message_fa": "اتصال تأیید شد اما صدور لایسنس نیاز به بررسی دارد."}, "context": _purchase_context(uid, payload.payment_id)}
    else:
        # Current NEXUS AutoTrade execution runtime is MT5-centric. MT4 can only
        # complete if the configured remote bridge is extended to issue/bind the
        # matching execution license; never fabricate a usable MT4 key here.
        with db.conn() as con:
            con.execute(
                "UPDATE miniapp_meta_onboarding SET status='INVALID',status_code='MT4_EXECUTION_BRIDGE_REQUIRED',status_message_fa=?,updated_at=? WHERE telegram_id=? AND payment_id=?",
                ("اعتبار حساب MT4 تأیید شد، اما Runtime فعلی AutoTrade برای صدور لایسنس اجرایی MT4 به Bridge اختصاصی نیاز دارد.", _now(), uid, payload.payment_id),
            )
        return {"ok": False, "validation": {"ok": False, "code": "MT4_EXECUTION_BRIDGE_REQUIRED", "message_fa": "اعتبار حساب MT4 تأیید شد اما Bridge اجرایی MT4 هنوز تنظیم نشده است."}, "context": _purchase_context(uid, payload.payment_id)}

    _notification(uid, "LICENSE_ISSUED", "لایسنس NEXUS صادر شد", "اتصال MT5 تأیید شد و لایسنس AutoTrade شما آماده استفاده است.", "account")
    await _telegram_notice(uid, "✅ NEXUS\n\nاتصال MT5 تأیید شد و لایسنس AutoTrade شما صادر گردید. جزئیات در بخش حساب من قابل مشاهده است.")
    db.add_audit(uid, "miniapp_mt5_validated_license_issued", int(lic["id"]), f"account={payload.account_number};server={payload.server[:80]}")
    return {"ok": True, "validation": result, "context": _purchase_context(uid, payload.payment_id)}
