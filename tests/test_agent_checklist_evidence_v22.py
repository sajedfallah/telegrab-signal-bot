from app.agent_system.scenario_v2 import format_compact_checklist


def record(state, direction="SHORT"):
    return {
        "symbol": "XAUUSD", "analysis_timeframe": "M1",
        "bid": 100.0, "ask": 100.1,
        "assessments": [{
            "agent": "nexus-ict-v1",
            "evidence": [
                "1H structure LH/LL",
                "M1 buy-side liquidity sweep/reclaim (1 bars before MSS check)",
                "M1 bearish displacement/MSS",
            ],
        }],
        "fast_scalp": {"state": state, "direction": direction},
        "shadow_scenarios_v2": {
            "status": "WATCH", "reference_levels": {
                "sell_side_reference": 98.0, "buy_side_reference": 102.0,
            }, "blocks": ["waiting_for_poi_touch"],
            "entry": None, "take_profits": [],
        }
    }


def test_generic_sweep_observed_but_not_confirmed_when_searching():
    output = format_compact_checklist(record("SEARCHING"))
    assert "◉ Sweep بالا" in output
    assert "◉ MSS نزولی" in output
    assert "☐ M15 POI" in output
    assert "✅ Sweep بالا" not in output


def test_confirmed_requires_fast_state_and_matching_direction():
    output = format_compact_checklist(record("LIQUIDITY_SWEPT"))
    assert "✅ Sweep بالا" in output
    assert "◉ MSS نزولی" in output
    opposite = format_compact_checklist(record("LIQUIDITY_SWEPT", "LONG"))
    assert "✅ Sweep بالا" not in opposite


def test_mss_confirmed_by_matching_fast_state_only():
    output = format_compact_checklist(record("MSS_CONFIRMED"))
    assert "✅ Sweep بالا" in output
    assert "✅ MSS نزولی" in output
    assert "☐ FVG Retest" in output
