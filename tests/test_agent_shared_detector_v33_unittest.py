from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from app.agent_system.lifecycle_evidence_v33 import Candle, Observation
from app.agent_system.lifecycle_snapshot_v33 import EvidenceFrame
from app.agent_system.setup_lifecycle_v33 import Setup, State, LifecycleStore
from app.agent_system.shared_detector_v33 import DetectorPolicy, detect_sequence, apply_research_sequence


def fixture(tf="M1",short=False):
    step=60 if tf=="M1" else 300
    def c(i,o=100.,h=101.,l=99.,close=100.2):
        if short: o,h,l,close=200.-o,200.-l,200.-h,200.-close
        return Candle("XAUUSD",tf,i*step,(i+1)*step,o,h,l,close,"shared_fixture")
    bars=[c(i) for i in range(26)]
    bars[10]=c(10,101.,103.,100.,101.5)
    bars[20]=c(20,100.,101.,98.,100.5)
    bars[21]=c(21,100.5,105.,100.,104.5)
    bars[22]=c(22,104.5,109.,104.,108.5)
    bars[23]=c(23,108.5,112.,107.,111.)
    bars[24]=c(24,111.,113.,110.,112.)
    bars[25]=c(25,111.,112.,109.3,109.8)
    setup=Setup("XAUUSD","ICT_FAST_SCALP_M1" if tf=="M1" else "ICT_STANDARD_M5",
        "SHORT" if short else "LONG",tf,"shared-context","bound-poi",c(0),step,
        97.,103.,True,110. if short else 90.,10*step,100*step)
    frame=EvidenceFrame("frame-26","shared-context","XAUUSD",tf,26*step,100.,100.2,tuple(bars))
    return setup,frame,c


