from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from . import db
from .autotrade import risk_firewall
from .config import settings

router = APIRouter(prefix="/api/v1/admin-web", tags=["admin-web"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _secret() -> bytes:
    value = os.getenv("ADMIN_WEB_SECRET", "").strip()
    if len(value) < 32:
        # Local-only deterministic fallback. Production deployment validation
        # must require a strong ADMIN_WEB_SECRET before public exposure.
        value = f"local-only:{db.DB_PATH.resolve()}:{settings.nexus_admin_token}"
    return hashlib.sha256(value.encode("utf-8")).digest()


def _password_hash(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 310_000)
    return (
        "pbkdf2_sha256$310000$"
        + base64.urlsafe_b64encode(salt).decode("ascii")
        + "$"
        + base64.urlsafe_b64encode(digest).decode("ascii")
    )


def _password_ok(password: str, encoded: str) -> bool:
    try:
        _, rounds, salt, expected = encoded.split("$", 3)
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            base64.urlsafe_b64decode(salt),
            int(rounds),
        )
        actual = base64.urlsafe_b64encode(digest).decode("ascii")
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def init_admin_schema() -> None:
    """Create only web-auth state.

    Risk, license, payment and signal business state deliberately remain in the
    existing NEXUS production services/tables. This prevents the web panel from
    becoming a second source of truth.
    """
    with db.conn() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS web_admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                display_name TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'ADMIN',
                active INTEGER NOT NULL DEFAULT 1,
                failed_attempts INTEGER NOT NULL DEFAULT 0,
                locked_until TEXT,
                last_login_at TEXT,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_web_admins_username
                ON web_admins(username);
            """
        )
        username = os.getenv("ADMIN_WEB_USERNAME", "admin").strip() or "admin"
        password = os.getenv("ADMIN_WEB_PASSWORD", "").strip()
        exists = con.execute("SELECT 1 FROM web_admins LIMIT 1").fetchone()
        if not exists and len(password) >= 12 and "CHANGE_ME" not in password.upper():
            con.execute(
                "INSERT INTO web_admins(username,password_hash,display_name,role,created_at) VALUES(?,?,?,?,?)",
                (username, _password_hash(password), "مدیر سیستم", "ADMIN", db.now_iso()),
            )


def _encode_token(*, subject: int, scope: str, role: str | None = None, ttl_seconds: int) -> str:
    payload: dict[str, Any] = {
        "sub": int(subject),
        "scope": scope,
        "exp": int(time.time()) + int(ttl_seconds),
        "nonce": secrets.token_hex(8),
    }
    if role:
        payload["role"] = role
    raw = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")
    sig = base64.urlsafe_b64encode(
        hmac.new(_secret(), raw.encode("ascii"), hashlib.sha256).digest()
    ).decode("ascii").rstrip("=")
    return f"{raw}.{sig}"


def _decode_token(token: str, *, expected_scope: str) -> dict[str, Any]:
    try:
        raw, sig = token.split(".", 1)
        expected = base64.urlsafe_b64encode(
            hmac.new(_secret(), raw.encode("ascii"), hashlib.sha256).digest()
        ).decode("ascii").rstrip("=")
        if not hmac.compare_digest(sig, expected):
            raise ValueError("signature")
        payload = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
        if int(payload["exp"]) < int(time.time()):
            raise ValueError("expired")
        if payload.get("scope") != expected_scope:
            raise ValueError("scope")
        return payload
    except (ValueError, KeyError, json.JSONDecodeError, TypeError) as exc:
        raise HTTPException(status_code=401, detail="نشست نامعتبر یا منقضی شده است") from exc


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="احراز هویت لازم است")
    return authorization[7:].strip()


def current_admin(authorization: str | None = Header(None)) -> dict[str, Any]:
    payload = _decode_token(_bearer(authorization), expected_scope="admin")
    with db.conn() as con:
        row = con.execute(
            "SELECT id,username,display_name,role,active FROM web_admins WHERE id=?",
            (int(payload["sub"]),),
        ).fetchone()
    if not row or not bool(row["active"]):
        raise HTTPException(status_code=401, detail="حساب مدیر غیرفعال است")
    return dict(row)


def require_admin(admin: dict[str, Any] = Depends(current_admin)) -> dict[str, Any]:
    if str(admin["role"]).upper() != "ADMIN":
        raise HTTPException(status_code=403, detail="این عملیات فقط برای مدیر اصلی مجاز است")
    return admin


def current_portal_user(authorization: str | None = Header(None)) -> dict[str, Any]:
    payload = _decode_token(_bearer(authorization), expected_scope="portal")
    user = db.get_user(int(payload["sub"]))
    if not user:
        raise HTTPException(status_code=401, detail="حساب کاربری پیدا نشد")
    if "status" in user.keys() and str(user["status"] or "").upper() == "BLOCKED":
        raise HTTPException(status_code=403, detail="حساب کاربری غیرفعال است")
    return dict(user)


def _audit(admin: dict[str, Any], action: str, target: int | None = None, details: str = "") -> None:
    db.add_audit(int(admin["id"]), action, target, details[:1000])


class LoginRequest(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=8, max_length=256)


@router.post("/auth/login")
def login(req: LoginRequest):
    init_admin_schema()
    generic = "نام کاربری یا رمز عبور نادرست است"
    with db.conn() as con:
        row = con.execute(
            "SELECT * FROM web_admins WHERE username=? COLLATE NOCASE",
            (req.username.strip(),),
        ).fetchone()
        if not row or not bool(row["active"]):
            hashlib.pbkdf2_hmac("sha256", req.password.encode("utf-8"), b"invalid-login-pad", 310_000)
            raise HTTPException(status_code=401, detail=generic)
        if row["locked_until"] and str(row["locked_until"]) > db.now_iso():
            raise HTTPException(status_code=429, detail="حساب موقتاً قفل شده است")
        if not _password_ok(req.password, str(row["password_hash"])):
            failures = int(row["failed_attempts"] or 0) + 1
            locked = (_utcnow() + timedelta(minutes=15)).isoformat() if failures >= 5 else None
            con.execute(
                "UPDATE web_admins SET failed_attempts=?,locked_until=? WHERE id=?",
                (failures, locked, int(row["id"])),
            )
            raise HTTPException(status_code=401, detail=generic)
        con.execute(
            "UPDATE web_admins SET failed_attempts=0,locked_until=NULL,last_login_at=? WHERE id=?",
            (db.now_iso(), int(row["id"])),
        )
        admin = dict(row)
    ttl = max(900, min(86400, int(os.getenv("ADMIN_SESSION_MINUTES", "480")) * 60))
    return {
        "token": _encode_token(subject=int(admin["id"]), scope="admin", role=str(admin["role"]), ttl_seconds=ttl),
        "user": {k: admin[k] for k in ("id", "username", "display_name", "role")},
    }


@router.get("/auth/me")
def me(admin=Depends(current_admin)):
    return admin


@router.get("/capabilities")
def capabilities(admin=Depends(current_admin)):
    return {
        "admin_web": True,
        "user_portal": True,
        "signal_authorities": ["MT5_ADMIN", "WEB_ADMIN"],
        "miniapp_signal_issuance": False,
        "risk_source": "autotrade_risk_firewall",
        "web_signal_chart_capture": db.get_setting("web_mt5_chart_capture_enabled", "0") == "1",
        "admin_accounts": list(settings.nexus_admin_mt5_accounts),
    }


@router.get("/dashboard")
def dashboard(admin=Depends(current_admin)):
    with db.conn() as con:
        signal_counts = {
            str(r["status"]): int(r["n"])
            for r in con.execute("SELECT status,COUNT(*) AS n FROM signals GROUP BY status").fetchall()
        }
        mt5_online = con.execute(
            "SELECT COUNT(*) FROM autotrade_mt5_accounts WHERE last_seen_at>=?",
            ((_utcnow() - timedelta(minutes=2)).isoformat(),),
        ).fetchone()[0]
    return {
        "stats": db.stats(),
        "entitlements": db.entitlement_counts(),
        "signals": signal_counts,
        "mt5_online": int(mt5_online or 0),
        "global_kill_switch": risk_firewall.global_kill_switch(),
    }


@router.get("/users")
def users(
    q: str = Query("", max_length=128),
    limit: int = Query(100, ge=1, le=300),
    admin=Depends(current_admin),
):
    needle = q.strip()
    with db.conn() as con:
        if needle:
            like = f"%{needle}%"
            rows = con.execute(
                """SELECT telegram_id,username,first_name,language,points_balance,created_at,updated_at
                   FROM users
                   WHERE CAST(telegram_id AS TEXT) LIKE ? OR username LIKE ? OR first_name LIKE ?
                   ORDER BY updated_at DESC LIMIT ?""",
                (like, like, like, int(limit)),
            ).fetchall()
        else:
            rows = con.execute(
                """SELECT telegram_id,username,first_name,language,points_balance,created_at,updated_at
                   FROM users ORDER BY updated_at DESC LIMIT ?""",
                (int(limit),),
            ).fetchall()
    result = []
    for row in rows:
        uid = int(row["telegram_id"])
        lic = db.active_license(uid)
        result.append({
            **dict(row),
            "vip": db.has_entitlement(uid, "vip") if lic else False,
            "autotrade": db.has_entitlement(uid, "autotrade") if lic else False,
            "license_expires_at": str(lic["expires_at"]) if lic else None,
        })
    return {"items": result}


@router.get("/signals")
def signals(limit: int = Query(100, ge=1, le=300), admin=Depends(current_admin)):
    with db.conn() as con:
        rows = con.execute(
            """SELECT id,code,symbol,market_type,timeframe,direction,entry_price,stop_loss,status,
                      destination,trailing_code,issuer_type,issuer_account,created_at,issued_at
               FROM signals ORDER BY id DESC LIMIT ?""",
            (int(limit),),
        ).fetchall()
    return {"items": [dict(r) for r in rows]}


@router.get("/signals/options")
def signal_options(admin=Depends(current_admin)):
    return {
        "admin_accounts": list(settings.nexus_admin_mt5_accounts),
        "order_types": [
            "MARKET", "BUY_LIMIT", "SELL_LIMIT", "BUY_STOP", "SELL_STOP",
            "BUY_STOP_LIMIT", "SELL_STOP_LIMIT",
        ],
        "timeframes": ["M1", "M3", "M5", "M15", "M30", "H1", "H4", "D1", "W1"],
        "destinations": ["FREE", "VIP", "BOTH"],
        "chart_capture_required": True,
        "chart_capture_ready": db.get_setting("web_mt5_chart_capture_enabled", "0") == "1",
    }


class GlobalKillWrite(BaseModel):
    enabled: bool


@router.get("/risk/global")
def get_global_risk(admin=Depends(current_admin)):
    return {"kill_switch": risk_firewall.global_kill_switch()}


@router.put("/risk/global")
def put_global_risk(req: GlobalKillWrite, admin=Depends(require_admin)):
    risk_firewall.set_global_kill_switch(req.enabled)
    _audit(admin, "web_global_kill_switch", None, f"enabled={int(req.enabled)}")
    return {"kill_switch": risk_firewall.global_kill_switch()}


@router.get("/risk/users/{telegram_id}")
def get_user_risk(telegram_id: int, admin=Depends(current_admin)):
    if not db.get_user(telegram_id):
        raise HTTPException(status_code=404, detail="کاربر پیدا نشد")
    return risk_firewall._profile(int(telegram_id))


class UserRiskWrite(BaseModel):
    daily_loss_limit_r: float | None = Field(None, ge=0.25, le=20)
    dynamic_risk_enabled: bool | None = None
    min_risk_multiplier: float | None = Field(None, ge=0.10, le=1.0)
    max_loss_streak: int | None = Field(None, ge=1, le=10)
    kill_switch: bool | None = None


@router.put("/risk/users/{telegram_id}")
def put_user_risk(telegram_id: int, req: UserRiskWrite, admin=Depends(require_admin)):
    if not db.get_user(telegram_id):
        raise HTTPException(status_code=404, detail="کاربر پیدا نشد")
    try:
        profile = risk_firewall.set_user_profile(telegram_id, **req.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _audit(admin, "web_user_risk_updated", telegram_id, req.model_dump_json())
    return profile


class PortalLoginRequest(BaseModel):
    telegram_id: int = Field(gt=0)
    license_key: str = Field(min_length=8, max_length=128)


@router.post("/portal/auth/login")
def portal_login(req: PortalLoginRequest):
    lic = db.license_by_key(req.license_key, active_only=True)
    if not lic or int(lic["telegram_id"]) != int(req.telegram_id):
        raise HTTPException(status_code=401, detail="شناسه تلگرام یا لایسنس معتبر نیست")
    user = db.get_user(req.telegram_id)
    if not user:
        raise HTTPException(status_code=401, detail="کاربر پیدا نشد")
    token = _encode_token(subject=req.telegram_id, scope="portal", ttl_seconds=8 * 3600)
    return {"token": token, "user": {"telegram_id": req.telegram_id, "first_name": user["first_name"], "username": user["username"]}}


@router.get("/portal/overview")
def portal_overview(user=Depends(current_portal_user)):
    uid = int(user["telegram_id"])
    lic = db.active_license(uid)
    account = db.mt5_account(uid)
    live = []
    if account:
        live = db.mt5_live_positions(str(account["account_number"]), nexus_only=True) + db.mt5_live_orders(str(account["account_number"]), nexus_only=True)
    return {
        "user": {
            "telegram_id": uid,
            "username": user.get("username"),
            "first_name": user.get("first_name"),
            "points_balance": int(user.get("points_balance") or 0),
        },
        "entitlements": {
            "vip": db.has_entitlement(uid, "vip") if lic else False,
            "autotrade": db.has_entitlement(uid, "autotrade") if lic else False,
        },
        "license": dict(lic) if lic else None,
        "mt5": dict(account) if account else None,
        "live": live,
        "risk": risk_firewall._profile(uid),
    }
