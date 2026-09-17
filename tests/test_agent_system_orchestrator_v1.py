from datetime import datetime, timedelta, timezone

from app.agent_system.contracts import MarketSnapshot, WorkflowState
from app.agent_system.orchestrator import run_shadow


def _rows(count=50, trend=True):
    out=[]
    for i in range(count):
        b=100+i*.3 if trend else 100
        out.append({"time":1700000000+i*300,"open":b-.05,"high":b+.2,"low":b-.2,"close":b+.05,"tick_volume":10})
    return out


def _flat_rows(count=50):
    return [{"time":1700000000+i*300,"open":100.0,"high":101.5,"low":99.5,"close":100.0,"tick_volume":10} for i in range(count)]


def _snapshot(seq=0, watch=False, news=True):
    h1=_rows(); m15=_rows(); m5=_rows(); d1=_rows(20)
    if watch:
        pl=min(x["low"] for x in m5[-14:-2]); m5[-2]={**m5[-2],"low":pl-1,"close":pl+.1}; br=max(x["high"] for x in m5[-7:-1])+.5; m5[-1]={**m5[-1],"high":br+.2,"close":br}
    ctx=({"kind":"macro","summary":"macro neutral","direction":"NEUTRAL"},{"kind":"news","title":"news neutral","direction":"NEUTRAL"}) if news else ()
    return MarketSnapshot(snapshot_id=f"shadow-snapshot-{seq:04d}",symbol="XAUUSD",as_of=datetime(2026,9,17,8,0,tzinfo=timezone.utc)+timedelta(seconds=seq),source="TEST",timeframes={"D1":tuple(d1),"H1":tuple(h1),"M15":tuple(m15),"M5":tuple(m5)},bid=114.7+seq*.01,ask=114.9+seq*.01,session="LONDON",news_context=ctx,data_freshness_ms=1000)


def test_shadow_stops_before_specialists_when_scanner_waits():
    def builder(a,s):
        snap=_snapshot()
        flat=tuple(_flat_rows())
        return snap.model_copy(update={"timeframes": {"D1": snap.timeframes["D1"], "H1": flat, "M15": flat, "M5": flat}, "bid":100.49, "ask":100.51})
    r=run_shadow("1","XAUUSD",snapshot_builder=builder)
    assert r.scan.state==WorkflowState.WAIT
    assert r.assessments==() and r.fresh_snapshot is None and r.risk is None


def test_shadow_runs_candidate_through_fresh_snapshot_and_risk():
    calls=[]
    def builder(a,s):
        calls.append(1); return _snapshot(len(calls),watch=True,news=True)
    r=run_shadow("1","XAUUSD",proposed_rr=2.0,snapshot_builder=builder)
    assert len(calls)==2
    assert r.supervisor.state==WorkflowState.SIGNAL_CANDIDATE
    assert r.final_decision.state==WorkflowState.SIGNAL_CANDIDATE
    assert r.risk is not None and r.risk.allowed


def test_shadow_arms_instead_of_candidate_when_context_missing():
    def builder(a,s): return _snapshot(1,watch=True,news=False)
    r=run_shadow("1","XAUUSD",proposed_rr=2.0,snapshot_builder=builder)
    assert r.supervisor.state==WorkflowState.ARMED
    assert r.fresh_snapshot is None and r.risk is None