class SharedDetectorTests(unittest.TestCase):
    def detect(self,setup,frame,**kwargs):
        step=60 if setup.timeframe=="M1" else 300
        return detect_sequence(frame,setup,sweep_opened_at=20*step,**kwargs)

    def prepared(self,setup,frame,path):
        store=LifecycleStore(path)
        store.create(setup,snapshot_ref="location")
        c=frame.candles[19]
        for state in (State.POI_SELECTED,State.APPROACHING_POI,State.POI_TOUCHED):
            store.advance(setup.setup_id,state,Observation(c,"isolated caller location"),event_key=state.value,
                          at=c.closed_at,snapshot_ref="location",feed_fresh=True)
        return store

    def test_exact_sequence_both_directions_and_timeframes(self):
        for tf in ("M1","M5"):
            for short in (False,True):
                with self.subTest(tf=tf,short=short):
                    setup,frame,_=fixture(tf,short)
                    result=self.detect(setup,frame)
                    self.assertEqual(result.status,State.RETEST_CONFIRMED)
                    self.assertEqual([e.state for e in result.events],[State.LIQUIDITY_SWEPT,State.MSS_CONFIRMED,
                        State.DISPLACEMENT_CONFIRMED,State.FVG_CREATED,State.RETEST_CONFIRMED])
                    sweep,mss,disp,gap,retest=result.events
                    self.assertEqual(mss.evidence.sweep_event,sweep.identity)
                    self.assertEqual(disp.evidence.mss_event,mss.identity)
                    self.assertEqual(gap.evidence.displacement_event,disp.identity)
                    self.assertEqual(retest.evidence.fvg_event,gap.identity)
                    self.assertEqual(mss.evidence.swing,frame.candles[10])
                    self.assertEqual(mss.evidence.swing_confirmation,frame.candles[12])
                    self.assertEqual(gap.evidence.left,frame.candles[22])

    def test_streaming_prefix_does_not_confirm_future_events(self):
        setup,frame,_=fixture()
        previous=()
        statuses={21:State.LIQUIDITY_SWEPT,22:State.MSS_CONFIRMED,23:State.DISPLACEMENT_CONFIRMED,
                  24:State.DISPLACEMENT_CONFIRMED,25:State.FVG_CREATED,26:State.RETEST_CONFIRMED}
        for count,status in statuses.items():
            prefix=replace(frame,candles=frame.candles[:count],decision_at=count*60,snapshot_ref=f"frame-{count}")
            result=self.detect(setup,prefix)
            self.assertEqual(result.status,status)
            identities=tuple(e.identity for e in result.events)
            self.assertEqual(identities[:len(previous)],previous)
            previous=identities

    def test_newer_sweep_does_not_replace_bound_anchor(self):
        setup,frame,c=fixture()
        before=self.detect(setup,frame)
        after=self.detect(setup,replace(frame,candles=(*frame.candles,c(26,100.,101.,97.,100.5)),decision_at=1620))
        self.assertEqual(before.events,after.events)
        self.assertEqual(before.sequence_id,after.sequence_id)

    def test_expiry_and_later_invalidation_override_old_retest(self):
        setup,frame,c=fixture()
        expired=self.detect(setup,replace(frame,decision_at=setup.expires_at))
        self.assertEqual(expired.status,State.EXPIRED)
        invalid=self.detect(setup,replace(frame,candles=(*frame.candles,c(26,100.,101.,88.,89.)),decision_at=1620))
        self.assertEqual(invalid.status,State.INVALIDATED)
        self.assertEqual(invalid.invalidating_candle.closed_at,1620)

    def test_reject_forming_future_missing_and_foreign_bars(self):
        setup,frame,_=fixture()
        for invalid in (replace(frame,decision_at=frame.decision_at-1),
                        replace(frame,candles=frame.candles[:8]+frame.candles[9:]),
                        replace(frame,context_ref="other"),
                        replace(frame,candles=(*frame.candles[:-1],replace(frame.candles[-1],source="other")))):
            with self.assertRaises(ValueError): self.detect(setup,invalid)

    def test_stale_closed_series_fails_without_promoting(self):
        setup,frame,_=fixture()
        result=self.detect(setup,replace(frame,decision_at=1800))
        self.assertEqual(result.events,())
        self.assertIn("closed_series_stale",result.blocks)

    def test_unconfirmed_or_equal_high_pivot_cannot_establish_mss(self):
        setup,frame,c=fixture()
        rows=list(frame.candles); rows[10]=c(10)
        result=self.detect(setup,replace(frame,candles=tuple(rows)))
        self.assertEqual(result.status,State.LIQUIDITY_SWEPT)
        self.assertIn("confirmed_pre_sweep_swing_unavailable",result.blocks)

    def test_same_candle_displacement_requires_explicit_policy(self):
        setup,frame,_=fixture()
        default=self.detect(setup,frame)
        opted=self.detect(replace(setup,allow_same_candle_displacement=True),frame)
        self.assertEqual(default.events[2].evidence.candle,frame.candles[22])
        self.assertEqual(opted.events[2].evidence.candle,frame.candles[21])

    def test_already_broken_swing_cannot_be_reused_for_mss(self):
        setup,frame,c=fixture()
        bars=list(frame.candles); bars[18]=c(18,100.,105.,99.,104.)
        result=self.detect(setup,replace(frame,candles=tuple(bars)))
        self.assertEqual(result.status,State.LIQUIDITY_SWEPT)
        self.assertIn("confirmed_pre_sweep_swing_unavailable",result.blocks)

    def test_pre_mss_gap_cannot_substitute_for_post_displacement_gap(self):
        setup,frame,c=fixture()
        bars=list(frame.candles)
        bars[21]=c(21,104.,106.,104.,105.)
        for i in range(23,26): bars[i]=c(i,105.,110.,103.,105.2)
        result=self.detect(setup,replace(frame,candles=tuple(bars)))
        self.assertEqual(result.status,State.DISPLACEMENT_CONFIRMED)
        self.assertEqual(len(result.events),3)

    def test_provisional_poi_evidence_never_becomes_entry_ready(self):
        setup,frame,_=fixture()
        setup=replace(setup,poi_qualified=False)
        with tempfile.TemporaryDirectory() as tmp:
            store=self.prepared(setup,frame,Path(tmp)/"shared.db")
            apply_research_sequence(store,setup,self.detect(setup,frame))
            self.assertEqual(store.recover(setup.setup_id)[1][-1]["state"],"RETEST_CONFIRMED")

    def test_research_persistence_idempotency_restart_and_prefix_progress(self):
        setup,frame,_=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"shared.db"
            store=self.prepared(setup,frame,path)
            for count in range(21,27):
                prefix=replace(frame,candles=frame.candles[:count],decision_at=count*60,snapshot_ref=f"frame-{count}")
                result=self.detect(setup,prefix)
                apply_research_sequence(store,setup,result)
                store=LifecycleStore(path)
            history=store.recover(setup.setup_id)[1]
            self.assertEqual(len(history),9)
            self.assertEqual(history[-1]["state"],"RETEST_CONFIRMED")
            self.assertEqual(apply_research_sequence(store,setup,self.detect(setup,frame)),())
            self.assertEqual(store.recover(setup.setup_id)[1],history)

    def test_research_bridge_does_not_manufacture_location_or_entry_permission(self):
        setup,frame,_=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            store=LifecycleStore(Path(tmp)/"shared.db")
            store.create(setup,snapshot_ref="initial")
            with self.assertRaises(ValueError): apply_research_sequence(store,setup,self.detect(setup,frame))
            self.assertEqual(len(store.recover(setup.setup_id)[1]),1)

    def test_bridge_persists_exact_invalidation_and_never_reactivates(self):
        setup,frame,c=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            store=self.prepared(setup,frame,Path(tmp)/"shared.db")
            apply_research_sequence(store,setup,self.detect(setup,frame))
            bad=replace(frame,candles=(*frame.candles,c(26,100.,101.,88.,89.)),decision_at=1620)
            apply_research_sequence(store,setup,self.detect(setup,bad))
            self.assertEqual(store.recover(setup.setup_id)[1][-1]["state"],"INVALIDATED")
            self.assertEqual(apply_research_sequence(store,setup,self.detect(setup,frame)),())

    def test_policy_or_anchor_changes_cannot_merge_into_persisted_setup(self):
        setup,frame,c=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            store=self.prepared(setup,frame,Path(tmp)/"shared.db")
            apply_research_sequence(store,setup,self.detect(setup,frame))
            for result in (self.detect(setup,frame,policy=DetectorPolicy(liquidity_window=13)),
                           detect_sequence(replace(frame,candles=(*frame.candles,c(26,100.,101.,97.,100.5)),decision_at=1620),
                                           setup,sweep_opened_at=1560)):
                with self.assertRaises(ValueError): apply_research_sequence(store,setup,result)


if __name__=="__main__": unittest.main()
