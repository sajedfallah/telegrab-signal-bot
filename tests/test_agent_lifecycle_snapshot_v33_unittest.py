from datetime import datetime, timezone
from dataclasses import FrozenInstanceError
import unittest

from app.agent_system.contracts import MarketSnapshot
from app.agent_system.lifecycle_snapshot_v33 import evidence_frame


def snapshot():
    def rows(seconds):
        return tuple(dict(time=t,closed_at=t+seconds,open=100.,high=102.,low=98.,close=101.)
                     for t in range(0,900+seconds,seconds))
    return MarketSnapshot(snapshot_id="snapshot-adapter-v33",symbol="XAUUSD",
        as_of=datetime.fromtimestamp(930,timezone.utc),source="isolated_fixture",
        timeframes={"M1":rows(60),"M5":rows(300)},bid=100.,ask=100.1,data_freshness_ms=0)


class SnapshotBoundaryTests(unittest.TestCase):
    def test_m1_m5_use_identical_snapshot_and_context(self):
        snap=snapshot()
        m1=evidence_frame(snap,"M1",context_ref="shared-1")
        m5=evidence_frame(snap,"M5",context_ref="shared-1")
        self.assertEqual((m1.snapshot_ref,m1.context_ref,m1.decision_at),
                         (m5.snapshot_ref,m5.context_ref,m5.decision_at))
        self.assertTrue(all(c.closed_at<=930 for c in (*m1.candles,*m5.candles)))
        self.assertEqual(m1.candles[-1].closed_at,900)
        self.assertEqual(m5.candles[-1].closed_at,900)

    def test_output_is_deeply_immutable_and_detached(self):
        snap=snapshot()
        frame=evidence_frame(snap,"M1",context_ref="context")
        original=frame.candles[0].close
        snap.timeframes["M1"][0]["close"]=99.
        self.assertEqual(frame.candles[0].close,original)
        with self.assertRaises(FrozenInstanceError): frame.candles[0].close=99.

    def test_legacy_snapshot_missing_close_metadata_fails(self):
        snap=snapshot()
        del snap.timeframes["M1"][0]["closed_at"]
        with self.assertRaises(ValueError): evidence_frame(snap,"M1",context_ref="context")

    def test_missing_stale_quote_context_or_timeframe_fails(self):
        snap=snapshot()
        for item in (snap.model_copy(update={"data_freshness_ms":30001}),
                     snap.model_copy(update={"missing_data":("candles:H4",)}),
                     snap.model_copy(update={"ask":None})):
            with self.assertRaises(ValueError): evidence_frame(item,"M1",context_ref="context")
        with self.assertRaises(ValueError): evidence_frame(snap,"M1",context_ref="")
        with self.assertRaises(ValueError): evidence_frame(snap,"H4",context_ref="context")

    def test_duplicate_and_future_bars_fail(self):
        for rows in ((snapshot().timeframes["M1"][0],)*2,
                     (dict(time=960,closed_at=1020,open=100.,high=102.,low=98.,close=101.),)):
            snap=snapshot().model_copy(update={"timeframes":{"M1":rows}})
            with self.assertRaises(ValueError): evidence_frame(snap,"M1",context_ref="context")

    def test_no_lookahead_in_prefix(self):
        snap=snapshot()
        frame=evidence_frame(snap,"M1",context_ref="context")
        snap.timeframes["M1"][-1]["high"]=1000.
        self.assertEqual(frame,evidence_frame(snap,"M1",context_ref="context"))


if __name__=="__main__":
    unittest.main()
