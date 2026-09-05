import hashlib
import hmac
import json
import time
from pathlib import Path
from urllib.parse import urlencode

from fastapi.testclient import TestClient

from app import db
from app.admin_api import init_admin_schema
from app.autotrade.api import app
from app.config import settings
from app.miniapp_api import validate_init_data


def signed_init_data(user: dict, auth_date: int | None = None) -> str:
    values = {"auth_date": str(auth_date or int(time.time())), "query_id": "test-query", "user": json.dumps(user, separators=(",", ":"))}
    check = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret = hmac.new(b"WebAppData", settings.bot_token.encode(), hashlib.sha256).digest()
    values["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(values)


def test_telegram_init_data_signature_and_expiry():
    raw = signed_init_data({"id": 880001, "first_name": "Mini", "username": "mini_user"})
    assert validate_init_data(raw)["id"] == 880001
    try:
        validate_init_data(raw.replace("mini_user", "attacker"))
        assert False, "tampered initData must fail"
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 401


def test_miniapp_user_session_risk_support_and_admin_guard(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "miniapp.db")
    monkeypatch.setenv("MINIAPP_DEV_BYPASS", "true")
    monkeypatch.setenv("MINIAPP_DEV_USER_ID", "990000001")
    db.init_db(); init_admin_schema()
    db.create_plan("TEST30", 30, "آزمایشی", "Test", usdt_price="10", vip_access=True, autotrade_access=False, service_type="signal")
    db.create_plan("AUTO30", 30, "اتوترید", "Auto", usdt_price="20", vip_access=False, autotrade_access=True, service_type="auto_trade")
    db.create_plan("BUNDLE30", 30, "ترکیبی", "Bundle", usdt_price="25", vip_access=True, autotrade_access=True, service_type="auto_trade")
    for destination in ("FREE", "VIP"):
        db.create_signal(market_type="GOLD", symbol="XAUUSD", direction="BUY", entry_price=2400, stop_loss=2390,
                         targets=[2410], risk_percent=1, rr_ratio=1, destination=destination,
                         chart_file_id=None, created_by=1)
    with TestClient(app) as client:
        session = client.get("/api/v1/miniapp/session")
        assert session.status_code == 200
        assert session.json()["user"]["telegram_id"] == 990000001
        signals = client.get("/api/v1/miniapp/signals")
        assert signals.status_code == 200
        assert len(signals.json()["items"]) == 2
        assert next(x for x in signals.json()["items"] if x["destination"] == "VIP")["locked"] is True
        assert next(x for x in signals.json()["items"] if x["destination"] == "FREE")["entry_price"] == 2400
        commerce = client.get("/api/v1/miniapp/commerce")
        assert commerce.status_code == 200
        assert {x["category"] for x in commerce.json()["plans"]} == {"vip", "autotrade", "bundle"}
        plan = commerce.json()["plans"][0]
        payment = client.post("/api/v1/miniapp/payments", json={"plan_code": plan["code"], "method": "USDT", "reference": "miniapp-test-tx-001"})
        assert payment.status_code == 201
        assert payment.json()["status"] == "pending"
        risk = client.put("/api/v1/miniapp/risk", json={"management_mode":"SELF","risk_percent":1.2,"max_daily_loss":3,"max_open_trades":2,"max_daily_trades":8,"fixed_lot":None,"emergency_stop":False})
        assert risk.status_code == 200
        support = client.post("/api/v1/miniapp/support", json={"subject":"Test","message":"Mini App support request","priority":"NORMAL"})
        assert support.status_code == 201
        assert client.get("/api/v1/miniapp/support").json()["items"][0]["subject"] == "Test"
        expected = 200 if 990000001 in settings.admin_ids else 403
        assert client.get("/api/v1/miniapp/admin/overview").status_code == expected


def test_miniapp_rejects_requests_without_telegram_identity(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "miniapp-auth.db")
    monkeypatch.delenv("MINIAPP_DEV_BYPASS", raising=False)
    db.init_db(); init_admin_schema()
    with TestClient(app) as client:
        assert client.get("/api/v1/miniapp/session").status_code == 401


def test_miniapp_admin_parity_endpoints(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "miniapp-admin.db")
    monkeypatch.setenv("MINIAPP_DEV_BYPASS", "true")
    monkeypatch.setenv("MINIAPP_DEV_USER_ID", str(settings.admin_ids[0]))
    db.init_db(); init_admin_schema()
    db.create_plan("VIP30", 30, "وی‌آی‌پی", "VIP", usdt_price="10", vip_access=True, autotrade_access=False, service_type="signal")
    with TestClient(app) as client:
        data = client.get("/api/v1/miniapp/admin/data")
        assert data.status_code == 200
        assert {"users", "payments", "plans", "discounts", "campaigns", "leaderboard", "waitlist", "tickets", "risk", "accounts", "audit"} <= set(data.json())
        assert client.put("/api/v1/miniapp/admin/settings", json={"key":"usdt_irr_rate", "value":"650000"}).status_code == 200
        assert client.put("/api/v1/miniapp/admin/plans/VIP30", json={"price_usdt":"12"}).status_code == 200
        assert client.post("/api/v1/miniapp/admin/discounts", json={"code":"MINI20", "percent":20, "expires_days":30}).status_code == 201
        assert client.post("/api/v1/miniapp/admin/campaigns", json={"title_fa":"کمپین تست", "title_en":"Test", "percent":10, "days":7, "audience":"all"}).status_code == 201
