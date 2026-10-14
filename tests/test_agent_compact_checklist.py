from datetime import datetime, timezone

from app.agent_system.contracts import MarketSnapshot
from app.agent_system.scenario_v2 import build_shadow_scenarios, format_compact_checklist


def test_compact_checklist_supported_timeframes():
    rows=tuple({"open":100,"high":101+i/100,"low":99-i/100,"close":100} for i in range(30))
    for tf in ("M1","M5","M15","H1","D1","W1","MN1"):
        snapshot=MarketSnapshot(snapshot_id="compact-test-snapshot",symbol="XAUUSD",
            as_of=datetime.now(timezone.utc),source="test",timeframes={tf:rows},
            bid=100.0,ask=100.2,data_freshness_ms=0)
        scenario=build_shadow_scenarios(snapshot,tf)
        record={"symbol":"XAUUSD","analysis_timeframe":tf,"bid":100.0,"ask":100.2,
                "assessments":[],"shadow_scenarios_v2":scenario}
        text=format_compact_checklist(record)
        assert f"XAUUSD {tf}" in text
        assert "LONG" in text and "SHORT" in text
        assert "Entry / SL / TP / RR" in text
        assert "NO AUTO-EXECUTION" in text
        assert len(text)<1000
