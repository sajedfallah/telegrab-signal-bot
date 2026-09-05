from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import hmac
import io
import json
import os
import secrets
import struct
import time
import zipfile
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Response, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, field_validator

from . import db

router = APIRouter(prefix="/api/v1/admin-web", tags=["admin-web"])
ROLES = {"ADMIN", "MODERATOR", "VIP_USER", "REGULAR_USER"}
SIGNAL_STATUSES = {"DRAFT", "PENDING", "ACTIVE", "CLOSED", "CANCELED"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _secret() -> bytes:
    value = os.getenv("ADMIN_WEB_SECRET", "").strip()
    if len(value) < 32:
        # Local installations remain operable without silently persisting a
        # weak secret. Public deployments must set ADMIN_WEB_SECRET.
        value = f"local-only:{db.DB_PATH.resolve()}:{os.getenv('NEXUS_ADMIN_TOKEN', '')}"
    return hashlib.sha256(value.encode()).digest()


def _password_hash(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)
    return f"pbkdf2_sha256$310000${base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(digest).decode()}"


def _password_ok(password: str, encoded: str) -> bool:
    try:
        _, rounds, salt, expected = encoded.split("$", 3)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.urlsafe_b64decode(salt), int(rounds))
        return hmac.compare_digest(base64.urlsafe_b64encode(digest).decode(), expected)
    except (ValueError, TypeError):
        return False


