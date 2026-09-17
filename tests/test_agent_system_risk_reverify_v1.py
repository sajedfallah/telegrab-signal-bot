from datetime import datetime, timezone

from app.agent_system.contracts import Direction, MarketSnapshot, SupervisorDecision, WorkflowState
from app.agent_system.reverify import reverify
from app.agent_system.risk_gate import RiskPolicy, evaluate_risk


def _trend_rows(count=50):
    rows=[]
    for i in range(count):
        b=100+i*.3
        rows.append({"time":1700000000+i*300,"open":b-.05,"high":b+.2,"low":b-.2,"close":b+.05,"tick_volume":10})
    return rows


def _bull_trigger_rows(enabled=True):
    rows=_trend_rows()
    if enabled:
        pl=min(x["low"] for x in rows[-14:-2])
        rows[-2]={**rows[-2],"low":pl-1,"close":pl+.1}
        br=max(x["high"] for x in rows[-7:-1])+.5
        rows[-1]={**rows[-1],"high":br+.2,"close":br}
    return rows


def snap(trigger=True,fresh=1000,events=()):
    d1=_trend_rows(20); h1=_trend_rows(); m15=_trend_rows(); m5=_bull_trigger_rows(trigger)
    return MarketSnapshot(snapshot_id=f"snapshot-{trigger}-{fresh}",symbol="XAUUSD",as_of=datetime(2026,9,17,tzinfo=timezone.utc),source="TEST",timeframes={"D1":tuple(d1),"H1":tuple(h1),"M15":tuple(m15),"M5":tuple(m5)},bid=114.7,ask=114.9,data_freshness_ms=fresh,scheduled_events=events)


def armed(s):
    return SupervisorDecision(symbol=s.symbol,snapshot_id=s.snapshot_id,state=WorkflowState.ARMED,direction=Direction.LONG,explanation="test")


def candidate(s):
    return SupervisorDecision(symbol=s.symbol,snapshot_id=s.snapshot_id,state=WorkflowState.SIGNAL_CANDIDATE,direction=Direction.LONG,explanation="test")


def test_reverify_promotes_armed_when_fresh_ict_direction_still_matches():
    a=snap(True); b=snap(True); d=reverify(a,b,armed(a))
    assert d.state==WorkflowState.SIGNAL_CANDIDATE and d.direction==Direction.LONG


def test_reverify_waits_when_fresh_5m_confirmation_disappears():
    a=snap(True); b=snap(False)
    assert reverify(a,b,armed(a)).state==WorkflowState.WAIT


def test_reverify_cancels_stale_fresh_snapshot():
    a=snap(True); b=snap(True,fresh=60000)
    assert reverify(a,b,armed(a)).state==WorkflowState.CANCELLED


def test_risk_gate_blocks_without_verified_rr():
    s=snap(); r=evaluate_risk(s,candidate(s),policy=RiskPolicy(min_rr=1.5))
    assert not r.allowed and "rr_not_verified" in r.hard_blocks


def test_risk_gate_fails_closed_when_rr_policy_is_not_explicit():
    s=snap(); r=evaluate_risk(s,candidate(s),proposed_rr=2.0)
    assert not r.allowed and "risk_policy_missing:min_rr" in r.hard_blocks


def test_risk_gate_blocks_active_high_impact_event():
    s=snap(events=({"name":"CPI","impact":"HIGH","active_window":True},))
    r=evaluate_risk(s,candidate(s),proposed_rr=2.0,policy=RiskPolicy(min_rr=1.5))
    assert not r.allowed and "high_impact_news_window" in r.hard_blocks


def test_risk_gate_allows_clean_candidate_with_explicit_policy():
    s=snap(); r=evaluate_risk(s,candidate(s),proposed_rr=2.0,policy=RiskPolicy(min_rr=1.5))
    assert r.allowed
