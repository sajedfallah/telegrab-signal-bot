from datetime import datetime, timezone

from app.agent_system.contracts import Direction, MarketSnapshot
from app.agent_system.full_ict_gate import verify_full_ict


def sample(freshness=0):
    bars=tuple({"time":i,"open":100.0,"close":100.0,"high":101.0,
                "low":99.0} for i in range(40))
    return MarketSnapshot(snapshot_id="full-ict-gate-test",symbol="XAUUSD",
        as_of=datetime.now(timezone.utc),source="test",
        timeframes={"M1":bars,"M5":bars,"M15":bars,"H1":bars,"D1":bars},
        bid=100.0,ask=100.2,data_freshness_ms=freshness)


def test_full_ict_rejects_missing_sequence():
    gate=verify_full_ict(sample(),Direction.LONG,"M1",100.2,99.0,(103.0,),1.5)
    assert gate.allowed is False


def test_full_ict_rejects_stale_feed():
    gate=verify_full_ict(sample(40001),Direction.SHORT,"M5",100.0,102.0,(96.0,),1.5)
    assert gate.allowed is False
    assert "stale_or_missing_feed" in gate.blocks


def test_full_ict_needs_policy():
    gate=verify_full_ict(sample(),Direction.LONG,"M1",100.2,99.0,(103.0,),None)
    assert gate.allowed is False
    assert "risk_policy_missing" in gate.blocks


def test_full_ict_never_approves_zero_risk():
    gate=verify_full_ict(sample(),Direction.LONG,"M1",100.0,100.0,(103.0,),1.5)
    assert gate.allowed is False
