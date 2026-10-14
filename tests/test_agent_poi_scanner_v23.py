from datetime import datetime, timezone

from app.agent_system.contracts import MarketSnapshot
from app.agent_system.poi_scanner_v23 import scan_pois


def test_multiple_pois_do_not_grant_execution():
    rows = tuple({"open": 100, "high": 103+i*.01, "low": 97-i*.01,
                  "close": 100, "time": i} for i in range(32))
    snapshot = MarketSnapshot(snapshot_id="poi-scanner-v23-test",symbol="XAUUSD",
        as_of=datetime.now(timezone.utc),source="test",
        timeframes={"D1":rows,"M15":rows,"M5":rows},
        bid=100.0,ask=100.2,data_freshness_ms=0)
    pois = scan_pois(snapshot)
    assert len(pois) >= 2
    assert all(p["confirmed"] is False for p in pois)
    assert all(p["low"] < p["high"] for p in pois)


def test_stale_snapshot_has_no_actionable_pois():
    rows=tuple({"open":100,"high":101,"low":99,"close":100,"time":i} for i in range(32))
    snapshot=MarketSnapshot(snapshot_id="poi-scanner-stale-test",symbol="XAUUSD",
        as_of=datetime.now(timezone.utc),source="test",timeframes={"D1":rows,"M5":rows},
        bid=100.0,ask=100.1,data_freshness_ms=40000)
    assert scan_pois(snapshot)==[]
