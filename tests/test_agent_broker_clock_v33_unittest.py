from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from contextlib import closing
import hashlib
import sqlite3
import tempfile
import unittest

from app.agent_system.broker_clock_v33 import BrokerClock, read_broker_series, validate_broker_series


def rows(tf="M1",offset=0):
    step=60 if tf=="M1" else 300
    return tuple(dict(bar_time=t+offset,open=100.,high=102.,low=98.,close=101.,
                      captured_at=datetime.fromtimestamp(930,timezone.utc).isoformat())
                 for t in range(0,901,step))


class BrokerClockTests(unittest.TestCase):
    def setUp(self):
        self.clock=BrokerClock("isolated_broker_fixture","calibration-test-1",0,0,1200)

    def validate(self,data,**kwargs):
        args=dict(symbol="XAUUSD",timeframe="M1",clock=self.clock,decision_at=930)
        args.update(kwargs)
        return validate_broker_series(data,**args)

    def test_broker_successor_proves_close_not_live_bar(self):
        result=self.validate(rows())
        self.assertEqual(len(result.candles),15)
        self.assertEqual(result.candles[-1].closed_at,900)
        self.assertEqual(result.clock_reference,self.clock.reference)

    def test_explicit_offset_normalizes_without_changing_prices(self):
        original=self.validate(rows())
        converted=self.validate(rows(offset=7200),clock=replace(self.clock,offset_seconds=7200))
        self.assertEqual(original,converted)

    def test_m5_has_actual_m5_origins(self):
        result=self.validate(rows("M5"),timeframe="M5")
        self.assertEqual([c.opened_at for c in result.candles],[0,300,600])
        self.assertTrue(all(c.timeframe=="M5" for c in result.candles))

    def test_reject_missing_calibration_milliseconds_and_naive_capture(self):
        with self.assertRaises(ValueError): self.validate(rows(),clock=None)
        bad=list(rows()); bad[-1]={**bad[-1],"bar_time":900000}
        with self.assertRaises(ValueError): self.validate(bad)
        bad=list(rows()); bad[0]={**bad[0],"captured_at":"1970-01-01T00:15:30"}
        with self.assertRaises(ValueError): self.validate(bad)

    def test_reject_expired_calibration_future_and_stale_capture(self):
        with self.assertRaises(ValueError): self.validate(rows(),clock=replace(self.clock,valid_until=900))
        with self.assertRaises(ValueError): self.validate(rows(),decision_at=920)
        with self.assertRaises(ValueError): self.validate(rows(),decision_at=1000)

    def test_reject_gaps_duplicates_and_invalid_ohlc(self):
        bad=list(rows()); del bad[4]
        with self.assertRaises(ValueError): self.validate(bad)
        bad=list(rows()); bad[4]=dict(bad[3])
        with self.assertRaises(ValueError): self.validate(bad)
        bad=list(rows()); bad[4]={**bad[4],"high":float("inf")}
        with self.assertRaises(ValueError): self.validate(bad)

    def test_reject_close_without_capture_and_unknown_daily_session(self):
        bad=list(rows()); bad[0]={**bad[0],"captured_at":"1970-01-01T00:00:30+00:00"}
        with self.assertRaises(ValueError): self.validate(bad)
        with self.assertRaises(ValueError): self.validate(rows(),timeframe="D1")

    def test_read_only_export_is_unchanged_and_missing_account_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"export.sqlite"
            with closing(sqlite3.connect(path)) as db:
                db.execute("CREATE TABLE mt5_market_candles (account_number TEXT,symbol TEXT,timeframe TEXT,bar_time INTEGER,open REAL,high REAL,low REAL,close REAL,captured_at TEXT)")
                db.executemany("INSERT INTO mt5_market_candles VALUES (?,?,?,?,?,?,?,?,?)",
                    [("test-account","XAUUSD","M1",r["bar_time"],r["open"],r["high"],r["low"],r["close"],r["captured_at"]) for r in rows()])
                db.commit()
            before=hashlib.sha256(path.read_bytes()).hexdigest()
            result=read_broker_series(path,account="test-account",symbol="XAUUSD",timeframe="M1",clock=self.clock,decision_at=930)
            self.assertEqual(len(result.candles),15)
            with self.assertRaises(ValueError):
                read_broker_series(path,account="other",symbol="XAUUSD",timeframe="M1",clock=self.clock,decision_at=930)
            self.assertEqual(before,hashlib.sha256(path.read_bytes()).hexdigest())


if __name__=="__main__": unittest.main()
