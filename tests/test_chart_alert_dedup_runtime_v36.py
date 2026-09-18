from __future__ import annotations

from app.autotrade.chart_alert_dedup_runtime import _incident_payload


def _health(*, job_id: int, severity: str = "CRITICAL") -> dict:
    return {
        "severity": severity,
        "counts": {"FAILED": 0, "EXPIRED": 0},
        "fallback_publications": 0,
        "repair_exhausted": [{
            "signal_id": 103,
            "job_id": job_id,
            "code": "NX-103",
            "error_text": "CAPTURE_FAILED: SL_TAG_DRAW_FAILED:Y_BOUNDS",
        }],
    }


def test_same_signal_error_dedupes_across_repair_job_ids():
    first = _incident_payload("80150619", _health(job_id=9001))
    second = _incident_payload("80150619", _health(job_id=9002))

    assert first is not None
    assert second is not None
    assert first[0] == second[0]
    assert first[2]["job_id"] == 9001
    assert second[2]["job_id"] == 9002


def test_changed_error_is_a_new_incident():
    first = _incident_payload("80150619", _health(job_id=9001))
    changed = _health(job_id=9002)
    changed["repair_exhausted"][0]["error_text"] = "CAPTURE_FAILED: SL_TAG_DRAW_FAILED:XY_FAILED"
    second = _incident_payload("80150619", changed)

    assert first is not None
    assert second is not None
    assert first[0] != second[0]


def test_ok_health_has_no_alert_incident():
    assert _incident_payload("80150619", {"severity": "OK"}) is None
