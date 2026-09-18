from __future__ import annotations

from pathlib import Path

from app.autotrade.chart_alert_dedup_runtime import _incident_payload


ROOT = Path(__file__).resolve().parents[1]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8-sig")


def test_v46_same_exhausted_incident_keeps_same_identity_when_rolling_counts_change():
    base = {
        "severity": "CRITICAL",
        "counts": {"FAILED": 0, "EXPIRED": 0},
        "fallback_publications": 0,
        "repair_exhausted": [{
            "signal_id": 103,
            "job_id": 9001,
            "code": "NX-103",
            "error_text": "CAPTURE_FAILED: SL_TAG_DRAW_FAILED:Y_BOUNDS:key=SL.TAG",
        }],
    }
    changed_counters = {
        **base,
        "counts": {"FAILED": 4, "EXPIRED": 2},
        "fallback_publications": 7,
    }

    key1, signal_id1, payload1 = _incident_payload("80150619", base)
    key2, signal_id2, payload2 = _incident_payload("80150619", changed_counters)

    assert key1 == key2
    assert signal_id1 == signal_id2 == 103
    assert payload1["code"] == payload2["code"] == "NX-103"


def test_v46_materially_changed_chart_incident_gets_new_identity():
    base = {
        "severity": "CRITICAL",
        "counts": {},
        "fallback_publications": 0,
        "repair_exhausted": [{
            "signal_id": 103,
            "job_id": 9001,
            "code": "NX-103",
            "error_text": "CAPTURE_FAILED: SL_TAG_DRAW_FAILED:Y_BOUNDS:key=SL.TAG",
        }],
    }
    changed = {
        **base,
        "repair_exhausted": [{
            "signal_id": 103,
            "job_id": 9002,
            "code": "NX-103",
            "error_text": "CAPTURE_FAILED: SL_TAG_DRAW_FAILED:XY_FAILED:key=SL.TAG",
        }],
    }

    key1, _, _ = _incident_payload("80150619", base)
    key2, _, _ = _incident_payload("80150619", changed)
    assert key1 != key2


def test_v46_dedup_is_installed_after_chart_delivery_guard():
    combined = _text("app/combined_api.py")
    assert "install_chart_delivery_guard(app)" in combined
    assert "install_chart_alert_dedup_runtime(app)" in combined
    assert combined.index("install_chart_delivery_guard(app)") < combined.index("install_chart_alert_dedup_runtime(app)")


def test_v46_dedup_runtime_exposes_install_marker():
    src = _text("app/autotrade/chart_alert_dedup_runtime.py")
    assert '_DEDUP_VERSION = "v46"' in src
    assert "nexus_chart_alert_dedup_version" in src
    assert "[NEXUS][CHART_ALERT_DEDUP] installed version=%s" in src


def test_v46_chartagent_preserves_sl_tag_failure_detail():
    src = _text("mt5/NEXUS_ChartAgent/NEXUS_ChartAgent.mq5")
    assert 'error_text="SL_TAG_DRAW_FAILED:"+g_last_tag_error;' in src
    assert 'error_text="SL_TAG_DRAW_FAILED";' not in src
