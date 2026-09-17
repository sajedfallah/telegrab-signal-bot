from datetime import datetime, timedelta, timezone

from app.agent_system.contracts import MarketSnapshot, WorkflowState
from app.agent_system.orchestrator import run_shadow
from app.agent_system.risk_gate import RiskPolicy


def _rows(count=50, trend=True):
    out=[]
    for i in range(count):
        b=100+i*.3 if trend else 100
        out.append({"time":1700000000+i*300,"open":b-.05,"high":b+.2,"low":b-.2,"close":b+.05,"tick_volume":10})
    return out


def _snapshot(seq=0, watch=False, news=True, target=True):
    h1=_rows(); m15=_rows(); m5=_rows(); d1=_rows(20)
    if watch:
        pl=min(x["low"] for x in m5[-14:-2]); m5[-2]={**m5[-2],"low":pl-1,"close":pl+.1}; br=max(x["high"] for x in m5[-7:-1])+.5; m5[-1]={**m5[-1],"high":br+.2,"close":br}
        # Signal construction requires an objective 15M structural target at >= 1R.
        # Keep the fixture deterministic and realistic enough to exercise the risk stage.
        if target:
            m15[-3]={**m15[-3],"high":122.0}
            m15[-2]={**m15[-2],"high":125.0}
            m15[-1]={**m15[-1],"high":128.0}
    else:
        m15=[{**x,"high":130.0,"low":90.0,"open":110.0,"close":110.0} for x in m15]
        m5=[{**x,"high":111.0,"low":109.0,"open":110.0,"close":110.0} for x in m5]
    ctx=({"kind":"macro","summary":"macro neutral","direction":"NEUTRAL"},{"kind":"news","title":"news neutral","direction":"NEUTRAL"}) if news else ()
    return MarketSnapshot(snapshot_id=f"shadow-snapshot-{seq:04d}",symbol="XAUUSD",as_of=datetime(2026,9,17,8,0,tzinfo=timezone.utc)+timedelta(seconds=seq),source="TEST",timeframes={"D1":tuple(d1),"H1":tuple(h1),"M15":tuple(m15),"M5":tuple(m5)},bid=114.7+seq*.01,ask=114.9+seq*.01,session="LONDON",news_context=ctx,data_freshness_ms=1000)


def test_shadow_stops_before_specialists_when_scanner_waits():
    def builder(a,s): return _snapshot()
    r=run_shadow("1","XAUUSD",snapshot_builder=builder)
    assert r.scan.state==WorkflowState.WAIT
    assert r.assessments==() and r.fresh_snapshot is None and r.risk is None


def test_shadow_arms_then_fresh_reverify_promotes_candidate_builds_signal_and_runs_risk():
    calls=[]
    def builder(a,s):
        calls.append(1); return _snapshot(len(calls),watch=True,news=True)
    r=run_shadow("1","XAUUSD",risk_policy=RiskPolicy(min_rr=1.5),snapshot_builder=builder)
    assert len(calls)==2
    assert r.supervisor.state==WorkflowState.ARMED
    assert r.final_decision.state==WorkflowState.SIGNAL_CANDIDATE
    assert r.signal is not None and not r.signal_blocks
    assert r.risk is not None and r.risk.allowed


def test_shadow_fails_closed_when_risk_threshold_policy_is_missing():
    calls=[]
    def builder(a,s):
        calls.append(1); return _snapshot(len(calls),watch=True,news=True)
    r=run_shadow("1","XAUUSD",snapshot_builder=builder)
    assert r.final_decision.state==WorkflowState.SIGNAL_CANDIDATE
    assert r.signal is not None
    assert r.risk is not None and not r.risk.allowed
    assert "risk_policy_missing:min_rr" in r.risk.hard_blocks


def test_shadow_does_not_run_risk_when_structural_signal_cannot_be_built():
    calls=[]
    def builder(a,s):
        calls.append(1); return _snapshot(len(calls),watch=True,news=True,target=False)
    r=run_shadow("1","XAUUSD",risk_policy=RiskPolicy(min_rr=1.5),snapshot_builder=builder)
    assert r.final_decision.state==WorkflowState.SIGNAL_CANDIDATE
    assert r.signal is None
    assert "no_valid_structural_target" in r.signal_blocks
    assert r.risk is None


def test_shadow_waits_without_fresh_snapshot_when_required_context_missing():
    def builder(a,s): return _snapshot(1,watch=True,news=False)
    r=run_shadow("1","XAUUSD",risk_policy=RiskPolicy(min_rr=1.5),snapshot_builder=builder)
    assert r.supervisor.state==WorkflowState.WAIT
    assert r.fresh_snapshot is None and r.risk is None
