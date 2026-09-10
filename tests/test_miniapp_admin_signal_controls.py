from __future__ import annotations

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
from app.miniapp_admin_api import calculate_signal_levels


ADMIN_ID = 9002002
ACCOUNT = "80150619"


def signed_init_data(user_id: int = ADMIN_ID) -> str:
    values = {
        "auth_date": str(int(time.time())),
        "query_id": "AAE-miniapp-admin-controls",
        "user": json.dumps({"id": user_id, "first_name": "Admin"}, separators=(",", ":")),
    }
    check = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret = hmac.new(b"WebAppData", settings.bot_token.encode(), hashlib.sha256).digest()
    values["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(values)


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "miniapp-admin-controls.db")
    old_admin_ids = settings.admin_ids
    old_accounts = settings.nexus_admin_mt5_accounts
    old_token = settings.nexus_admin_token
    object.__setattr__(settings, "admin_ids", (ADMIN_ID,))
    object.__setattr__(settings, "nexus_admin_mt5_accounts", (ACCOUNT,))
    object.__setattr__(settings, "nexus_admin_token", "miniapp-controls-token")
    from app.autotrade.api import app
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        object.__setattr__(settings, "admin_ids", old_admin_ids)
        object.__setattr__(settings, "nexus_admin_mt5_accounts", old_accounts)
        object.__setattr__(settings, "nexus_admin_token", old_token)


def headers():
    return {"X-Telegram-Init-Data": signed_init_data()}


def test_auto_sl_requires_explicit_distance_and_resolves_by_direction():
    buy = calculate_signal_levels(
        "XAUUSD", "BUY", 3650,
        stop_loss_mode="AUTO", stop_distance=5,
        take_profit_mode="AUTO", digits=2,
    )
    sell = calculate_signal_levels(
        "XAUUSD", "SELL", 3650,
        stop_loss_mode="AUTO", stop_distance=5,
        take_profit_mode="AUTO", digits=2,
    )
    assert buy["stop_loss"] == 3645
    assert sell["stop_loss"] == 3655
    assert buy["targets"] == [3655, 3657.5, 3660, 3665]
    assert sell["targets"] == [3645, 3642.5, 3640, 3635]
    with pytest.raises(ValueError, match="stop_distance"):
        calculate_signal_levels("XAUUSD", "BUY", 3650, stop_loss_mode="AUTO")


def test_manual_tp_prices_are_preserved_and_validated():
    result = calculate_signal_levels(
        "XAUUSD", "BUY", 3650,
        stop_loss=3645,
        stop_loss_mode="MANUAL",
        take_profit_mode="MANUAL",
        targets=[3654, 3656, 3658, 3662],
        digits=2,
    )
    assert result["targets"] == [3654, 3656, 3658, 3662]
    assert result["target_multipliers"] == [0.8, 1.2, 1.6, 2.4]

    with pytest.raises(ValueError, match="strictly increasing"):
        calculate_signal_levels(
            "XAUUSD", "BUY", 3650,
            stop_loss=3645,
            take_profit_mode="MANUAL",
            targets=[3654, 3658, 3657, 3662],
            digits=2,
        )


def test_fixed_lot_and_custom_trailing_are_persisted(client):
    payload = {
        "symbol": "XAUUSD",
        "direction": "BUY",
        "entry": 3650,
        "stop_loss": 3645,
        "stop_loss_mode": "MANUAL",
        "take_profit_mode": "MANUAL",
        "targets": [3654, 3656, 3658, 3662],
        "destination": "BOTH",
        "request_id": "manual-fixed-trail-001",
        "timeframe": "M5",
        "volume_mode": "FIXED",
        "lot_size": 0.03,
        "trailing_enabled": True,
        "trailing_break_even_r": 1.0,
        "trailing_step_r": 0.5,
        "trailing_lock_r": 0.3,
        "digits": 2,
    }
    response = client.post("/miniapp/api/admin/signals", headers=headers(), json=payload)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["targets"] == [3654, 3656, 3658, 3662]

    signal = db.get_signal(body["signal_id"])
    assert signal["volume_mode"] == "FIXED"
    assert float(signal["lot_size"]) == 0.03
    assert float(signal["risk_percent"]) == 0.0
    assert signal["trailing_code"] == "NEXUS_TRAIL_01"
    config = json.loads(signal["trailing_config_json"])
    assert config["break_even_r"] == 1.0
    assert config["trail_step_r"] == 0.5
    assert config["lock_step_r"] == 0.3


def test_fixed_risk_and_auto_levels_are_persisted(client):
    payload = {
        "symbol": "XAUUSD",
        "direction": "SELL",
        "entry": 3650,
        "stop_loss_mode": "AUTO",
        "stop_distance": 5,
        "take_profit_mode": "AUTO",
        "destination": "VIP",
        "request_id": "auto-risk-001",
        "timeframe": "M5",
        "volume_mode": "RISK",
        "risk_percent": 1.25,
        "trailing_enabled": False,
        "digits": 2,
    }
    response = client.post("/miniapp/api/admin/signals", headers=headers(), json=payload)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["targets"] == [3645, 3642.5, 3640, 3635]

    signal = db.get_signal(body["signal_id"])
    assert float(signal["stop_loss"]) == 3655
    assert signal["volume_mode"] == "RISK"
    assert float(signal["risk_percent"]) == 1.25
    assert signal["lot_size"] is None
    assert signal["trailing_code"] is None


def test_invalid_fixed_lot_and_aggressive_trailing_are_rejected(client):
    base = {
        "symbol": "XAUUSD", "direction": "BUY", "entry": 3650, "stop_loss": 3645,
        "destination": "BOTH", "timeframe": "M5", "digits": 2,
    }
    missing_lot = client.post(
        "/miniapp/api/admin/signals", headers=headers(),
        json={**base, "request_id": "bad-fixed-lot", "volume_mode": "FIXED"},
    )
    assert missing_lot.status_code == 422

    invalid_trail = client.post(
        "/miniapp/api/admin/signals", headers=headers(),
        json={
            **base,
            "request_id": "bad-trailing-lock",
            "volume_mode": "RISK",
            "risk_percent": 1,
            "trailing_enabled": True,
            "trailing_break_even_r": 1,
            "trailing_step_r": 0.25,
            "trailing_lock_r": 0.5,
        },
    )
    assert invalid_trail.status_code == 422
    assert "lock step" in invalid_trail.json()["detail"]


def test_admin_ui_exposes_new_control_surface():
    html = Path("miniapp/admin.html").read_text(encoding="utf-8")
    js = Path("miniapp/admin-signal.js").read_text(encoding="utf-8")
    css = Path("miniapp/admin-signal.css").read_text(encoding="utf-8")

    for marker in (
        'id="slMode"', 'id="tpMode"', 'id="stopDistance"', 'id="manualTp1"',
        'id="manualTp4"', 'id="volumeMode"', 'id="riskPercent"', 'id="lotSize"',
        'id="trailingEnabled"', 'id="trailingBreakEven"', 'id="trailingStep"',
        'id="trailingLock"',
    ):
        assert marker in html

    for marker in (
        "stop_loss_mode", "take_profit_mode", "volume_mode", "risk_percent",
        "lot_size", "trailing_enabled", "trailing_break_even_r", "trailing_step_r",
        "trailing_lock_r", "/signals/calculate",
    ):
        assert marker in js

    assert "border:2px solid" in css
    assert "border-right-width:5px" in css
