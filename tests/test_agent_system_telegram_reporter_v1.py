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