def init_admin_schema() -> None:
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
            CREATE TABLE IF NOT EXISTS web_notification_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id INTEGER,
                channels TEXT NOT NULL,
                audience TEXT NOT NULL,
                message TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'QUEUED',
                sent_count INTEGER NOT NULL DEFAULT 0,
                failed_count INTEGER NOT NULL DEFAULT 0,
                created_by INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                finished_at TEXT
            );
            CREATE TABLE IF NOT EXISTS expert_settings (
                account_number TEXT PRIMARY KEY,
                risk_percent REAL NOT NULL DEFAULT 1,
                max_daily_loss REAL NOT NULL DEFAULT 3,
                max_open_trades INTEGER NOT NULL DEFAULT 3,
                fixed_lot REAL,
                trading_enabled INTEGER NOT NULL DEFAULT 1,
                updated_by INTEGER,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS user_risk_preferences (
                telegram_id INTEGER PRIMARY KEY,
                management_mode TEXT NOT NULL DEFAULT 'SELF',
                risk_percent REAL NOT NULL DEFAULT 1,
                max_daily_loss REAL NOT NULL DEFAULT 3,
                max_open_trades INTEGER NOT NULL DEFAULT 3,
                max_daily_trades INTEGER NOT NULL DEFAULT 10,
                fixed_lot REAL,
                emergency_stop INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(telegram_id) REFERENCES users(telegram_id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS system_controls (
                control_key TEXT PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 0,
                value_json TEXT NOT NULL DEFAULT '{}',
                updated_by INTEGER,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS risk_policies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                risk_percent REAL NOT NULL,
                max_daily_loss REAL NOT NULL,
                max_open_trades INTEGER NOT NULL,
                max_daily_trades INTEGER NOT NULL,
                symbols_json TEXT NOT NULL DEFAULT '[]',
                active INTEGER NOT NULL DEFAULT 1,
                created_by INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );
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
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS message_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                channel TEXT NOT NULL,
                body TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                updated_by INTEGER,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS market_news_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                currency TEXT NOT NULL,
                impact TEXT NOT NULL,
                event_at TEXT NOT NULL,
                pause_before_minutes INTEGER NOT NULL DEFAULT 15,
                pause_after_minutes INTEGER NOT NULL DEFAULT 15,
                auto_pause INTEGER NOT NULL DEFAULT 1,
                created_by INTEGER,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_web_admins_username ON web_admins(username);
            CREATE INDEX IF NOT EXISTS idx_notification_jobs_created ON web_notification_jobs(created_at DESC);
            """
        )
        user_columns = {r[1] for r in con.execute("PRAGMA table_info(users)")}
        for name, ddl in {
            "role": "ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'REGULAR_USER'",
            "status": "ALTER TABLE users ADD COLUMN status TEXT NOT NULL DEFAULT 'ACTIVE'",
            "email": "ALTER TABLE users ADD COLUMN email TEXT",
            "notes": "ALTER TABLE users ADD COLUMN notes TEXT",
        }.items():
            if name not in user_columns:
                con.execute(ddl)
        signal_columns = {r[1] for r in con.execute("PRAGMA table_info(signals)")}
        for name, ddl in {
            "technical_analysis": "ALTER TABLE signals ADD COLUMN technical_analysis TEXT",
            "fundamental_analysis": "ALTER TABLE signals ADD COLUMN fundamental_analysis TEXT",
            "category": "ALTER TABLE signals ADD COLUMN category TEXT NOT NULL DEFAULT 'GENERAL'",
        }.items():
            if name not in signal_columns:
                con.execute(ddl)

        username = os.getenv("ADMIN_WEB_USERNAME", "admin").strip() or "admin"
        password = os.getenv("ADMIN_WEB_PASSWORD", "").strip()
        exists = con.execute("SELECT 1 FROM web_admins LIMIT 1").fetchone()
        if not exists and len(password) >= 12 and "CHANGE_ME" not in password.upper():
            con.execute(
                "INSERT INTO web_admins(username,password_hash,display_name,role,created_at) VALUES(?,?,?,?,?)",
                (username, _password_hash(password), "مدیر سیستم", "ADMIN", db.now_iso()),
            )


def _encode_token(admin: dict[str, Any]) -> str:
    minutes = max(15, min(1440, int(os.getenv("ADMIN_SESSION_MINUTES", "480"))))
    payload = {"sub": int(admin["id"]), "role": admin["role"], "exp": int(time.time()) + minutes * 60, "nonce": secrets.token_hex(8)}
    raw = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    sig = base64.urlsafe_b64encode(hmac.new(_secret(), raw.encode(), hashlib.sha256).digest()).decode().rstrip("=")
    return f"{raw}.{sig}"


def _encode_user_token(telegram_id: int) -> str:
    payload = {"sub": int(telegram_id), "scope": "user-portal", "exp": int(time.time()) + 8 * 3600, "nonce": secrets.token_hex(8)}
    raw = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    sig = base64.urlsafe_b64encode(hmac.new(_secret(), raw.encode(), hashlib.sha256).digest()).decode().rstrip("=")
    return f"{raw}.{sig}"


def _decode_token(token: str) -> dict[str, Any]:
    try:
        raw, sig = token.split(".", 1)
        expected = base64.urlsafe_b64encode(hmac.new(_secret(), raw.encode(), hashlib.sha256).digest()).decode().rstrip("=")
        if not hmac.compare_digest(sig, expected):
            raise ValueError
        payload = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
        if int(payload["exp"]) < int(time.time()):
            raise ValueError
        return payload
    except (ValueError, KeyError, json.JSONDecodeError):
        raise HTTPException(status_code=401, detail="نشست نامعتبر یا منقضی شده است")


def current_admin(authorization: str | None = Header(None)) -> dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="احراز هویت لازم است")
    payload = _decode_token(authorization[7:].strip())
    with db.conn() as con:
        row = con.execute("SELECT id,username,display_name,role,active FROM web_admins WHERE id=?", (payload["sub"],)).fetchone()
    if not row or not row["active"]:
        raise HTTPException(status_code=401, detail="حساب مدیر غیرفعال است")
    return dict(row)


def current_portal_user(authorization: str | None = Header(None)) -> dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="ورود به حساب کاربری لازم است")
    payload = _decode_token(authorization[7:].strip())
    if payload.get("scope") != "user-portal":
        raise HTTPException(status_code=401, detail="نشست کاربری نامعتبر است")
    with db.conn() as con:
        row = con.execute("SELECT telegram_id,username,first_name,language,role,status,points_balance,created_at FROM users WHERE telegram_id=?", (payload["sub"],)).fetchone()
    if not row or str(row["status"]).upper() == "BLOCKED":
        raise HTTPException(status_code=403, detail="حساب کاربری غیرفعال است")
    return dict(row)


def require(*roles: str):
    def dependency(admin: dict[str, Any] = Depends(current_admin)):
        if admin["role"] not in roles:
            raise HTTPException(status_code=403, detail="دسترسی کافی نیست")
        return admin
    return dependency


def _audit(admin: dict[str, Any], action: str, target: int | None = None, details: str = "") -> None:
    db.add_audit(int(admin["id"]), action, target, details[:1000])


class LoginRequest(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=8, max_length=256)


@router.post("/auth/login")
def login(req: LoginRequest):
    init_admin_schema()
    with db.conn() as con:
        row = con.execute("SELECT * FROM web_admins WHERE username=? COLLATE NOCASE", (req.username.strip(),)).fetchone()
        generic = "نام کاربری یا رمز عبور نادرست است"
        if not row or not row["active"]:
            hashlib.pbkdf2_hmac("sha256", req.password.encode(), b"invalid-login-pad", 310_000)
            raise HTTPException(status_code=401, detail=generic)
        if row["locked_until"] and str(row["locked_until"]) > db.now_iso():
            raise HTTPException(status_code=429, detail="حساب موقتاً قفل شده است")
        if not _password_ok(req.password, row["password_hash"]):
            failures = int(row["failed_attempts"] or 0) + 1
            locked = (_utcnow() + timedelta(minutes=15)).isoformat() if failures >= 5 else None
            con.execute("UPDATE web_admins SET failed_attempts=?,locked_until=? WHERE id=?", (failures, locked, row["id"]))
            raise HTTPException(status_code=401, detail=generic)
        con.execute("UPDATE web_admins SET failed_attempts=0,locked_until=NULL,last_login_at=? WHERE id=?", (db.now_iso(), row["id"]))
        admin = dict(row)
    return {"token": _encode_token(admin), "user": {k: admin[k] for k in ("id", "username", "display_name", "role")}}


@router.get("/auth/me")
def me(admin=Depends(current_admin)):
    return admin


class PortalLoginRequest(BaseModel):
    telegram_id: int = Field(gt=0)
    license_key: str = Field(min_length=8, max_length=128)


@router.post("/portal/auth/login")
def portal_login(req: PortalLoginRequest):
    license_row = db.license_by_key(req.license_key, active_only=True)
    if not license_row or int(license_row["telegram_id"]) != req.telegram_id:
        raise HTTPException(status_code=401, detail="شناسه تلگرام یا کلید لایسنس معتبر نیست")
    user = db.get_user(req.telegram_id)
    if not user or ("status" in user.keys() and str(user["status"]).upper() == "BLOCKED"):
        raise HTTPException(status_code=403, detail="حساب کاربری غیرفعال است")
    return {"token": _encode_user_token(req.telegram_id), "user": {"telegram_id": req.telegram_id, "first_name": user["first_name"], "username": user["username"]}}


@router.get("/portal/overview")
def portal_overview(user=Depends(current_portal_user)):
    telegram_id = int(user["telegram_id"])
    entitlements = db.current_entitlements(telegram_id)
    account = db.mt5_account(telegram_id)
    trades = [dict(row) for row in db.autotrade_user_signal_receipts(telegram_id, limit=20)]
    start = (_utcnow() - timedelta(days=30)).isoformat()
    stats = db.autotrade_user_daily_stats(telegram_id, start, db.now_iso())
    destination = "BOTH" if entitlements.get("vip") else "FREE"
    with db.conn() as con:
        signal_rows = [dict(r) for r in con.execute("""SELECT id,code,symbol,market_type,timeframe,direction,entry_price,stop_loss,tp1,tp2,tp3,status,created_at,technical_analysis
          FROM signals WHERE status IN ('ACTIVE','PENDING') AND destination IN ('BOTH',?) ORDER BY id DESC LIMIT 20""", (destination,))]
        preference = con.execute("SELECT * FROM user_risk_preferences WHERE telegram_id=?", (telegram_id,)).fetchone()
        expert_risk = con.execute("SELECT * FROM expert_settings WHERE account_number=?", (str(account["account_number"]),)).fetchone() if account else None
    live = []
    if account:
        live = db.mt5_live_positions(str(account["account_number"]), nexus_only=True) + db.mt5_live_orders(str(account["account_number"]), nexus_only=True)
    risk = dict(preference) if preference else {"management_mode": "SELF", "risk_percent": 1, "max_daily_loss": 3, "max_open_trades": 3, "max_daily_trades": 10, "fixed_lot": None, "emergency_stop": 0}
    if risk["management_mode"] == "ADMIN" and expert_risk:
        risk.update({"risk_percent": expert_risk["risk_percent"], "max_daily_loss": expert_risk["max_daily_loss"], "max_open_trades": expert_risk["max_open_trades"], "fixed_lot": expert_risk["fixed_lot"], "emergency_stop": 0 if expert_risk["trading_enabled"] else 1})
    return {"user": user, "entitlements": entitlements, "account": dict(account) if account else None, "stats": stats, "signals": signal_rows, "trades": trades, "live": live, "risk": risk, "server_time": db.now_iso()}


class PortalRiskSettings(BaseModel):
    management_mode: str = Field(pattern="^(SELF|ADMIN)$")
    risk_percent: float = Field(default=1, ge=0.1, le=10)
    max_daily_loss: float = Field(default=3, ge=0.5, le=25)
    max_open_trades: int = Field(default=3, ge=1, le=20)
    max_daily_trades: int = Field(default=10, ge=1, le=100)
    fixed_lot: float | None = Field(default=None, gt=0, le=100)
    emergency_stop: bool = False


@router.put("/portal/risk-settings")
def portal_risk_settings(req: PortalRiskSettings, user=Depends(current_portal_user)):
    telegram_id = int(user["telegram_id"])
    with db.conn() as con:
        con.execute("""INSERT INTO user_risk_preferences(telegram_id,management_mode,risk_percent,max_daily_loss,max_open_trades,max_daily_trades,fixed_lot,emergency_stop,updated_at)
          VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(telegram_id) DO UPDATE SET management_mode=excluded.management_mode,risk_percent=excluded.risk_percent,
          max_daily_loss=excluded.max_daily_loss,max_open_trades=excluded.max_open_trades,max_daily_trades=excluded.max_daily_trades,
          fixed_lot=excluded.fixed_lot,emergency_stop=excluded.emergency_stop,updated_at=excluded.updated_at""",
          (telegram_id, req.management_mode, req.risk_percent, req.max_daily_loss, req.max_open_trades, req.max_daily_trades, req.fixed_lot, int(req.emergency_stop), db.now_iso()))
        account = con.execute("SELECT account_number FROM autotrade_mt5_accounts WHERE telegram_id=?", (telegram_id,)).fetchone()
        if account and req.management_mode == "SELF":
            con.execute("""INSERT INTO expert_settings(account_number,risk_percent,max_daily_loss,max_open_trades,fixed_lot,trading_enabled,updated_by,updated_at)
              VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(account_number) DO UPDATE SET risk_percent=excluded.risk_percent,max_daily_loss=excluded.max_daily_loss,
              max_open_trades=excluded.max_open_trades,fixed_lot=excluded.fixed_lot,trading_enabled=excluded.trading_enabled,updated_by=excluded.updated_by,updated_at=excluded.updated_at""",
              (str(account["account_number"]), req.risk_percent, req.max_daily_loss, req.max_open_trades, req.fixed_lot, int(not req.emergency_stop), telegram_id, db.now_iso()))
    db.add_audit(telegram_id, "portal_risk_settings_updated", telegram_id, f"mode={req.management_mode}; risk={req.risk_percent}")
    return {"ok": True, "mode": req.management_mode}


@router.get("/dashboard")
def dashboard(admin=Depends(current_admin)):
    with db.conn() as con:
        counts = dict(con.execute("""
            SELECT COUNT(*) users,
                   SUM(CASE WHEN status='ACTIVE' THEN 1 ELSE 0 END) active_users,
                   SUM(CASE WHEN role='VIP_USER' THEN 1 ELSE 0 END) vip_users
            FROM users
        """).fetchone())
        signal = dict(con.execute("""
            SELECT COUNT(*) total,
                   SUM(CASE WHEN status IN ('ACTIVE','PENDING') THEN 1 ELSE 0 END) active,
                   SUM(CASE WHEN status='CLOSED' AND COALESCE(result_value,0)>0 THEN 1 ELSE 0 END) wins,
                   SUM(CASE WHEN status='CLOSED' THEN 1 ELSE 0 END) closed
            FROM signals
        """).fetchone())
        profit = dict(con.execute("SELECT COALESCE(SUM(profit),0) profit,COUNT(DISTINCT telegram_id) traders FROM autotrade_trade_executions WHERE event_type='CLOSE'").fetchone())
        experts = dict(con.execute("SELECT COUNT(*) total,SUM(CASE WHEN last_seen_at >= datetime('now','-2 minutes') THEN 1 ELSE 0 END) online FROM autotrade_mt5_accounts").fetchone())
        trend = [dict(r) for r in con.execute("""
            WITH RECURSIVE days(d) AS (SELECT date('now','-6 days') UNION ALL SELECT date(d,'+1 day') FROM days WHERE d<date('now'))
            SELECT d date, COUNT(s.id) signals,
                   COALESCE(SUM(CASE WHEN COALESCE(s.result_value,0)>0 THEN 1 ELSE 0 END),0) wins
            FROM days LEFT JOIN signals s ON date(s.created_at)=d GROUP BY d ORDER BY d
        """)]
        recent = [dict(r) for r in con.execute("SELECT id,admin_id,action,target_id,details,created_at FROM audit_logs ORDER BY id DESC LIMIT 8")]
    closed = int(signal.get("closed") or 0)
    return {"users": counts, "signals": signal, "experts": experts, "profit": profit, "win_rate": round(int(signal.get("wins") or 0) * 100 / closed, 1) if closed else 0, "trend": trend, "recent_activity": recent, "server_time": db.now_iso()}


@router.get("/users")
def users(q: str = "", role: str = "", status: str = "", page: int = Query(1, ge=1), page_size: int = Query(20, ge=5, le=100), admin=Depends(current_admin)):
    where, args = ["1=1"], []
    if q.strip():
        where.append("(CAST(u.telegram_id AS TEXT) LIKE ? OR u.username LIKE ? OR u.first_name LIKE ? OR u.email LIKE ?)")
        args.extend([f"%{q.strip()}%"] * 4)
    if role.upper() in ROLES:
        where.append("u.role=?"); args.append(role.upper())
    if status.upper() in {"ACTIVE", "BLOCKED"}:
        where.append("u.status=?"); args.append(status.upper())
    clause = " AND ".join(where)
    with db.conn() as con:
        total = con.execute(f"SELECT COUNT(*) FROM users u WHERE {clause}", args).fetchone()[0]
        rows = [dict(r) for r in con.execute(f"""
            SELECT u.telegram_id,u.username,u.first_name,u.email,u.language,u.role,u.status,u.points_balance,u.created_at,u.updated_at,
                   EXISTS(SELECT 1 FROM licenses l WHERE l.telegram_id=u.telegram_id AND l.status='active' AND l.expires_at>?) has_license,
                   (SELECT MAX(a.last_seen_at) FROM autotrade_mt5_accounts a WHERE a.telegram_id=u.telegram_id) expert_last_seen
            FROM users u WHERE {clause} ORDER BY u.created_at DESC LIMIT ? OFFSET ?
        """, [db.now_iso(), *args, page_size, (page - 1) * page_size])]
    return {"items": rows, "total": total, "page": page, "page_size": page_size}


class UserUpdate(BaseModel):
    first_name: str | None = Field(None, max_length=120)
    username: str | None = Field(None, max_length=64)
    email: str | None = Field(None, max_length=200)
    role: str | None = None
    status: str | None = None
    notes: str | None = Field(None, max_length=2000)

    @field_validator("role")
    @classmethod
    def role_valid(cls, value):
        if value is not None and value.upper() not in ROLES: raise ValueError("invalid role")
        return value.upper() if value else value


@router.patch("/users/{telegram_id}")
def update_user(telegram_id: int, req: UserUpdate, admin=Depends(require("ADMIN", "MODERATOR"))):
    values = req.model_dump(exclude_unset=True)
    if "status" in values and str(values["status"]).upper() not in {"ACTIVE", "BLOCKED"}: raise HTTPException(422, "invalid status")
    if "status" in values: values["status"] = str(values["status"]).upper()
    if not values: raise HTTPException(422, "هیچ تغییری ارسال نشده است")
    with db.conn() as con:
        if not con.execute("SELECT 1 FROM users WHERE telegram_id=?", (telegram_id,)).fetchone(): raise HTTPException(404, "کاربر پیدا نشد")
        values["updated_at"] = db.now_iso()
        con.execute(f"UPDATE users SET {','.join(f'{k}=?' for k in values)} WHERE telegram_id=?", [*values.values(), telegram_id])
    _audit(admin, "web_user_updated", telegram_id, json.dumps(values, ensure_ascii=False))
    return {"ok": True}


@router.delete("/users/{telegram_id}")
def delete_user(telegram_id: int, admin=Depends(require("ADMIN"))):
    with db.conn() as con:
        if con.execute("SELECT 1 FROM payments WHERE telegram_id=? LIMIT 1", (telegram_id,)).fetchone():
            raise HTTPException(409, "کاربر دارای سوابق مالی است؛ به‌جای حذف، مسدودش کنید")
        cur = con.execute("DELETE FROM users WHERE telegram_id=?", (telegram_id,))
    if not cur.rowcount: raise HTTPException(404, "کاربر پیدا نشد")
    _audit(admin, "web_user_deleted", telegram_id)
    return Response(status_code=204)


@router.get("/users/{telegram_id}/activity")
def user_activity(telegram_id: int, admin=Depends(current_admin)):
    with db.conn() as con:
        user = con.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
        if not user: raise HTTPException(404, "کاربر پیدا نشد")
        payments = [dict(r) for r in con.execute("SELECT id,plan_code,status,payment_method,created_at,reviewed_at FROM payments WHERE telegram_id=? ORDER BY id DESC LIMIT 30", (telegram_id,))]
        trades = [dict(r) for r in con.execute("SELECT id,event_type AS event_name,ticket,symbol,direction,profit,created_at AS event_time FROM autotrade_trade_executions WHERE telegram_id=? ORDER BY id DESC LIMIT 50", (telegram_id,))]
        licenses = [dict(r) for r in con.execute("SELECT id,plan_code,status,starts_at,expires_at,vip_access,autotrade_access FROM licenses WHERE telegram_id=? ORDER BY id DESC LIMIT 20", (telegram_id,))]
    return {"user": dict(user), "payments": payments, "trades": trades, "licenses": licenses}


class SignalWrite(BaseModel):
    market_type: str = Field(pattern="^(FOREX|CRYPTO|GOLD|INDEX|OTHER)$")
    symbol: str = Field(min_length=2, max_length=64)
    timeframe: str = Field(default="M5", pattern="^(M1|M3|M5|M15|M30|H1|H4|D1|W1)$")
    direction: str = Field(pattern="^(BUY|SELL|LONG|SHORT)$")
    entry_price: float = Field(gt=0)
    stop_loss: float = Field(gt=0)
    targets: list[float] = Field(min_length=1, max_length=10)
    volume_mode: str = Field(default="RISK", pattern="^(RISK|FIXED)$")
    risk_percent: float = Field(default=1, ge=0, le=10)
    lot_size: float | None = Field(None, gt=0, le=100)
    destination: str = Field(default="BOTH", pattern="^(FREE|VIP|BOTH)$")
    order_type: str = Field(default="MARKET", pattern="^(MARKET|LIMIT|BUY_LIMIT|SELL_LIMIT|BUY_STOP|SELL_STOP|BUY_STOP_LIMIT|SELL_STOP_LIMIT)$")
    stop_limit_price: float | None = Field(None, gt=0)
    trailing_code: str | None = Field(None, pattern="^(NEXUS_TRAIL_0[1-7])$")
    max_entry_deviation_pct: float | None = Field(None, gt=0, le=20)
    max_entry_deviation_abs: float | None = Field(None, gt=0)
    technical_analysis: str = Field(default="", max_length=10000)
    fundamental_analysis: str = Field(default="", max_length=10000)
    chart_base64: str | None = Field(None, max_length=7_000_000)
    publish: bool = False
    issuer_account: str | None = Field(None, max_length=32)

    @field_validator("lot_size")
    @classmethod
    def fixed_lot_required(cls, value, info):
        if info.data.get("volume_mode") == "FIXED" and value is None:
            raise ValueError("lot_size is required in FIXED mode")
        return value


@router.get("/signals")
def signals(q: str = "", status: str = "", market: str = "", limit: int = Query(100, ge=1, le=300), admin=Depends(current_admin)):
    where, args = ["1=1"], []
    if q: where.append("(code LIKE ? OR symbol LIKE ?)"); args.extend([f"%{q}%", f"%{q}%"])
    if status.upper() in SIGNAL_STATUSES: where.append("status=?"); args.append(status.upper())
    if market.upper() in {"FOREX", "CRYPTO", "GOLD", "INDEX", "OTHER"}: where.append("market_type=?"); args.append(market.upper())
    with db.conn() as con:
        rows = [dict(r) for r in con.execute(f"SELECT * FROM signals WHERE {' AND '.join(where)} ORDER BY id DESC LIMIT ?", [*args, limit])]
        for row in rows:
            row["targets"] = [dict(t) for t in con.execute("SELECT target_no,price FROM signal_targets WHERE signal_id=? ORDER BY target_no", (row["id"],))]
    return {"items": rows}


@router.get("/signals/options")
def signal_options(admin=Depends(current_admin)):
    from .autotrade.trailing_profiles import TRAILING_PROFILES, TRAILING_GUIDE_FA
    symbols = {
        "FOREX": ["EURUSD","GBPUSD","USDJPY","USDCHF","AUDUSD","USDCAD","NZDUSD","EURJPY","GBPJPY","EURGBP"],
        "CRYPTO": ["BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT","ADAUSDT","DOGEUSDT","AVAXUSDT","LINKUSDT","TONUSDT"],
        "GOLD": ["XAUUSD","XAGUSD"],
        "INDEX": ["US30","US100","SPX500","GER40","UK100","JP225"],
        "OTHER": ["USOIL","UKOIL","NATGAS"],
    }
    trailing = [{"code":code,"name":profile["name"],"guide":TRAILING_GUIDE_FA.get(code,""),"config":profile} for code,profile in TRAILING_PROFILES.items()]
    from .config import settings
    return {"symbols":symbols,"trailing":trailing,"admin_accounts":list(settings.nexus_admin_mt5_accounts),"order_types":["MARKET","BUY_LIMIT","SELL_LIMIT","BUY_STOP","SELL_STOP","BUY_STOP_LIMIT","SELL_STOP_LIMIT"],"timeframes":["M1","M3","M5","M15","M30","H1","H4","D1","W1"]}


@router.post("/signals", status_code=201)
async def create_signal(req: SignalWrite, admin=Depends(require("ADMIN", "MODERATOR"))):
    try:
        raw_chart: bytes | None = None
        chart = req.chart_base64
        if chart and "," in chart[:128]: chart = chart.split(",", 1)[1]
        if chart:
            try:
                raw_chart = base64.b64decode(chart, validate=True)
                if not raw_chart or len(raw_chart) > 5_000_000: raise ValueError("chart image is empty or exceeds 5 MB")
                if not (raw_chart.startswith(b"\x89PNG\r\n\x1a\n") or raw_chart.startswith(b"\xff\xd8\xff")): raise ValueError("chart image must be PNG or JPEG")
            except (ValueError, binascii.Error) as exc:
                raise HTTPException(422, f"invalid chart image: {exc}") from exc
        if req.publish:
            from .config import settings
            account = str(req.issuer_account or (settings.nexus_admin_mt5_accounts[0] if settings.nexus_admin_mt5_accounts else "")).strip()
            if not account or account not in settings.nexus_admin_mt5_accounts:
                raise HTTPException(409, "یک حساب مرجع MT5 معتبر برای صدور وب تنظیم کنید")
            row = db.issue_mt5_admin_signal(market_type=req.market_type, symbol=req.symbol, direction=req.direction,
                entry_price=req.entry_price, stop_loss=req.stop_loss, targets=req.targets, risk_percent=req.risk_percent,
                rr_ratio=None, destination=req.destination, order_type=req.order_type, volume_mode=req.volume_mode,
                lot_size=req.lot_size, trailing_code=req.trailing_code, max_entry_deviation_pct=req.max_entry_deviation_pct,
                max_entry_deviation_abs=req.max_entry_deviation_abs, timeframe=req.timeframe, stop_limit_price=req.stop_limit_price,
                admin_account=account, admin_id=int(admin["id"]), request_id=f"WEB-{secrets.token_urlsafe(12)}")
        else:
            row = db.create_signal(market_type=req.market_type, symbol=req.symbol, direction=req.direction, entry_price=req.entry_price,
                stop_loss=req.stop_loss, targets=req.targets, risk_percent=req.risk_percent, rr_ratio=None, destination=req.destination,
                chart_file_id=None, created_by=int(admin["id"]), timeframe=req.timeframe, order_type=req.order_type,
                volume_mode=req.volume_mode, lot_size=req.lot_size, trailing_code=req.trailing_code,
                max_entry_deviation_pct=req.max_entry_deviation_pct, max_entry_deviation_abs=req.max_entry_deviation_abs,
                stop_limit_price=req.stop_limit_price)
        with db.conn() as con:
            con.execute("UPDATE signals SET category='GENERAL',technical_analysis=?,fundamental_analysis=? WHERE id=?", (req.technical_analysis, req.fundamental_analysis, row["id"]))
        publication = None
        if req.publish:
            if raw_chart:
                folder = db.DB_PATH.parent / "assets" / "autotrade" / "pending_signal_charts"
                folder.mkdir(parents=True, exist_ok=True)
                extension = "png" if raw_chart.startswith(b"\x89PNG") else "jpg"
                path = folder / f"{int(row['id'])}.{extension}"
                path.write_bytes(raw_chart); db.save_mt5_signal_publication_asset(int(row["id"]), str(path))
            publication = {"status":"WAITING_EXECUTION", "source_account":row["issuer_account"], "image":"UPLOADED" if raw_chart else "GENERATED_FALLBACK"}
        final = db.get_signal(int(row["id"]))
        _audit(admin, "web_signal_issued" if req.publish else "web_signal_created", int(row["id"]), str(row["code"]))
        return {"id": row["id"], "code": row["code"], "status": final["status"], "publication": publication}
    except ValueError as exc:
        raise HTTPException(422, str(exc))


class SignalPatch(BaseModel):
    status: str | None = None
    entry_price: float | None = Field(None, gt=0)
    stop_loss: float | None = Field(None, gt=0)
    targets: list[float] | None = Field(None, min_length=1, max_length=10)
    technical_analysis: str | None = Field(None, max_length=10000)
    fundamental_analysis: str | None = Field(None, max_length=10000)


@router.patch("/signals/{signal_id}")
def update_signal(signal_id: int, req: SignalPatch, admin=Depends(require("ADMIN", "MODERATOR"))):
    values = req.model_dump(exclude_unset=True); targets = values.pop("targets", None)
    if "status" in values:
        values["status"] = str(values["status"]).upper()
        if values["status"] not in SIGNAL_STATUSES: raise HTTPException(422, "invalid status")
    with db.conn() as con:
        if not con.execute("SELECT 1 FROM signals WHERE id=?", (signal_id,)).fetchone(): raise HTTPException(404, "سیگنال پیدا نشد")
        if values: con.execute(f"UPDATE signals SET {','.join(f'{k}=?' for k in values)} WHERE id=?", [*values.values(), signal_id])
        if targets is not None:
            con.execute("DELETE FROM signal_targets WHERE signal_id=?", (signal_id,))
            con.executemany("INSERT INTO signal_targets(signal_id,target_no,price) VALUES(?,?,?)", [(signal_id, i + 1, float(v)) for i, v in enumerate(targets)])
            con.execute("UPDATE signals SET tp1=?,tp2=?,tp3=? WHERE id=?", (targets[0], targets[1] if len(targets)>1 else None, targets[2] if len(targets)>2 else None, signal_id))
    _audit(admin, "web_signal_updated", signal_id, json.dumps(values, ensure_ascii=False))
    return {"ok": True}


@router.delete("/signals/{signal_id}")
def delete_signal(signal_id: int, admin=Depends(require("ADMIN"))):
    with db.conn() as con:
        row = con.execute("SELECT status FROM signals WHERE id=?", (signal_id,)).fetchone()
        if not row: raise HTTPException(404, "سیگنال پیدا نشد")
        if row["status"] not in {"DRAFT", "CANCELED"}: raise HTTPException(409, "فقط سیگنال پیش‌نویس یا لغوشده قابل حذف است")
        con.execute("DELETE FROM signals WHERE id=?", (signal_id,))
    _audit(admin, "web_signal_deleted", signal_id)
    return Response(status_code=204)


@router.get("/experts")
def experts(admin=Depends(current_admin)):
    with db.conn() as con:
        rows = [dict(r) for r in con.execute("""
            SELECT a.id,a.telegram_id,a.account_number,a.broker,a.server,a.status,a.ea_version,a.last_seen_at,
                   u.username,u.first_name,COALESCE(s.risk_percent,1) risk_percent,COALESCE(s.max_daily_loss,3) max_daily_loss,
                   COALESCE(s.max_open_trades,3) max_open_trades,s.fixed_lot,COALESCE(s.trading_enabled,1) trading_enabled,
                   COALESCE((SELECT SUM(t.profit) FROM autotrade_trade_executions t WHERE t.telegram_id=a.telegram_id AND t.event_type='CLOSE'),0) profit,
                   (SELECT COUNT(*) FROM mt5_live_state m WHERE m.account_number=a.account_number AND m.status IN ('OPEN','PENDING')) open_trades
            FROM autotrade_mt5_accounts a LEFT JOIN users u ON u.telegram_id=a.telegram_id LEFT JOIN expert_settings s ON s.account_number=a.account_number
            ORDER BY a.last_seen_at DESC
        """)]
    now = _utcnow()
    for row in rows:
        try: row["online"] = (now - datetime.fromisoformat(row["last_seen_at"])).total_seconds() < 120
        except (TypeError, ValueError): row["online"] = False
    return {"items": rows}


class ExpertSettings(BaseModel):
    risk_percent: float = Field(ge=0.01, le=100)
    max_daily_loss: float = Field(ge=0.1, le=100)
    max_open_trades: int = Field(ge=1, le=100)
    fixed_lot: float | None = Field(None, gt=0)
    trading_enabled: bool = True


@router.put("/experts/{account_number}/settings")
def expert_settings(account_number: str, req: ExpertSettings, admin=Depends(require("ADMIN", "MODERATOR"))):
    with db.conn() as con:
        if not con.execute("SELECT 1 FROM autotrade_mt5_accounts WHERE account_number=?", (account_number,)).fetchone(): raise HTTPException(404, "اکسپرت پیدا نشد")
        con.execute("""INSERT INTO expert_settings(account_number,risk_percent,max_daily_loss,max_open_trades,fixed_lot,trading_enabled,updated_by,updated_at)
          VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(account_number) DO UPDATE SET risk_percent=excluded.risk_percent,max_daily_loss=excluded.max_daily_loss,
          max_open_trades=excluded.max_open_trades,fixed_lot=excluded.fixed_lot,trading_enabled=excluded.trading_enabled,updated_by=excluded.updated_by,updated_at=excluded.updated_at""",
          (account_number, req.risk_percent, req.max_daily_loss, req.max_open_trades, req.fixed_lot, int(req.trading_enabled), admin["id"], db.now_iso()))
    _audit(admin, "web_expert_settings_updated", None, account_number)
    return {"ok": True}


@router.get("/experts/{account_number}/logs")
def expert_logs(account_number: str, limit: int = Query(100, ge=1, le=500), admin=Depends(current_admin)):
    with db.conn() as con:
        account = con.execute("SELECT telegram_id FROM autotrade_mt5_accounts WHERE account_number=?", (account_number,)).fetchone()
        if not account:
            raise HTTPException(404, "اکسپرت پیدا نشد")
        rows = [dict(r) for r in con.execute("""SELECT id,event_type AS event_name,ticket,signal_id,symbol,direction,volume,profit,created_at AS event_time,error_text AS payload_json
          FROM autotrade_trade_executions WHERE telegram_id=? ORDER BY id DESC LIMIT ?""", (account["telegram_id"], limit))]
        heartbeats = [dict(r) for r in con.execute("SELECT rowid AS id,role,ea_version,last_seen_at AS received_at,payload_json FROM mt5_heartbeats_v060 WHERE account_number=? LIMIT 20", (account_number,))]
    return {"events": rows, "heartbeats": heartbeats}


@router.get("/reports")
def reports(period: str = Query("30d", pattern="^(7d|30d|90d|all)$"), admin=Depends(current_admin)):
    days = {"7d": 7, "30d": 30, "90d": 90}.get(period)
    start = (_utcnow() - timedelta(days=days)).isoformat() if days else "2000-01-01T00:00:00+00:00"
    with db.conn() as con:
        summary = dict(con.execute("""SELECT COUNT(*) trades,COALESCE(SUM(profit),0) net_profit,
          COALESCE(AVG(profit),0) avg_profit,SUM(CASE WHEN profit>0 THEN 1 ELSE 0 END) wins,
          SUM(CASE WHEN profit<0 THEN 1 ELSE 0 END) losses FROM autotrade_trade_executions WHERE event_type='CLOSE' AND created_at>=?""", (start,)).fetchone())
        by_symbol = [dict(r) for r in con.execute("""SELECT symbol,COUNT(*) trades,ROUND(SUM(profit),2) profit,
          ROUND(100.0*SUM(CASE WHEN profit>0 THEN 1 ELSE 0 END)/COUNT(*),1) win_rate FROM autotrade_trade_executions
          WHERE event_type='CLOSE' AND created_at>=? GROUP BY symbol ORDER BY profit DESC LIMIT 20""", (start,))]
        daily = [dict(r) for r in con.execute("""SELECT date(created_at) date,ROUND(SUM(profit),2) profit,COUNT(*) trades
          FROM autotrade_trade_executions WHERE event_type='CLOSE' AND created_at>=? GROUP BY date(created_at) ORDER BY date""", (start,))]
    trades = int(summary.get("trades") or 0)
    summary["win_rate"] = round(int(summary.get("wins") or 0) * 100 / trades, 1) if trades else 0
    return {"period": period, "summary": summary, "by_symbol": by_symbol, "daily": daily}


def _xlsx(rows: list[list[Any]]) -> bytes:
    def cell(ref: str, value: Any) -> str:
        text = str(value if value is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return f'<c r="{ref}" t="inlineStr"><is><t>{text}</t></is></c>'
    xml_rows = []
    for rn, row in enumerate(rows, 1):
        cells = []
        for cn, value in enumerate(row, 1):
            n, col = cn, ""
            while n: n, rem = divmod(n - 1, 26); col = chr(65 + rem) + col
            cells.append(cell(f"{col}{rn}", value))
        xml_rows.append(f'<row r="{rn}">{"".join(cells)}</row>')
    files = {
        "[Content_Types].xml": '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
        "_rels/.rels": '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        "xl/workbook.xml": '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="NEXUS Report" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
        "xl/worksheets/sheet1.xml": f'<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{"".join(xml_rows)}</sheetData></worksheet>',
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, data in files.items(): archive.writestr(path, data)
    return output.getvalue()


@router.get("/reports/export.xlsx")
def export_xlsx(admin=Depends(current_admin)):
    with db.conn() as con:
        data = [["Signal", "Symbol", "Status", "Entry", "Exit", "Result", "Created"]] + [list(r) for r in con.execute("SELECT code,symbol,status,entry_price,exit_price,result_value,created_at FROM signals ORDER BY id DESC LIMIT 5000")]
    return Response(_xlsx(data), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": "attachment; filename=nexus-report.xlsx"})


@router.get("/reports/export.pdf")
def export_pdf(admin=Depends(current_admin)):
    # Minimal dependency-free PDF; the detailed RTL report remains available in
    # the UI while this portable export contains the executive numeric summary.
    report = reports("30d", admin)
    s = report["summary"]
    lines = ["NEXUS Trading Report - Last 30 Days", f"Trades: {s['trades']}", f"Win rate: {s['win_rate']}%", f"Net profit: {float(s['net_profit']):.2f}"]
    stream = "BT /F1 14 Tf 50 790 Td " + " ".join(f"({x.replace('(', '[').replace(')', ']')}) Tj 0 -24 Td" for x in lines) + " ET"
    objects = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>", "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>", f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream", "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out = io.BytesIO(); out.write(b"%PDF-1.4\n"); offsets = [0]
    for i, obj in enumerate(objects, 1): offsets.append(out.tell()); out.write(f"{i} 0 obj\n{obj}\nendobj\n".encode())
    xref = out.tell(); out.write(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    for off in offsets[1:]: out.write(f"{off:010d} 00000 n \n".encode())
    out.write(f"trailer << /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
    return Response(out.getvalue(), media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=nexus-report.pdf"})


class NotifyRequest(BaseModel):
    signal_id: int | None = None
    channels: list[str] = Field(min_length=1)
    audience: str = Field(default="ALL", pattern="^(ALL|VIP|REGULAR)$")
    message: str = Field(min_length=2, max_length=4000)


async def _deliver_notification(job_id: int, channels: list[str], audience: str, message: str) -> None:
    sent = failed = 0
    if "TELEGRAM" in channels:
        from aiogram import Bot
        from .config import settings
        target_key = {"ALL": "all", "VIP": "vip", "REGULAR": "nonvip"}[audience]
        targets = db.broadcast_targets(target_key)
        async with Bot(settings.bot_token) as bot:
            for row in targets:
                telegram_id = int(row["telegram_id"] if hasattr(row, "keys") else row)
                try:
                    await bot.send_message(telegram_id, message)
                    sent += 1
                except Exception:
                    failed += 1
                await asyncio.sleep(0.04)
    # Email and Web Push need provider credentials and subscriptions. Keeping
    # those channels queued is explicit and observable instead of claiming a
    # successful delivery that did not happen.
    pending_provider = any(channel in {"EMAIL", "PUSH"} for channel in channels)
    status = "PARTIAL" if pending_provider or failed else "SENT"
    with db.conn() as con:
        con.execute("UPDATE web_notification_jobs SET status=?,sent_count=?,failed_count=?,finished_at=? WHERE id=?",
                    (status, sent, failed, db.now_iso(), job_id))


@router.post("/notifications", status_code=202)
def notify(req: NotifyRequest, background: BackgroundTasks, admin=Depends(require("ADMIN", "MODERATOR"))):
    allowed = {"TELEGRAM", "EMAIL", "PUSH"}; channels = sorted({x.upper() for x in req.channels})
    if any(x not in allowed for x in channels): raise HTTPException(422, "invalid notification channel")
    with db.conn() as con:
        cur = con.execute("INSERT INTO web_notification_jobs(signal_id,channels,audience,message,created_by,created_at) VALUES(?,?,?,?,?,?)",
            (req.signal_id, ",".join(channels), req.audience, req.message, admin["id"], db.now_iso()))
        job_id = cur.lastrowid
    background.add_task(_deliver_notification, int(job_id), channels, req.audience, req.message)
    _audit(admin, "web_notification_queued", int(job_id), ",".join(channels))
    return {"id": job_id, "status": "QUEUED", "channels": channels}


@router.get("/audit")
def audit(limit: int = Query(100, ge=1, le=500), admin=Depends(current_admin)):
    with db.conn() as con: rows = [dict(r) for r in con.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?", (limit,))]
    return {"items": rows}


@router.get("/operations")
def operations(admin=Depends(current_admin)):
    with db.conn() as con:
        controls = {r["control_key"]: {"enabled": bool(r["enabled"]), "value": json.loads(r["value_json"] or "{}"), "updated_at": r["updated_at"]} for r in con.execute("SELECT * FROM system_controls")}
        live = [dict(r) for r in con.execute("SELECT * FROM mt5_live_state WHERE status IN ('OPEN','PENDING') ORDER BY last_seen_at DESC LIMIT 300")]
        failures = [dict(r) for r in con.execute("""SELECT d.id,d.signal_id,d.account_number,d.status,d.ticket,d.error_text,COALESCE(d.processed_at,d.first_seen_at) AS updated_at,s.code,s.symbol
          FROM signal_deliveries_v060 d LEFT JOIN signals s ON s.id=d.signal_id WHERE d.status IN ('FAILED','REJECTED','FAILED_RETRYABLE') ORDER BY d.id DESC LIMIT 100""")]
        heartbeats = [dict(r) for r in con.execute("SELECT account_number,role,ea_version,last_seen_at,payload_json FROM mt5_heartbeats_v060 ORDER BY last_seen_at DESC LIMIT 100")]
        commands = [dict(r) for r in con.execute("SELECT id,signal_id,command,payload_json,created_at FROM autotrade_commands ORDER BY id DESC LIMIT 30")]
    return {"controls": controls, "live": live, "failures": failures, "heartbeats": heartbeats, "commands": commands, "health": {"api": True, "database": True, "telegram": bool(os.getenv("BOT_TOKEN")), "websocket": True}}


class ControlUpdate(BaseModel):
    enabled: bool
    scope: str = Field(default="GLOBAL", max_length=64)
    reason: str = Field(default="", max_length=500)


@router.put("/operations/controls/{control_key}")
def update_control(control_key: str, req: ControlUpdate, admin=Depends(require("ADMIN"))):
    key = control_key.strip().upper()
    if key not in {"KILL_SWITCH", "NEWS_PAUSE", "SIGNAL_DELIVERY", "NEW_ENTRIES"}:
        raise HTTPException(422, "کنترل ناشناخته است")
    payload = json.dumps({"scope": req.scope, "reason": req.reason}, ensure_ascii=False)
    with db.conn() as con:
        con.execute("""INSERT INTO system_controls(control_key,enabled,value_json,updated_by,updated_at) VALUES(?,?,?,?,?)
          ON CONFLICT(control_key) DO UPDATE SET enabled=excluded.enabled,value_json=excluded.value_json,updated_by=excluded.updated_by,updated_at=excluded.updated_at""",
          (key, int(req.enabled), payload, admin["id"], db.now_iso()))
    db.set_setting(f"web_control_{key}", "1" if req.enabled else "0")
    _audit(admin, "system_control_updated", None, f"{key}={req.enabled}; scope={req.scope}; {req.reason}")
    return {"ok": True, "control": key, "enabled": req.enabled}


class LiveCommand(BaseModel):
    signal_id: int
    command: str = Field(pattern="^(CLOSE_SIGNAL|CANCEL_PENDING|MOVE_SL_TO_ENTRY|PARTIAL_CLOSE|UPDATE_SL|UPDATE_TP|ACTIVATE_TRAILING)$")
    value: str | None = Field(default=None, max_length=128)
    account_number: str | None = Field(default=None, max_length=32)


@router.post("/operations/commands", status_code=202)
def operation_command(req: LiveCommand, admin=Depends(require("ADMIN", "MODERATOR"))):
    if not db.get_signal(req.signal_id): raise HTTPException(404, "سیگنال پیدا نشد")
    command_id = db.create_autotrade_command(req.signal_id, req.command, {"value": req.value} if req.value else {}, actor_type="WEB_ADMIN", actor_id=admin["id"], account_number=req.account_number)
    _audit(admin, "live_trade_command", req.signal_id, f"{req.command}; account={req.account_number or 'ALL'}")
    return {"ok": True, "command_id": command_id}


@router.get("/risk-center")
def risk_center(admin=Depends(current_admin)):
    with db.conn() as con:
        preferences = [dict(r) for r in con.execute("""SELECT p.*,u.username,u.first_name,a.account_number,a.last_seen_at
          FROM user_risk_preferences p JOIN users u ON u.telegram_id=p.telegram_id LEFT JOIN autotrade_mt5_accounts a ON a.telegram_id=p.telegram_id ORDER BY p.updated_at DESC LIMIT 300""")]
        policies = [dict(r) for r in con.execute("SELECT * FROM risk_policies ORDER BY id DESC")]
        breaches = [dict(r) for r in con.execute("""SELECT telegram_id,date(created_at) day,ROUND(SUM(CASE WHEN event_type='CLOSE' THEN profit ELSE 0 END),2) pnl,COUNT(*) events
          FROM autotrade_trade_executions WHERE created_at>=datetime('now','-7 days') GROUP BY telegram_id,date(created_at) HAVING pnl<0 ORDER BY pnl LIMIT 50""")]
    return {"preferences": preferences, "policies": policies, "breaches": breaches}


class RiskPolicyWrite(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    risk_percent: float = Field(ge=.1, le=10)
    max_daily_loss: float = Field(ge=.5, le=25)
    max_open_trades: int = Field(ge=1, le=20)
    max_daily_trades: int = Field(ge=1, le=100)
    symbols: list[str] = []


@router.post("/risk-center/policies", status_code=201)
def create_risk_policy(req: RiskPolicyWrite, admin=Depends(require("ADMIN"))):
    try:
        with db.conn() as con:
            cur = con.execute("INSERT INTO risk_policies(name,risk_percent,max_daily_loss,max_open_trades,max_daily_trades,symbols_json,created_by,created_at) VALUES(?,?,?,?,?,?,?,?)",
              (req.name,req.risk_percent,req.max_daily_loss,req.max_open_trades,req.max_daily_trades,json.dumps(req.symbols),admin["id"],db.now_iso()))
        _audit(admin,"risk_policy_created",int(cur.lastrowid),req.name)
        return {"id":cur.lastrowid,"ok":True}
    except Exception as exc:
        raise HTTPException(409,"نام سیاست تکراری است") from exc


@router.get("/commerce")
def commerce(admin=Depends(current_admin)):
    with db.conn() as con:
        summary = db.dashboard_stats()
        payments = [dict(r) for r in con.execute("SELECT * FROM payments ORDER BY id DESC LIMIT 100")]
        licenses = [dict(r) for r in con.execute("""SELECT l.id,l.telegram_id,l.plan_code,l.status,l.starts_at,l.expires_at,l.vip_access,l.autotrade_access,u.username,u.first_name
          FROM licenses l LEFT JOIN users u ON u.telegram_id=l.telegram_id ORDER BY l.id DESC LIMIT 100""")]
        plans = [dict(r) for r in con.execute("SELECT * FROM subscription_plans ORDER BY sort_order,code")]
        discounts = [dict(r) for r in con.execute("SELECT * FROM discounts ORDER BY id DESC LIMIT 100")]
    return {"summary":summary,"payments":payments,"licenses":licenses,"plans":plans,"discounts":discounts}


class LicenseAction(BaseModel):
    action: str = Field(pattern="^(SUSPEND|ACTIVATE|EXTEND)$")
    days: int = Field(default=30, ge=1, le=730)


@router.post("/commerce/licenses/{license_id}/action")
def license_action(license_id:int,req:LicenseAction,admin=Depends(require("ADMIN"))):
    with db.conn() as con:
        row=con.execute("SELECT * FROM licenses WHERE id=?",(license_id,)).fetchone()
        if not row: raise HTTPException(404,"لایسنس پیدا نشد")
        if req.action=="SUSPEND": con.execute("UPDATE licenses SET status='suspended' WHERE id=?",(license_id,))
        elif req.action=="ACTIVATE": con.execute("UPDATE licenses SET status='active' WHERE id=?",(license_id,))
        else:
            expiry=max(_utcnow(),datetime.fromisoformat(row["expires_at"]))+timedelta(days=req.days)
            con.execute("UPDATE licenses SET status='active',expires_at=?,vip_expires_at=CASE WHEN vip_access=1 THEN ? ELSE vip_expires_at END,autotrade_expires_at=CASE WHEN autotrade_access=1 THEN ? ELSE autotrade_expires_at END WHERE id=?",(expiry.isoformat(),expiry.isoformat(),expiry.isoformat(),license_id))
    _audit(admin,"license_action",license_id,req.action)
    return {"ok":True}


@router.get("/communications")
def communications(admin=Depends(current_admin)):
    with db.conn() as con:
        tickets=[dict(r) for r in con.execute("SELECT t.*,u.username,u.first_name FROM support_tickets t LEFT JOIN users u ON u.telegram_id=t.telegram_id ORDER BY CASE t.priority WHEN 'URGENT' THEN 0 WHEN 'HIGH' THEN 1 ELSE 2 END,t.id DESC LIMIT 100")]
        templates=[dict(r) for r in con.execute("SELECT * FROM message_templates ORDER BY id DESC")]
        jobs=[dict(r) for r in con.execute("SELECT * FROM web_notification_jobs ORDER BY id DESC LIMIT 100")]
    return {"tickets":tickets,"templates":templates,"jobs":jobs}


class TemplateWrite(BaseModel):
    name:str=Field(min_length=2,max_length=80)
    channel:str=Field(pattern="^(TELEGRAM|EMAIL|PUSH)$")
    body:str=Field(min_length=2,max_length=10000)


@router.post("/communications/templates",status_code=201)
def create_template(req:TemplateWrite,admin=Depends(require("ADMIN","MODERATOR"))):
    with db.conn() as con:
        con.execute("""INSERT INTO message_templates(name,channel,body,updated_by,updated_at) VALUES(?,?,?,?,?)
          ON CONFLICT(name) DO UPDATE SET channel=excluded.channel,body=excluded.body,updated_by=excluded.updated_by,updated_at=excluded.updated_at""",(req.name,req.channel,req.body,admin["id"],db.now_iso()))
    return {"ok":True}


@router.get("/security-center")
def security_center(admin=Depends(require("ADMIN"))):
    with db.conn() as con:
        admins=[dict(r) for r in con.execute("SELECT id,username,display_name,role,active,failed_attempts,locked_until,last_login_at,created_at FROM web_admins")]
        audits=[dict(r) for r in con.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 200")]
        controls=[dict(r) for r in con.execute("SELECT * FROM system_controls")]
    backup_dir=db.DB_PATH.parent/"artifacts"/"backups"
    backups=[{"name":p.name,"size":p.stat().st_size,"created_at":datetime.fromtimestamp(p.stat().st_mtime,timezone.utc).isoformat()} for p in sorted(backup_dir.glob("nexus-*.db"),reverse=True)[:20]] if backup_dir.exists() else []
    return {"admins":admins,"audits":audits,"controls":controls,"backups":backups,"checks":{"secret_configured":len(os.getenv("ADMIN_WEB_SECRET",""))>=32,"https_required":True,"cors_origins":len(os.getenv("ADMIN_WEB_ORIGINS","" ).split(",")),"database_wal":True}}


@router.post("/security-center/backups",status_code=201)
def create_backup(admin=Depends(require("ADMIN"))):
    import shutil
    folder=db.DB_PATH.parent/"artifacts"/"backups";folder.mkdir(parents=True,exist_ok=True)
    target=folder/f"nexus-{_utcnow().strftime('%Y%m%d-%H%M%S')}.db"
    shutil.copy2(db.DB_PATH,target)
    _audit(admin,"database_backup_created",None,target.name)
    return {"ok":True,"name":target.name,"size":target.stat().st_size}


@router.websocket("/ws")
async def websocket_updates(websocket: WebSocket, token: str = Query("")):
    try:
        payload = _decode_token(token)
        with db.conn() as con: active = con.execute("SELECT active FROM web_admins WHERE id=?", (payload["sub"],)).fetchone()
        if not active or not active["active"]: raise HTTPException(401)
    except HTTPException:
        await websocket.close(code=4401); return
    await websocket.accept()
    try:
        last = None
        while True:
            with db.conn() as con:
                state = dict(con.execute("SELECT COUNT(*) signals,MAX(updated) updated FROM (SELECT id,COALESCE(closed_at,created_at) updated FROM signals)").fetchone())
                state["online_experts"] = con.execute("SELECT COUNT(*) FROM autotrade_mt5_accounts WHERE last_seen_at>=datetime('now','-2 minutes')").fetchone()[0]
            marker = json.dumps(state, sort_keys=True)
            if marker != last:
                await websocket.send_json({"type": "system:update", "data": state, "at": db.now_iso()}); last = marker
            await asyncio.sleep(5)
    except (WebSocketDisconnect, RuntimeError):
        return
