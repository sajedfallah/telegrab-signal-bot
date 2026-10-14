from datetime import datetime, timezone

from app.agent_system.contracts import MarketSnapshot
from app.agent_system.setup_tracker_v31 import track_ict_setup


def make_snapshot(*, stale=False, with_times=True):
    rows=tuple(dict(open=100.0,high=101.0,low=99.0,close=100.0,
                   **({"time":i*60+1700000000} if with_times else {}))
               for i in range(45))
    h1=tuple(dict(open=100.0,high=105.0,low=95.0,close=100.0,
                  time=i*3600+1700000000) for i in range(45))
    return MarketSnapshot(snapshot_id="tracker-test",symbol="XAUUSD",
        as_of=datetime.now(timezone.utc),source="test",
        timeframes={"M1":rows,"M5":rows,"H1":h1},
        bid=100.0,ask=100.2,data_freshness_ms=31000 if stale else 0)


def test_fails_closed_on_stale():
    result=track_ict_setup(make_snapshot(stale=True),"M1")
    assert result["status"]=="WAIT"
    assert "market_data_not_verified" in result["blocks"]
    assert result["confirmed_for_signal"] is False


def test_neutral_or_no_sweep_never_confirms():
    result=track_ict_setup(make_snapshot(),"M5")
    assert result["status"]=="WAIT"
    assert result["setup_id"] is None
    assert result["confirmed_for_signal"] is False


def test_higher_timeframe_never_execution():
    result=track_ict_setup(make_snapshot(),"H1")
    assert result["status"]=="WAIT"
    assert "analysis_timeframe_not_execution_trigger" in result["blocks"]
