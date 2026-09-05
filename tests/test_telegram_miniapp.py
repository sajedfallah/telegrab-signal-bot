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
    db.create_plan("TEST30", 30, "آزمایشی", "Test", usdt_price="10", service_type="signal")
    with TestClient(app) as client:
        session = client.get("/api/v1/miniapp/session")
        assert session.status_code == 200
        assert session.json()["user"]["telegram_id"] == 990000001
        assert client.get("/api/v1/miniapp/signals").status_code == 200
        commerce = client.get("/api/v1/miniapp/commerce")
        assert commerce.status_code == 200
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
