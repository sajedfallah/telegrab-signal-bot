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
    record={"symbol":"XAUUSD","scan":"WATCH","supervisor":"WAIT","final":"WAIT","direction":"NEUTRAL","assessments":[{"agent":"nexus-ict-v1","direction":"NEUTRAL","evidence":["1H structure HH/HL","5M bullish MSS"],"missing_data":[]} ]}
    text=format_hourly_analysis(record)
    assert "تحلیل ساعتی NEXUS | XAUUSD" in text
    assert "دیدگاه ICT: خنثی / در انتظار تأیید" in text
    assert "ساختار 1H: سقف و کف بالاتر (HH/HL) — تمایل صعودی" in text
    assert "Signal: WAIT" in text
