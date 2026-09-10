from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from pathlib import Path
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient

from app import db
from app.config import settings
from app.miniapp_admin_api import calculate_auto_targets


ADMIN_ID = 9001001
ACCOUNT = "80150619"


def signed_init_data(user_id: int = ADMIN_ID, *, auth_date: int | None = None) -> str:
    values = {
        "auth_date": str(int(time.time()) if auth_date is None else int(auth_date)),
        "query_id": "AAE-miniapp-admin-test",
        "user": json.dumps({"id": user_id, "first_name": "Admin"}, separators=(",", ":")),
    }
    check = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret = hmac.new(b"WebAppData", settings.bot_token.encode(), hashlib.sha256).digest()
    values["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(values)


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "miniapp-admin.db")
    old_admin_ids = settings.admin_ids
    old_accounts = settings.nexus_admin_mt5_accounts
    old_admin_token = settings.nexus_admin_token
    object.__setattr__(settings, "admin_ids", (ADMIN_ID,))
    object.__setattr__(settings, "nexus_admin_mt5_accounts", (ACCOUNT,))
    object.__setattr__(settings, "nexus_admin_token", "miniapp-test-admin-token")
    from app.autotrade.api import app
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        object.__setattr__(settings, "admin_ids", old_admin_ids)
        object.__setattr__(settings, "nexus_admin_mt5_accounts", old_accounts)
        object.__setattr__(settings, "nexus_admin_token", old_admin_token)


def headers():
    return {"X-Telegram-Init-Data": signed_init_data()}


def payload(request_id="miniapp-test-0001", destination="BOTH"):
    return {"symbol": "XAUUSD", "direction": "BUY", "entry": 3650,
            "stop_loss": 3645, "destination": destination, "request_id": request_id,
            "timeframe": "M5", "digits": 2}


def chart_headers():
    return {"X-MT5-Account": ACCOUNT, "X-NEXUS-Admin-Token": "miniapp-test-admin-token"}


def claim_job(client, request_id="chart-job-request"):
    db.ensure_admin_identity(ADMIN_ID)
    db.record_mt5_heartbeat(ACCOUNT, role="ADMIN", ea_version="0.6.5", payload={"ok": True})
    created = client.post("/miniapp/api/admin/signals", headers=headers(), json=payload(request_id)).json()
    claimed = client.get("/api/v1/autotrade/admin/chart-capture/next", headers=chart_headers())
    assert claimed.status_code == 200, claimed.text
    return created, claimed.json()["job"]


def test_buy_tp_calculation():
    result = calculate_auto_targets("XAUUSD", "BUY", 3650, 3645, 2)
    assert result["risk"] == 5
    assert result["targets"] == [3655, 3657.5, 3660, 3665]


def test_sell_tp_calculation():
    result = calculate_auto_targets("XAUUSD", "SELL", 3650, 3655, 2)
    assert result["targets"] == [3645, 3642.5, 3640, 3635]


@pytest.mark.parametrize("direction,entry,stop", [("BUY", 10, 11), ("SELL", 10, 9)])
def test_invalid_sl_validation(direction, entry, stop):
    with pytest.raises(ValueError):
        calculate_auto_targets("EURUSD", direction, entry, stop, 5)


def test_zero_risk_rejection():
    with pytest.raises(ValueError, match="non-zero risk"):
        calculate_auto_targets("XAUUSD", "BUY", 3650, 3650, 2)


def test_target_ordering():
    buy = calculate_auto_targets("EURUSD", "BUY", 1.1, 1.09, 5)["targets"]
    sell = calculate_auto_targets("EURUSD", "SELL", 1.1, 1.11, 5)["targets"]
    assert buy == sorted(buy)
    assert sell == sorted(sell, reverse=True)


def test_miniapp_signal_creation_and_backend_preserves_targets(client):
    response = client.post("/miniapp/api/admin/signals", headers=headers(), json=payload())
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["targets"] == [3655, 3657.5, 3660, 3665]
    stored = db.get_signal_targets(body["signal_id"])
    assert [float(row["price"]) for row in stored] == body["targets"]


def test_duplicate_publish_prevention(client):
    first = client.post("/miniapp/api/admin/signals", headers=headers(), json=payload("same-request-id"))
    second = client.post("/miniapp/api/admin/signals", headers=headers(), json=payload("same-request-id"))
    assert first.status_code == second.status_code == 201
    assert second.json()["idempotent"] is True
    with db.conn() as con:
        assert con.execute("SELECT COUNT(*) FROM miniapp_admin_signal_requests").fetchone()[0] == 1


def test_mt5_offline_handling(client):
    response = client.post("/miniapp/api/admin/signals", headers=headers(), json=payload("offline-request"))
    assert response.json()["status"] == "WAITING_FOR_MT5"
    assert response.json()["signal"]["status"] == "DRAFT"
    assert not response.json()["signal"]["free_message_id"]
    assert not response.json()["signal"]["vip_message_id"]


def test_mt5_online_publish_flow_enters_ready(client):
    db.ensure_admin_identity(ADMIN_ID)
    db.record_mt5_heartbeat(ACCOUNT, role="ADMIN", ea_version="0.6.5", payload={"ok": True})
    response = client.post("/miniapp/api/admin/signals", headers=headers(), json=payload("online-request"))
    assert response.status_code == 201
    assert response.json()["status"] == "READY"
    assert response.json()["chart_job"]["status"] == "PENDING"


@pytest.mark.parametrize("destination", ["FREE", "VIP", "BOTH"])
def test_destination_is_preserved(client, destination):
    response = client.post("/miniapp/api/admin/signals", headers=headers(),
                           json=payload(f"destination-{destination.lower()}", destination))
    assert response.status_code == 201
    assert response.json()["signal"]["destination"] == destination


