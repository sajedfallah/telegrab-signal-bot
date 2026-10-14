from datetime import datetime, timezone
from unittest.mock import patch

from app.agent_system.contracts import MarketSnapshot
from app.agent_system.setup_lifecycle_v32 import observe


def snapshot():
    rows=tuple({"time":1000+i*60,"open":100.0,"high":102.0,"low":98.0,"close":100.0} for i in range(35))
    return MarketSnapshot(snapshot_id="v32",symbol="XAUUSD",as_of=datetime.now(timezone.utc),
        source="test",timeframes={"M1":rows},bid=100.0,ask=100.1,data_freshness_ms=0)


def tracker(state="SWEEP_OBSERVED"):
    return dict(status=state,setup_id="stable-123",direction="SHORT",sweep_time=1000+20*60,
                blocks=[],confirmed_for_signal=False,mss_time=None,fvg_time=None,retest_time=None,fvg=None)


def zone(low=99.0):
    return dict(source="OB",timeframe="M15",low=low,high=101.0,direction="SHORT",quality="PROVISIONAL")


def test_without_poi_no_persistence(tmp_path):
    db=str(tmp_path/"test.db")
    with patch("app.agent_system.setup_lifecycle_v32.track_ict_setup",return_value=tracker()), \
         patch("app.agent_system.setup_lifecycle_v32.scan_pois",return_value=[]):
        result=observe(snapshot(),"M1",db)
    assert result["poi_bound"] is False
    assert result["persistent"] is False
    assert not (tmp_path/"test.db").exists()


def test_stable_state_and_no_regression(tmp_path):
    db=str(tmp_path/"test.db")
    with patch("app.agent_system.setup_lifecycle_v32.scan_pois",return_value=[zone()]), \
         patch("app.agent_system.setup_lifecycle_v32.track_ict_setup",
               side_effect=[tracker("RETEST_OBSERVED"),tracker("SWEEP_OBSERVED")]):
        first=observe(snapshot(),"M1",db)
        second=observe(snapshot(),"M1",db)
    assert first["persistent"]
    assert second["status"]=="RETEST_OBSERVED"
    assert second["confirmed_for_signal"] is False


def test_changed_poi_invalidates_setup(tmp_path):
    db=str(tmp_path/"test.db")
    with patch("app.agent_system.setup_lifecycle_v32.track_ict_setup",return_value=tracker()):
        with patch("app.agent_system.setup_lifecycle_v32.scan_pois",return_value=[zone()]):
            first=observe(snapshot(),"M1",db)
        with patch("app.agent_system.setup_lifecycle_v32.scan_pois",return_value=[zone(99.5)]):
            second=observe(snapshot(),"M1",db)
    assert first["status"]=="SWEEP_OBSERVED"
    assert second["status"]=="INVALIDATED"
    assert not second["confirmed_for_signal"]
