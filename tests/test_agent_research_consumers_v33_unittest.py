from dataclasses import FrozenInstanceError, replace
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import test_agent_shared_detector_v33_unittest as shared_fixtures
from app.agent_system.setup_lifecycle_v33 import LifecycleStore, State
from app.agent_system.lifecycle_evidence_v33 import Decision
from app.agent_system.shared_detector_v33 import DetectorPolicy, detect_sequence, apply_research_sequence
from app.agent_system.research_consumers_v33 import (
    analyze_research, fast_scalp_research, tracker_research, research_candidate, full_ict_research,
    persisted_full_ict_research,
)


def analysis(tf="M1",short=False):
    setup,frame,c=shared_fixtures.fixture(tf,short)
    step=60 if tf=="M1" else 300
    return analyze_research(frame,setup,sweep_opened_at=20*step),c


class ResearchConsumerTests(unittest.TestCase):
    def test_one_detector_call_serves_all_three_consumers(self):
        with patch("app.agent_system.research_consumers_v33.detect_sequence",wraps=detect_sequence) as detector:
            report,_=analysis()
            fast=fast_scalp_research(report)
            tracker=tracker_research(report)
            candidate=research_candidate(report)
            gate=full_ict_research(report,candidate)
        self.assertEqual(detector.call_count,1)
        self.assertEqual(fast.binding,tracker.binding)
        self.assertEqual(tracker.binding,gate.binding)
        self.assertEqual(fast.fvg_bounds,candidate.fvg_bounds)
        self.assertTrue(gate.structure_allowed)
        self.assertFalse(gate.allowed)
        self.assertFalse(fast.publication_allowed)
        self.assertFalse(tracker.confirmed_for_signal)

    def test_full_source_candles_and_confirmation_times_are_preserved(self):
        report,_=analysis()
        tracker=tracker_research(report)
        sources=dict(tracker.candle_evidence)
        times=dict(tracker.event_times)
        self.assertEqual(len(sources["LIQUIDITY_SWEPT"]),2)
        self.assertEqual(len(sources["MSS_CONFIRMED"]),3)
        self.assertEqual(len(sources["DISPLACEMENT_CONFIRMED"]),13)
        self.assertEqual(len(sources["FVG_CREATED"]),3)
        self.assertEqual(times["DISPLACEMENT_CONFIRMED"],report.frame.candles[22].closed_at)
        self.assertEqual(times["FVG_CREATED"],report.frame.candles[24].closed_at)
        self.assertEqual(times["RETEST_CONFIRMED"],report.frame.candles[25].closed_at)

    def test_long_short_and_m5_profiles_keep_binding_and_real_bounds(self):
        for tf in ("M1","M5"):
            for short in (False,True):
                with self.subTest(tf=tf,short=short):
                    report,_=analysis(tf,short)
                    tracker=tracker_research(report)
                    candidate=research_candidate(report)
                    gate=full_ict_research(report,candidate)
                    self.assertEqual(tracker.binding,candidate.binding)
                    self.assertEqual(gate.binding,candidate.binding)
                    self.assertEqual(candidate.fvg_bounds,(90.,91.) if short else (109.,110.))
                    self.assertTrue(gate.structure_allowed)
                    if tf=="M1":
                        self.assertEqual(fast_scalp_research(report).fvg_bounds,candidate.fvg_bounds)
                    else:
                        with self.assertRaises(ValueError): fast_scalp_research(report)

    def test_same_binding_does_not_allow_changed_geometry_direction_or_candles(self):
        report,_=analysis()
        candidate=research_candidate(report)
        for altered in (replace(candidate,fvg_bounds=(1.,2.)),replace(candidate,direction="SHORT"),
                        replace(candidate,poi_bounds=(96.,103.)),replace(candidate,source_candles=()),
                        replace(candidate,symbol="EURUSD"),replace(candidate,timeframe="M5"),
                        replace(candidate,strategy_id="OTHER")):
            with self.subTest(candidate=altered):
                gate=full_ict_research(report,altered)
                self.assertFalse(gate.structure_allowed)
                self.assertIn("candidate_geometry_direction_or_source_candles_mismatch",gate.structure_blocks)

    def test_individual_binding_mismatches_fail(self):
        report,_=analysis()
        candidate=research_candidate(report)
        alterations={"setup_id":"other","sequence_id":"other","snapshot_ref":"other",
                     "context_ref":"other","decision_at":0,"analysis_integrity":"other","events":()}
        for key,value in alterations.items():
            changed=replace(candidate,binding=replace(candidate.binding,**{key:value}))
            self.assertFalse(full_ict_research(report,changed).structure_allowed)

    def test_cross_setup_same_bounds_and_candles_fail(self):
        report,_=analysis()
        other=analyze_research(report.frame,replace(report.setup,poi_id="different-poi"),sweep_opened_at=1200)
        self.assertFalse(full_ict_research(report,research_candidate(other)).structure_allowed)

    def test_old_snapshot_candidate_cannot_verify_against_new_snapshot(self):
        report,_=analysis()
        candidate=research_candidate(report)
        newer=analyze_research(replace(report.frame,snapshot_ref="newer"),report.setup,sweep_opened_at=1200)
        self.assertEqual(report.result.events,newer.result.events)
        self.assertFalse(full_ict_research(newer,candidate).structure_allowed)
        self.assertTrue(full_ict_research(newer,research_candidate(newer)).structure_allowed)

    def test_forming_retest_or_missing_candidate_cannot_pass(self):
        report,_=analysis()
        prefix=replace(report.frame,candles=report.frame.candles[:25],decision_at=1500,snapshot_ref="before-retest")
        earlier=analyze_research(prefix,report.setup,sweep_opened_at=1200)
        with self.assertRaises(ValueError): research_candidate(earlier)
        self.assertFalse(full_ict_research(earlier,None).structure_allowed)
        self.assertFalse(full_ict_research(report,None).structure_allowed)

    def test_terminal_invalidation_expiry_and_stale_frame_block_old_candidate(self):
        report,c=analysis()
        candidate=research_candidate(report)
        for frame in (replace(report.frame,candles=(*report.frame.candles,c(26,100.,101.,88.,89.)),decision_at=1620),
                      replace(report.frame,decision_at=report.setup.expires_at),
                      replace(report.frame,decision_at=1800)):
            later=analyze_research(frame,report.setup,sweep_opened_at=1200)
            self.assertFalse(full_ict_research(later,candidate).structure_allowed)

    def test_provisional_poi_blocks_gate_even_with_complete_shared_structure(self):
        report,_=analysis()
        provisional=analyze_research(report.frame,replace(report.setup,poi_qualified=False),sweep_opened_at=1200)
        gate=full_ict_research(provisional,research_candidate(provisional))
        self.assertFalse(gate.structure_allowed)
        self.assertIn("poi_not_qualified",gate.structure_blocks)

    def test_revised_analysis_or_event_is_rejected_by_all_views(self):
        report,_=analysis()
        first=report.result.events[0]
        revised=replace(first,evidence=replace(first.evidence,candle=replace(first.evidence.candle,low=97.)))
        altered=(replace(report,frame=replace(report.frame,ask=101.)),
                 replace(report,result=replace(report.result,events=(revised,*report.result.events[1:]))),
                 replace(report,policy=DetectorPolicy(liquidity_window=13)))
        for item in altered:
            for consumer in (fast_scalp_research,tracker_research,research_candidate):
                with self.assertRaises(ValueError): consumer(item)
            with self.assertRaises(ValueError): full_ict_research(item,None)

    def test_research_binding_survives_persistence_restart_without_redetection(self):
        report,_=analysis()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"research.db"
            fixture=shared_fixtures.SharedDetectorTests()
            store=fixture.prepared(report.setup,report.frame,path)
            apply_research_sequence(store,report.setup,report.result)
            before=store.recover(report.setup.setup_id)[1]
            reopened=LifecycleStore(path)
            self.assertEqual(apply_research_sequence(reopened,report.setup,report.result),())
            gate=full_ict_research(report,research_candidate(report))
            self.assertTrue(gate.structure_allowed)
            self.assertEqual(gate.binding,tracker_research(report).binding)
            self.assertEqual(before,reopened.recover(report.setup.setup_id)[1])
            self.assertEqual(before[-1]["state"],State.RETEST_CONFIRMED.value)

    def test_views_are_frozen_and_research_candidate_has_no_trade_prices(self):
        report,_=analysis()
        candidate=research_candidate(report)
        with self.assertRaises(FrozenInstanceError): candidate.poi_id="changed"
        for name in ("entry","stop_loss","take_profits"):
            self.assertFalse(hasattr(candidate,name))

    def test_persistent_gate_reads_current_state_and_exact_event_ids(self):
        report,_=analysis()
        candidate=research_candidate(report)
        with tempfile.TemporaryDirectory() as tmp:
            helper=shared_fixtures.SharedDetectorTests()
            store=helper.prepared(report.setup,report.frame,Path(tmp)/"state.db")
            self.assertFalse(persisted_full_ict_research(store,report,candidate).structure_allowed)
            apply_research_sequence(store,report.setup,report.result)
            before=store.recover(report.setup.setup_id)[1]
            gate=persisted_full_ict_research(store,report,candidate)
            self.assertTrue(gate.structure_allowed)
            self.assertEqual(gate.persistent_event_ids,tuple(e["event_id"] for e in before[-5:]))
            self.assertFalse(gate.allowed)
            self.assertEqual(before,store.recover(report.setup.setup_id)[1])

    def test_persistent_invalidation_or_expiry_blocks_previously_valid_candidate(self):
        for terminal in (State.INVALIDATED,State.EXPIRED):
            with self.subTest(terminal=terminal),tempfile.TemporaryDirectory() as tmp:
                report,_=analysis()
                candidate=research_candidate(report)
                helper=shared_fixtures.SharedDetectorTests()
                store=helper.prepared(report.setup,report.frame,Path(tmp)/"state.db")
                apply_research_sequence(store,report.setup,report.result)
                at=report.setup.expires_at if terminal==State.EXPIRED else report.frame.decision_at+1
                store.advance(report.setup.setup_id,terminal,Decision("external_terminal"),event_key="terminal",
                    at=at,snapshot_ref="terminal-frame",feed_fresh=False)
                # Even an intact old snapshot and candidate cannot bypass the DB state.
                self.assertTrue(full_ict_research(report,candidate).structure_allowed)
                gate=persisted_full_ict_research(store,report,candidate)
                self.assertFalse(gate.structure_allowed)
                self.assertIn("persistent_current_state_not_confirmed",gate.structure_blocks)

    def test_missing_or_other_persistent_store_fails_closed(self):
        report,_=analysis()
        candidate=research_candidate(report)
        self.assertFalse(persisted_full_ict_research(None,report,candidate).structure_allowed)
        with tempfile.TemporaryDirectory() as tmp:
            store=LifecycleStore(Path(tmp)/"empty.db")
            gate=persisted_full_ict_research(store,report,candidate)
            self.assertFalse(gate.structure_allowed)
            self.assertIn("persistent_lifecycle_unavailable",gate.structure_blocks)


if __name__=="__main__": unittest.main()
