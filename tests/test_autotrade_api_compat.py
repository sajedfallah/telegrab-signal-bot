import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from app import db
from app.autotrade.api import app


def test_mt5_get_compat_activate_and_check():
    old = db.DB_PATH
    with tempfile.TemporaryDirectory() as td:
        db.DB_PATH = Path(td) / "api.db"
        db.init_db()
        db.upsert_user(9001, "mt5", "MT5")
        lic = db.create_or_extend_license(9001, None, 30, source="test", autotrade_access=True, vip_access=False)
        key = str(lic["license_key"])
        headers = {
            "X-License-Key": key,
            "X-MT5-Account": "50254",
            "X-Broker": "RoboBroker-Ltd",
            "X-Server": "Demo",
            "X-EA-Version": "0.3.1",
        }
        try:
            with TestClient(app) as client:
                r = client.get("/api/v1/autotrade/activate", headers=headers)
                assert r.status_code == 200, r.text
                assert r.json()["license_status"] == "ACTIVE"
                r2 = client.get("/api/v1/autotrade/license/check", headers=headers)
                assert r2.status_code == 200, r2.text
                assert r2.json()["allow_new_trade"] is True
        finally:
            db.DB_PATH = old


def test_receipt_post_rejects_unknown_status_and_accepts_retryable():
    old = db.DB_PATH
    with tempfile.TemporaryDirectory() as td:
        db.DB_PATH = Path(td) / "api.db"
        db.init_db()
        db.upsert_user(9002, "mt5", "MT5")
        lic = db.create_or_extend_license(9002, None, 30, source="test", autotrade_access=True, vip_access=False)
        signal = db.create_signal(
            market_type="FOREX", symbol="EURUSD", direction="BUY", entry_price=1.10,
            stop_loss=1.09, targets=[1.12], risk_percent=1.0, rr_ratio=2.0,
            destination="VIP", chart_file_id=None, created_by=9002,
        )
        db.set_signal_publish_messages(int(signal["id"]), None, 12345)
        key = str(lic["license_key"])
        headers = {"X-License-Key": key, "X-MT5-Account": "50255"}
        try:
            with TestClient(app) as client:
                activated = client.get(
                    "/api/v1/autotrade/activate",
                    headers={**headers, "X-EA-Version": "0.4.5"},
                )
                assert activated.status_code == 200, activated.text
                bad = client.post(
                    "/api/v1/autotrade/signal-receipt",
                    headers=headers,
                    json={"license_key": key, "account_number": "50255", "signal_db_id": int(signal["id"]), "status": "unknown"},
                )
                assert bad.status_code == 422
                good = client.post(
                    "/api/v1/autotrade/signal-receipt",
                    headers=headers,
                    json={"license_key": key, "account_number": "50255", "signal_db_id": int(signal["id"]), "status": "failed_retryable"},
                )
                assert good.status_code == 200, good.text
        finally:
            db.DB_PATH = old
