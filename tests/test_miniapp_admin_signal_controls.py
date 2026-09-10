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
from app.autotrade.trailing_profiles import TRAILING_PROFILES
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


def test_fixed_lot_and_legacy_custom_trailing_remain_backward_compatible(client):
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


def test_official_trailing_profile_selection_persists_exact_snapshot(client):
    payload = {
        "symbol": "XAUUSD",
        "direction": "BUY",
        "entry": 3650,
        "stop_loss": 3645,
        "stop_loss_mode": "MANUAL",
        "take_profit_mode": "AUTO",
        "destination": "VIP",
        "request_id": "official-profile-007",
        "timeframe": "M5",
        "volume_mode": "RISK",
        "risk_percent": 1.0,
        "trailing_enabled": True,
        "trailing_profile_code": "NEXUS_TRAIL_07",
        "digits": 2,
    }
    response = client.post("/miniapp/api/admin/signals", headers=headers(), json=payload)
    assert response.status_code == 201, response.text
    body = response.json()
    signal = db.get_signal(body["signal_id"])
    assert signal["trailing_code"] == "NEXUS_TRAIL_07"
    assert signal["trailing_name"] == TRAILING_PROFILES["NEXUS_TRAIL_07"]["name"]
    config = json.loads(signal["trailing_config_json"])
    assert config["code"] == "NEXUS_TRAIL_07"
    assert config["runner_mode"] == "MARKET_STRUCTURE_ATR_FALLBACK"
    assert config["tp1_close_pct"] == 30.0
    assert config["tp2_close_pct"] == 30.0
    assert config["runner_pct"] == 40.0


def test_all_seven_trailing_profiles_are_accepted(client):
    for number in range(1, 8):
        code = f"NEXUS_TRAIL_{number:02d}"
        response = client.post(
            "/miniapp/api/admin/signals",
            headers=headers(),
            json={
                "symbol": "XAUUSD",
                "direction": "BUY",
                "entry": 3650,
                "stop_loss": 3645,
                "destination": "VIP",
                "request_id": f"profile-{number:02d}-accept",
                "timeframe": "M5",
                "volume_mode": "RISK",
                "risk_percent": 1.0,
                "trailing_enabled": True,
                "trailing_profile_code": code,
                "digits": 2,
            },
        )
        assert response.status_code == 201, (code, response.text)
        body = response.json()
        signal = db.get_signal(body["signal_id"])
        assert signal["trailing_code"] == code
        assert json.loads(signal["trailing_config_json"])["code"] == code


def test_bootstrap_exposes_symbol_catalog_and_seven_trailing_profiles(client):
    response = client.get("/miniapp/api/admin/bootstrap", headers=headers())
    assert response.status_code == 200, response.text
    body = response.json()

    symbol_groups = {item["key"]: item["symbols"] for item in body["symbol_catalog"]}
    assert "DOWJONES" in symbol_groups["INDEX"]
    assert "NASDAQ" in symbol_groups["INDEX"]
    assert "EURUSD" in symbol_groups["FOREX"]
    assert "GBPUSD" in symbol_groups["FOREX"]
    assert "BTCUSD" in symbol_groups["CRYPTO"]
    assert "ETHUSD" in symbol_groups["CRYPTO"]
    assert "SOLUSD" in symbol_groups["CRYPTO"]

    profiles = body["trailing_profiles"]
    assert [item["code"] for item in profiles] == [f"NEXUS_TRAIL_{n:02d}" for n in range(1, 8)]
    assert all(item["name"] and item["guide"] and item["config"]["code"] == item["code"] for item in profiles)


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


def test_invalid_fixed_lot_and_aggressive_legacy_trailing_are_rejected(client):
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


def test_invalid_trailing_profile_code_is_rejected(client):
    response = client.post(
        "/miniapp/api/admin/signals",
        headers=headers(),
        json={
            "symbol": "XAUUSD",
            "direction": "BUY",
            "entry": 3650,
            "stop_loss": 3645,
            "destination": "VIP",
            "request_id": "bad-profile-code",
            "timeframe": "M5",
            "volume_mode": "RISK",
            "risk_percent": 1,
            "trailing_enabled": True,
            "trailing_profile_code": "NEXUS_TRAIL_99",
        },
    )
    assert response.status_code == 422


def test_admin_ui_exposes_v3_control_surface_and_theme():
    html = Path("miniapp/admin.html").read_text(encoding="utf-8")
    js = Path("miniapp/admin-signal.js").read_text(encoding="utf-8")
    css = Path("miniapp/admin-signal.css").read_text(encoding="utf-8")

    for marker in (
        'id="symbol"', '<option value="DOWJONES">', '<option value="NASDAQ">',
        '<option value="BTCUSD">', '<option value="ETHUSD">', '<option value="SOLUSD">',
        'id="slMode"', 'id="tpMode"', 'id="stopDistance"', 'id="manualTp1"',
        'id="manualTp4"', 'id="volumeMode"', 'id="riskPercent"', 'id="lotSize"',
        'id="trailingEnabled"', 'id="trailingProfile"', 'id="trailingPreview"',
        'NEXUS_TRAIL_01', 'NEXUS_TRAIL_07',
    ):
        assert marker in html

    for marker in (
        "stop_loss_mode", "take_profit_mode", "volume_mode", "risk_percent",
        "lot_size", "trailing_enabled", "trailing_profile_code", "/signals/calculate",
        "populateSymbols", "populateTrailingProfiles", "renderTrailingPreview",
    ):
        assert marker in js

    assert "--amber:#ffb020" in css
    assert "--cyan:#7ddcff" in css
    assert "border:3px solid" in css
    assert "border-right-width:7px" in css
    assert ".trail-profile-preview" in css
