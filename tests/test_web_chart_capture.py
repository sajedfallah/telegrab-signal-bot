from __future__ import annotations

import base64
import hashlib
from pathlib import Path

from fastapi.testclient import TestClient

from app import db
from app.admin_api import init_admin_schema
from app.autotrade.api import app
from app.config import settings


def _signal_payload(request_id: str = "web-e2e-request-01") -> dict:
    return {
        "market_type": "GOLD", "symbol": "XAUUSD", "timeframe": "M5",
        "direction": "BUY", "entry_price": 2300, "stop_loss": 2290,
        "targets": [2310, 2320, 2330], "risk_percent": 1,
        "volume_mode": "RISK", "destination": "VIP",
        "order_type": "MARKET", "trailing_code": "NEXUS_TRAIL_07",
        "issuer_account": "70001", "request_id": request_id,
    }


def test_web_signal_job_claim_security_and_idempotent_upload(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "chart-jobs.db")
    monkeypatch.setenv("ADMIN_WEB_USERNAME", "chart-admin")
    monkeypatch.setenv("ADMIN_WEB_PASSWORD", "correct-horse-battery-staple")
    monkeypatch.setenv("ADMIN_WEB_SECRET", "s" * 48)
    old_accounts, old_token = settings.nexus_admin_mt5_accounts, settings.nexus_admin_token
    object.__setattr__(settings, "nexus_admin_mt5_accounts", ("70001", "70002"))
    object.__setattr__(settings, "nexus_admin_token", "test-admin-mt5-token")
    try:
        db.init_db(); init_admin_schema()
        with TestClient(app) as client:
            login = client.post("/api/v1/admin-web/auth/login", json={"username": "chart-admin", "password": "correct-horse-battery-staple"})
            web_headers = {"Authorization": f"Bearer {login.json()['token']}"}
            first = client.post("/api/v1/admin-web/signals", headers=web_headers, json=_signal_payload())
            second = client.post("/api/v1/admin-web/signals", headers=web_headers, json=_signal_payload())
            assert first.status_code == 201
            assert second.status_code == 201
            assert first.json()["id"] == second.json()["id"]
            assert first.json()["code"] == "NX-01"
            assert second.json()["idempotent"] is True
            assert first.json()["publication_stage"] == "WAITING_FOR_CHART"

            assert client.get("/api/v1/autotrade/admin/chart-capture/jobs/next", headers={"X-MT5-Account": "70001"}).status_code == 403
            admin_headers = {"X-MT5-Account": "70001", "X-NEXUS-Admin-Token": "test-admin-mt5-token"}
            claimed = client.get("/api/v1/autotrade/admin/chart-capture/jobs/next", headers=admin_headers)
            assert claimed.status_code == 200
            job = claimed.json()["job"]
            assert job["signal_code"] == "NX-01"
            assert job["targets"] == [2310.0, 2320.0, 2330.0]

            other_headers = {"X-MT5-Account": "70002", "X-NEXUS-Admin-Token": "test-admin-mt5-token"}
            assert client.get("/api/v1/autotrade/admin/chart-capture/jobs/next", headers=other_headers).json()["job"] is None

            raw = b"\x89PNG\r\n\x1a\n" + b"x" * 5000
            digest = hashlib.sha256(raw).hexdigest()
            result = {
                "job_id": job["job_id"], "signal_db_id": job["signal_db_id"], "signal_code": job["signal_code"],
                "account_number": "70001", "broker_symbol": "XAUUSD.ec", "timeframe": "M5",
                "chart_base64": base64.b64encode(raw).decode(), "capture_timestamp": "2026-09-05T01:00:00Z",
                "image_sha256": digest,
            }
            uploaded = client.post(f"/api/v1/autotrade/admin/chart-capture/{job['job_id']}/result", headers=admin_headers, json=result)
            duplicate = client.post(f"/api/v1/autotrade/admin/chart-capture/{job['job_id']}/result", headers=admin_headers, json=result)
            assert uploaded.status_code == 200
            assert duplicate.status_code == 200
            assert duplicate.json()["idempotent"] is True
            assert db.get_signal_chart_capture_job(job["signal_db_id"])["image_sha256"] == digest
    finally:
        object.__setattr__(settings, "nexus_admin_mt5_accounts", old_accounts)
        object.__setattr__(settings, "nexus_admin_token", old_token)


def test_chart_job_retry_and_static_mt5_contract(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "retry.db")
    db.init_db(); db.upsert_user(1, "admin", "Admin")
    row = db.create_signal(market_type="GOLD", symbol="XAUUSD", direction="BUY", entry_price=2300,
        stop_loss=2290, targets=[2310], risk_percent=1, rr_ratio=None, destination="FREE",
        chart_file_id=None, created_by=1, timeframe="M5", publish_token="WEB:test")
    with db.conn() as con:
        con.execute("UPDATE signals SET issuer_type='WEB_ADMIN',issuer_account='70001' WHERE id=?", (int(row["id"]),))
    job = db.create_chart_capture_job(int(row["id"]), "WEB_ADMIN:1")
    claimed = db.claim_next_chart_capture_job("70001")
    assert claimed and int(claimed["id"]) == int(job["id"])
    retry = db.fail_chart_capture_job(int(job["id"]), "70001", "render failed")
    assert retry["status"] == "PENDING"
    assert retry["attempt_count"] == 1

    root = Path(__file__).resolve().parents[1]
    ea = (root / "mt5/NEXUS_AutoTrade/NEXUS_AutoTrade.mq5").read_text(encoding="utf-8")
    api = (root / "mt5/NEXUS_AutoTrade/Include/APIClient.mqh").read_text(encoding="utf-8")
    assert "PollChartCaptureJobs();" in ea and "void OnTimer()" in ea
    assert "NXS.SHOT." in ea
    assert "HideNexusUiForScreenshot(chart_id,hidden);" in ea
    assert "DeleteShotObjects(chart_id,prefix);" in ea
    assert "RestoreNexusUiAfterScreenshot(chart_id,hidden);" in ea
    assert "ChartScreenShot(chart_id,filename,1280,720,ALIGN_RIGHT)" in ea
    assert "/api/v1/autotrade/admin/chart-capture/jobs/next" in api
