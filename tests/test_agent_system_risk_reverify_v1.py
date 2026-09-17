from datetime import datetime,timezone

from app.agent_system.contracts import Direction,MarketSnapshot,SupervisorDecision,WorkflowState
from app.agent_system.reverify import reverify
from app.agent_system.risk_gate import evaluate_risk


def snap(price=100.0,fresh=1000,events=()):
    rows=tuple({"time":i,"open":100,"high":101,"low":99,"close":100} for i in range(20))
    return MarketSnapshot(snapshot_id=f"snapshot-{price}-{fresh}",symbol="XAUUSD",as_of=datetime(2026,9,17,tzinfo=timezone.utc),source="TEST",timeframes={"D1":rows,"H1":rows,"M15":rows,"M5":rows},bid=price,ask=price+.1,data_freshness_ms=fresh,scheduled_events=events)

def candidate(s):
    return SupervisorDecision(symbol=s.symbol,snapshot_id=s.snapshot_id,state=WorkflowState.SIGNAL_CANDIDATE,direction=Direction.LONG,explanation="test")

def test_reverify_passes_small_move():
    a=snap(100); b=snap(100.1); d=reverify(a,b,candidate(a)); assert d.state==WorkflowState.SIGNAL_CANDIDATE and d.snapshot_id==b.snapshot_id

def test_reverify_waits_after_material_move():
    a=snap(100); b=snap(101); assert reverify(a,b,candidate(a)).state==WorkflowState.WAIT

def test_risk_gate_blocks_without_verified_rr():
    s=snap(); r=evaluate_risk(s,candidate(s)); assert not r.allowed and "rr_not_verified" in r.hard_blocks

def test_risk_gate_blocks_active_high_impact_event():
    s=snap(events=({"name":"CPI","impact":"HIGH","active_window":True},)); r=evaluate_risk(s,candidate(s),proposed_rr=2.0); assert not r.allowed and "high_impact_news_window" in r.hard_blocks

def test_risk_gate_allows_clean_candidate_with_rr():
    s=snap(); r=evaluate_risk(s,candidate(s),proposed_rr=2.0); assert r.allowed