def test_existing_client_ea_compatibility_is_preserved():
    source = Path("app/db.py").read_text(encoding="utf-8")
    assert "issuer_type IN ('MT5_ADMIN','WEB_ADMIN')" in source
    chart_agent = Path("mt5/NEXUS_ChartAgent/NEXUS_ChartAgent.mq5").read_text(encoding="utf-8")
    assert "/api/v1/autotrade/admin/chart-capture/next" in chart_agent
    assert '\\"image_base64\\"' in chart_agent


def test_existing_trailing_engine_compatibility_is_preserved():
    source = Path("mt5/NEXUS_AutoTrade_UI65/Core/Include/TrailingEngine.mqh").read_text(encoding="utf-8")
    assert "NEXUS_TRAIL" in source
    api = Path("app/autotrade/api.py").read_text(encoding="utf-8")
    assert "_publish_mt5_admin_signal_async" in api


def test_admin_only_authentication(client):
    unauthorized_id = ADMIN_ID + 1234567
    response = client.get("/miniapp/api/admin/bootstrap", headers={"X-Telegram-Init-Data": signed_init_data(unauthorized_id)})
    assert response.status_code == 403


def test_expired_and_tampered_init_data_are_rejected(client):
    expired = signed_init_data(auth_date=int(time.time()) - 90_000)
    assert client.get("/miniapp/api/admin/bootstrap", headers={"X-Telegram-Init-Data": expired}).status_code == 401
    tampered = signed_init_data().replace("Admin", "Attacker")
    assert client.get("/miniapp/api/admin/bootstrap", headers={"X-Telegram-Init-Data": tampered}).status_code == 401


def test_ui_keeps_tp_inputs_automatic():
    html = Path("miniapp/admin.html").read_text(encoding="utf-8")
    js = Path("miniapp/admin-signal.js").read_text(encoding="utf-8")
    assert "اهداف خودکار" in html
    assert "/signals/calculate" in js
    assert 'id="tp1"' not in html.lower()


def test_ui_exposes_existing_mt5_position_commands():
    js = Path("miniapp/admin-signal.js").read_text(encoding="utf-8")
    for command in ("MOVE_SL_TO_ENTRY", "PARTIAL_CLOSE", "ACTIVATE_TRAILING", "UPDATE_SL", "UPDATE_TP", "CLOSE_SIGNAL", "CANCEL_PENDING"):
        assert command in js


def test_chart_agent_legacy_and_new_poll_routes(client):
    _, job = claim_job(client, "legacy-poll-route")
    assert job["job_id"] > 0
    response = client.get("/api/v1/autotrade/admin/chart-capture/jobs/next", headers=chart_headers())
    assert response.status_code == 200
    assert response.json()["job"] is None


@pytest.mark.parametrize("field", ["image_base64", "chart_base64"])
def test_chart_upload_accepts_legacy_and_new_image_fields(client, monkeypatch, field):
    from app.autotrade import api

    async def no_publish(*_args, **_kwargs):
        return {"complete": True}

    monkeypatch.setattr(api, "_publish_mt5_admin_signal_async", no_publish)
    _, job = claim_job(client, f"upload-{field}")
    image = b"\x89PNG\r\n\x1a\n" + (b"NEXUS" * 900)
    body = {
        "signal_db_id": job["signal_db_id"], "signal_code": job["signal_code"],
        "broker_symbol": job["symbol"], "timeframe": job["timeframe"],
        field: base64.b64encode(image).decode(), "image_sha256": hashlib.sha256(image).hexdigest(),
    }
    response = client.post(
        f"/api/v1/autotrade/admin/chart-capture/{job['job_id']}/result",
        headers=chart_headers(), json=body,
    )
    assert response.status_code == 200, response.text
    assert response.json()["idempotent"] is False

    duplicate = client.post(
        f"/api/v1/autotrade/admin/chart-capture/{job['job_id']}/result",
        headers=chart_headers(), json=body,
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["idempotent"] is True


def test_legacy_failure_payload_and_retry(client):
    created, job = claim_job(client, "legacy-failure-retry")
    failed = client.post(
        f"/api/v1/autotrade/admin/chart-capture/{job['job_id']}/fail",
        headers=chart_headers(), json={"error_code": "CAPTURE_FAILED", "error_text": "chart unavailable"},
    )
    assert failed.status_code == 200, failed.text
    with db.conn() as con:
        con.execute(
            "UPDATE signal_chart_capture_jobs SET status='FAILED' WHERE id=?", (job["job_id"],)
        )
    retried = client.post(
        f"/miniapp/api/admin/signals/{created['request_id']}/retry", headers=headers()
    )
    assert retried.status_code == 200, retried.text
    assert retried.json()["chart_job"]["status"] == "PENDING"


def test_web_admin_position_commands_are_allowed(client):
    created = client.post(
        "/miniapp/api/admin/signals", headers=headers(), json=payload("web-admin-command")
    ).json()
    response = client.post(
        f"/miniapp/api/admin/signals/{created['signal_id']}/command", headers=headers(),
        json={"command": "MOVE_SL_TO_ENTRY", "account_number": ACCOUNT},
    )
    assert response.status_code == 200, response.text
    assert response.json()["command"] == "MOVE_SL_TO_ENTRY"


def test_production_user_and_admin_miniapps_are_both_served(client):
    import app.combined_api  # registers the current Production user Mini App and shared static mount

    user_app = client.get("/miniapp/")
    admin_app = client.get("/miniapp/admin.html")
    assert user_app.status_code == 200
    assert admin_app.status_code == 200
    assert "NEXUS Admin Signal Center" in admin_app.text
