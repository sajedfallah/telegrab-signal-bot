from app.agent_system.telegram_reporter import format_hourly_analysis
import os

import pytest

from app.agent_system.shadow_runner import _reporter_from_env
from app.agent_system.telegram_reporter import format_shadow_record


def test_format_shadow_record_marks_mode_and_risk():
    text=format_shadow_record({"symbol":"XAUUSD","scan":"WATCH","supervisor":"ARMED","final":"SIGNAL_CANDIDATE","direction":"LONG","risk_allowed":False,"risk_blocks":["risk_policy_missing:min_rr"]})
    assert "XAUUSD" in text
    assert "SIGNAL_CANDIDATE" in text
    assert "Risk Gate: BLOCKED" in text
    assert "NO REAL ORDER" in text


def test_format_error_is_no_trade():
    text=format_shadow_record({"symbol":"US30","final":"NO_TRADE","error":"feed unavailable"})
    assert "NO_TRADE" in text and "feed unavailable" in text


def test_reporter_requires_both_secret_env_values(monkeypatch):
    monkeypatch.delenv("NEXUS_AGENT_TEST_BOT_TOKEN",raising=False)
    monkeypatch.delenv("NEXUS_AGENT_TEST_CHAT_ID",raising=False)
    with pytest.raises(RuntimeError):
        _reporter_from_env(True)


def test_reporter_disabled_never_requires_secrets(monkeypatch):
    monkeypatch.delenv("NEXUS_AGENT_TEST_BOT_TOKEN",raising=False)
    monkeypatch.delenv("NEXUS_AGENT_TEST_CHAT_ID",raising=False)
    assert _reporter_from_env(False) is None


def test_hourly_analysis_includes_agent_evidence_and_wait_state():
    record={"symbol":"XAUUSD","final":"ANALYSIS","direction":"NEUTRAL","bid":4356.51,"ask":4356.73,"m5_recent_high":4363.06,"m5_recent_low":4343.0,"assessments":[{"agent":"nexus-ict-v1","direction":"NEUTRAL","evidence":["1H structure HH/HL","Daily Quadrant UPPER 4295.2-4367.46; 25=4313.26, 50=4331.33, 75=4349.4","Price is inside Daily Quadrant HTF reaction zone; lower-timeframe confirmation remains mandatory","15M bearish FVG 4358.15-4363.06"],"invalidation":["valid 5M liquidity sweep + MSS confirmation required"],"missing_data":[]}]}
    text=format_hourly_analysis(record)
    assert "آپدیت ساعتی NEXUS | XAUUSD" in text
    assert "بچه‌های نکسوس" in text
    assert "ساختار 1H فعلاً HH/HL" in text
    assert "محدوده کامل: 4295.2 تا 4367.46" in text
    assert "سطح 25٪: 4313.26" in text
    assert "سطح 50٪: 4331.33" in text
    assert "سطح 75٪: 4349.4" in text
    assert "سناریوی Long در 5M" in text
    assert "4343" in text
    assert "سناریوی Short در 5M" in text
    assert "4363.06" in text
    assert "SHADOW" not in text
