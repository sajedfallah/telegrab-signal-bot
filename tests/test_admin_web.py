from pathlib import Path

from fastapi.testclient import TestClient

from app import db
from app.admin_api import init_admin_schema
from app.autotrade.api import app
from app.config import settings


def test_admin_web_auth_dashboard_and_signal_crud(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "admin-test.db")
    monkeypatch.setenv("ADMIN_WEB_USERNAME", "test-admin")
    monkeypatch.setenv("ADMIN_WEB_PASSWORD", "correct-horse-battery-staple")
    monkeypatch.setenv("ADMIN_WEB_SECRET", "x" * 48)
    db.init_db()
    init_admin_schema()

    with TestClient(app) as client:
        login = client.post(
            "/api/v1/admin-web/auth/login",
            json={"username": "test-admin", "password": "correct-horse-battery-staple"},
        )
        assert login.status_code == 200
        headers = {"Authorization": f"Bearer {login.json()['token']}"}

        dashboard = client.get("/api/v1/admin-web/dashboard", headers=headers)
        assert dashboard.status_code == 200
        assert dashboard.json()["signals"]["total"] == 0
        options = client.get("/api/v1/admin-web/signals/options", headers=headers)
        assert options.status_code == 200
        assert "XAUUSD" in options.json()["symbols"]["GOLD"]
        assert len(options.json()["trailing"]) == 7

        created = client.post(
            "/api/v1/admin-web/signals",
            headers=headers,
            json={
                "market_type": "GOLD",
                "symbol": "XAUUSD",
                "direction": "BUY",
                "entry_price": 2300,
                "stop_loss": 2290,
                "targets": [2310, 2320],
                "risk_percent": 1,
                "destination": "BOTH",
            },
        )
        assert created.status_code == 201
        signal_id = created.json()["id"]
        assert client.patch(
            f"/api/v1/admin-web/signals/{signal_id}",
            headers=headers,
            json={"status": "CANCELED"},
        ).status_code == 200
        assert client.delete(
            f"/api/v1/admin-web/signals/{signal_id}", headers=headers
        ).status_code == 204

        fixed = client.post("/api/v1/admin-web/signals", headers=headers, json={
            "market_type":"FOREX","symbol":"EURUSD","direction":"SELL","entry_price":1.1,
            "stop_loss":1.11,"targets":[1.09],"volume_mode":"FIXED","risk_percent":0,
            "lot_size":0.05,"destination":"VIP","order_type":"MARKET",
            "trailing_code":"NEXUS_TRAIL_07","max_entry_deviation_pct":0.2,
        })
        assert fixed.status_code == 201
        fixed_row = db.get_signal(fixed.json()["id"])
        assert fixed_row["volume_mode"] == "FIXED"
        assert fixed_row["trailing_code"] == "NEXUS_TRAIL_07"

        published = client.post("/api/v1/admin-web/signals", headers=headers, json={
            "market_type":"GOLD","symbol":"XAUUSD","direction":"BUY","entry_price":2300,
            "stop_loss":2290,"targets":[2310],"risk_percent":1,"destination":"BOTH",
            "chart_base64":"data:image/png;base64,iVBORw0KGgo=","publish":True,
            "issuer_account":settings.nexus_admin_mt5_accounts[0],
        })
        assert published.status_code == 201
        assert published.json()["status"] == "ACTIVE"
        assert published.json()["publication"]["status"] == "WAITING_EXECUTION"
        assert db.get_mt5_signal_publication_asset(published.json()["id"])

        assert client.get("/api/v1/admin-web/reports", headers=headers).status_code == 200
        xlsx = client.get("/api/v1/admin-web/reports/export.xlsx", headers=headers)
        assert xlsx.status_code == 200
        assert xlsx.content.startswith(b"PK")

        db.upsert_user(900001, "portal_user", "کاربر تست")
        with db.conn() as con:
            con.execute(
                """INSERT INTO licenses(telegram_id,license_key,plan_code,source,vip_access,autotrade_access,starts_at,expires_at,vip_expires_at,autotrade_expires_at,status,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (900001, "NXS-PORTAL-TEST-KEY", "AUTO1M", "test", 1, 1,
                 db.now_iso(), "2099-01-01T00:00:00+00:00", "2099-01-01T00:00:00+00:00",
                 "2099-01-01T00:00:00+00:00", "active", db.now_iso()),
            )
        portal_login = client.post("/api/v1/admin-web/portal/auth/login", json={"telegram_id": 900001, "license_key": "NXS-PORTAL-TEST-KEY"})
        assert portal_login.status_code == 200
        portal_headers = {"Authorization": f"Bearer {portal_login.json()['token']}"}
        overview = client.get("/api/v1/admin-web/portal/overview", headers=portal_headers)
        assert overview.status_code == 200
        assert overview.json()["entitlements"]["vip"] is True
        risk = client.put(
            "/api/v1/admin-web/portal/risk-settings",
            headers=portal_headers,
            json={"management_mode": "SELF", "risk_percent": 1.5, "max_daily_loss": 4,
                  "max_open_trades": 2, "max_daily_trades": 8, "fixed_lot": None,
                  "emergency_stop": False},
        )
        assert risk.status_code == 200
        updated = client.get("/api/v1/admin-web/portal/overview", headers=portal_headers).json()
        assert updated["risk"]["management_mode"] == "SELF"
        assert updated["risk"]["risk_percent"] == 1.5
        for endpoint in ("operations", "risk-center", "commerce", "communications", "security-center"):
            assert client.get(f"/api/v1/admin-web/{endpoint}", headers=headers).status_code == 200
        assert client.put("/api/v1/admin-web/operations/controls/NEW_ENTRIES", headers=headers,
                          json={"enabled": True, "scope": "GLOBAL", "reason": "test"}).status_code == 200
        assert client.post("/api/v1/admin-web/security-center/backups", headers=headers).status_code == 201


def test_admin_web_rejects_unauthenticated_access(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "unauth-test.db")
    db.init_db()
    init_admin_schema()
    with TestClient(app) as client:
        assert client.get("/api/v1/admin-web/users").status_code == 401
