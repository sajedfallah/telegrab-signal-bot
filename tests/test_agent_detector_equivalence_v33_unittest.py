"""Characterization gates: a test passing may CONFIRM a legacy disagreement.

No runtime detector is patched. These synthetic cases are not proof of general
equivalence and must not authorize watcher integration.
"""
from datetime import datetime, timezone
import unittest

from app.agent_system.contracts import Direction, MarketSnapshot
from app.agent_system.fast_scalp import assess_fast_scalp, FastScalpState, _m1_sequence
from app.agent_system.setup_tracker_v31 import track_ict_setup
from app.agent_system.full_ict_gate import verify_full_ict


def sample(*, pre_mss_only=False, mirror=False):
    base=1700000000
    def row(i,o=100.,h=101.,l=99.,c=100.1,seconds=60):
        return dict(time=base+i*seconds,open=o,high=h,low=l,close=c)
    bars=[row(i) for i in range(40)]
    bars[33]=row(33,100.,101.,98.,100.2)
    if pre_mss_only:
        bars[34]=row(34,103.,106.,103.,105.)
        for i in range(35,40): bars[i]=row(i,102.,107.,100.,102.)
        price=102.5
    else:
        bars[34]=row(34,100.,104.5,100.,104.)
        bars[35]=row(35,104.,106.5,103.,106.)
        bars[36]=row(36,106.,107.5,105.,107.)
        bars[37]=row(37,106.,106.5,104.6,105.5)
        price=104.8
    h1=[row(i-40,90.+i*.2,90.5+i*.2,89.5+i*.2,90.1+i*.2,3600) for i in range(40)]
    m15=[row(i-40,100.,110.,98.,100.1,900) for i in range(40)]
    daily=[row(i-11,100.,110.,98.,100.1,86400) for i in range(11)]
    frames={"M1":tuple(bars),"M5":tuple(bars),"H1":tuple(h1),"M15":tuple(m15),"D1":tuple(daily)}
    if mirror:
        frames={tf:tuple({**r,"open":200.-r["open"],"high":200.-r["low"],
            "low":200.-r["high"],"close":200.-r["close"]} for r in rows) for tf,rows in frames.items()}
        price=200.-price
    return MarketSnapshot(snapshot_id="detector-comparison-fixture",symbol="XAUUSD",
        as_of=datetime.fromtimestamp(base+40*60,timezone.utc),source="isolated_fixture",
        timeframes=frames,bid=price-.1,ask=price+.1,data_freshness_ms=0)


def compare(snap,mirror=False):
    fast=assess_fast_scalp(snap)
    tracker=track_ict_setup(snap,"M1")
    price=(snap.bid+snap.ask)/2
    gate=verify_full_ict(snap,Direction.SHORT if mirror else Direction.LONG,"M1",price,
                         102. if mirror else 98.,(82. if mirror else 118.,),1.5)
    return fast,tracker,gate


class DetectorComparisonTests(unittest.TestCase):
    def test_all_detectors_reject_stale_fixture(self):
        snap=sample().model_copy(update={"data_freshness_ms":30001})
        fast,tracker,gate=compare(snap)
        self.assertNotEqual(fast.state,FastScalpState.ENTRY_READY)
        self.assertEqual(tracker["status"],"WAIT")
        self.assertFalse(gate.allowed)

    def test_same_readiness_does_not_prove_same_fvg_identity(self):
        for mirror in (False,True):
            with self.subTest(short=mirror):
                fast,tracker,gate=compare(sample(mirror=mirror),mirror)
                self.assertEqual(fast.state,FastScalpState.ENTRY_READY)
                self.assertEqual(tracker["status"],"RETEST_OBSERVED")
                self.assertTrue(gate.allowed)
                # Both say ready but select different gaps: integration must block.
                self.assertNotEqual(tuple(tracker["fvg"]),fast.entry_zone)

    def test_pre_mss_gap_disagreement_is_a_migration_blocker(self):
        fast,tracker,gate=compare(sample(pre_mss_only=True))
        self.assertEqual(fast.state,FastScalpState.ENTRY_READY)
        self.assertEqual(tracker["status"],"RETEST_OBSERVED")
        self.assertFalse(gate.allowed)
        self.assertIn("full_ict_sequence_unverified",gate.blocks)

    def test_fast_scalp_confirms_forming_mss_but_tracker_does_not(self):
        snap=sample()
        base=snap.timeframes["M1"][0]["time"]
        rows=[dict(time=base+i*60,open=100.,high=101.,low=99.,close=100.1) for i in range(40)]
        rows[37].update(low=98.,close=100.2)
        rows[39].update(open=100.,high=106.,close=105.)
        snap=snap.model_copy(update={"timeframes":{**snap.timeframes,"M1":tuple(rows)},
            "as_of":datetime.fromtimestamp(base+39*60+30,timezone.utc)})
        sweep,_,mss,_=_m1_sequence(tuple(rows),Direction.LONG)
        tracker=track_ict_setup(snap,"M1")
        self.assertEqual((sweep,mss),(37,39))
        self.assertEqual(tracker["status"],"SWEEP_OBSERVED")
        self.assertIsNone(tracker["mss_time"])


if __name__=="__main__": unittest.main()
