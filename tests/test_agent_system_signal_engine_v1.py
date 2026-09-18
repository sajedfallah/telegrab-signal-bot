from datetime import datetime, timezone

from app.agent_system.contracts import Direction, MarketSnapshot, SupervisorDecision, WorkflowState
from app.agent_system.signal_engine import build_signal


def _bar(o,h,l,c,t): return {"time":t,"open":o,"high":h,"low":l,"close":c,"tick_volume":1}

def test_signal_builder_fails_closed_without_candidate():
    rows=tuple(_bar(100,101,99,100, i) for i in range(30))
    s=MarketSnapshot(snapshot_id="snap-signal-0001",symbol="XAUUSD",as_of=datetime.now(timezone.utc),source="TEST",timeframes={"M15":rows,"M5":rows},bid=100,ask=100.1,data_freshness_ms=100)
    d=SupervisorDecision(symbol="XAUUSD",snapshot_id=s.snapshot_id,state=WorkflowState.WAIT,direction=Direction.NEUTRAL,explanation="wait")
    r=build_signal(s,d)
    assert r.plan is None and "not_signal_candidate" in r.blocks


def test_signal_builder_uses_reverified_sweep_for_stop_and_structure_for_targets():
    m5=[]
    for i in range(20): m5.append(_bar(100,101,99,100,i))
    # Prior 12 lows are 99; penultimate bar sweeps below then reclaims.
    m5[-2]=_bar(100,101,98,100,i+1)
    m5[-1]=_bar(100,103,100,102,i+2)
    m15=tuple(_bar(100,100+i*.3,99,100,i) for i in range(30))
    s=MarketSnapshot(snapshot_id="snap-signal-0002",symbol="XAUUSD",as_of=datetime.now(timezone.utc),source="TEST",timeframes={"M15":m15,"M5":tuple(m5)},bid=101.9,ask=102,data_freshness_ms=100)
    d=SupervisorDecision(symbol="XAUUSD",snapshot_id=s.snapshot_id,state=WorkflowState.SIGNAL_CANDIDATE,direction=Direction.LONG,explanation="confirmed")
    r=build_signal(s,d)
    assert r.plan is not None
    assert r.plan.entry==102
    assert r.plan.stop_loss==98
    assert r.plan.take_profits and r.plan.take_profits[0]>102
    assert r.plan.rr>=1


def _delayed_long_m5_rows():
    rows=[_bar(100,101,99,100,i) for i in range(24)]
    # Sweep is three bars before the latest MSS check and remains eligible.
    rows[-4]=_bar(100,101,98,100,20)
    rows[-3]=_bar(100,101,99,100,21)
    rows[-2]=_bar(100,101,99,100,22)
    rows[-1]=_bar(100,103,100,102,23)
    return tuple(rows)


def _expired_long_m5_rows():
    rows=[_bar(100,101,99,100,i) for i in range(24)]
    # Sweep is outside the four-bar confirmation window.
    rows[-7]=_bar(100,101,98,100,17)
    rows[-1]=_bar(100,103,100,102,23)
    return tuple(rows)


def test_signal_builder_anchors_stop_to_recent_delayed_sweep():
    m15=tuple(_bar(100,100+i*.3,99,100,i) for i in range(30))
    s=MarketSnapshot(snapshot_id="snap-signal-delayed",symbol="XAUUSD",as_of=datetime.now(timezone.utc),source="TEST",timeframes={"M15":m15,"M5":_delayed_long_m5_rows()},bid=101.9,ask=102,data_freshness_ms=100)
    d=SupervisorDecision(symbol="XAUUSD",snapshot_id=s.snapshot_id,state=WorkflowState.SIGNAL_CANDIDATE,direction=Direction.LONG,explanation="confirmed")
    r=build_signal(s,d)
    assert r.plan is not None
    assert r.plan.stop_loss==98


def test_signal_builder_rejects_expired_sweep_anchor():
    m15=tuple(_bar(100,100+i*.3,99,100,i) for i in range(30))
    s=MarketSnapshot(snapshot_id="snap-signal-expired",symbol="XAUUSD",as_of=datetime.now(timezone.utc),source="TEST",timeframes={"M15":m15,"M5":_expired_long_m5_rows()},bid=101.9,ask=102,data_freshness_ms=100)
    d=SupervisorDecision(symbol="XAUUSD",snapshot_id=s.snapshot_id,state=WorkflowState.SIGNAL_CANDIDATE,direction=Direction.LONG,explanation="confirmed")
    r=build_signal(s,d)
    assert r.plan is None
    assert r.blocks==("5m_sweep_not_reverified",)