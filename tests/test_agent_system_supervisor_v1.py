from datetime import datetime, timezone

from app.agent_system.contracts import AgentAssessment, Direction, MarketSnapshot, WorkflowState
from app.agent_system.quadrant import derive_daily_quadrant
from app.agent_system.supervisor import supervise


def _snap():
    rows = tuple({"time": 1000+i, "open":100.0, "high":101.0, "low":99.0, "close":100.2} for i in range(30))
    return MarketSnapshot(snapshot_id="snap-supervisor-001", symbol="XAUUSD", as_of=datetime(2026,9,17,tzinfo=timezone.utc), source="TEST", timeframes={"H1":rows,"M15":rows,"M5":rows}, bid=100, ask=100.1, data_freshness_ms=100)


def _a(s, agent, direction, missing=()):
    return AgentAssessment(agent_id=agent, symbol=s.symbol, snapshot_id=s.snapshot_id, direction=direction, confidence=None, evidence=("test",), missing_data=missing, created_at=s.as_of)


def test_quadrant_uses_longest_wick_and_levels():
    rows = []
    for i in range(10):
        rows.append({"time":i, "open":100.0, "high":101.0, "low":99.0, "close":100.2})
    rows[4] = {"time":4, "open":100.0, "high":106.0, "low":99.8, "close":101.0}
    q = derive_daily_quadrant(tuple(rows))
    assert q is not None and q.wick_side == "UPPER"
    assert q.low == 101.0 and q.high == 106.0
    assert q.level_50 == 103.5


def test_supervisor_waits_without_ict_direction():
    s = _snap()
    d = supervise(s, (_a(s,"nexus-ict-v1",Direction.NEUTRAL),))
    assert d.state == WorkflowState.WAIT


def test_supervisor_waits_on_specialist_conflict():
    s = _snap()
    d = supervise(s, (_a(s,"nexus-ict-v1",Direction.LONG), _a(s,"nexus-macro-v1",Direction.SHORT)))
    assert d.state == WorkflowState.WAIT


def test_supervisor_arms_when_context_missing():
    s = _snap()
    d = supervise(s, (_a(s,"nexus-ict-v1",Direction.LONG), _a(s,"nexus-macro-v1",Direction.NEUTRAL,("structured_macro_context",))))
    assert d.state == WorkflowState.ARMED


def test_supervisor_candidate_requires_no_conflict_or_missing_context():
    s = _snap()
    d = supervise(s, (_a(s,"nexus-ict-v1",Direction.LONG), _a(s,"nexus-macro-v1",Direction.LONG), _a(s,"nexus-news-v1",Direction.NEUTRAL)))
    assert d.state == WorkflowState.SIGNAL_CANDIDATE
    assert d.direction == Direction.LONG
