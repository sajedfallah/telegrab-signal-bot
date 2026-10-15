"""End-to-end research tests: actual contracts, detector, SQLite and persisted gate.

All market inputs are isolated synthetic fixtures. No detector/store/gate mocks.
"""
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from contextlib import closing
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest

import test_agent_shared_detector_v33_unittest as shared_fixtures
from app.agent_system.contracts import MarketSnapshot
from app.agent_system.lifecycle_evidence_v33 import Candle
from app.agent_system.research_pipeline_v33 import LocationProof, run_research_snapshot
from app.agent_system.research_consumers_v33 import persisted_full_ict_research
from app.agent_system.setup_lifecycle_v33 import LifecycleStore, State


def sample(tf="M1",short=False,count=26):
    setup,frame,c=shared_fixtures.fixture(tf,short)
    bars=list(frame.candles)
    bars[16]=c(16,103.1,103.3,102.8,103.15)
    bars[17]=c(17,103.2,103.25,103.05,103.1)
    bars[18]=c(18,103.1,103.2,102.5,102.8)
    proof=LocationProof(bars[16].identity,bars[17].identity,bars[18].identity,.5)
    bars=bars[:count]
    rows=tuple(dict(time=b.opened_at,closed_at=b.closed_at,open=b.open,high=b.high,low=b.low,close=b.close) for b in bars)
    snap=MarketSnapshot(snapshot_id=f"integration-{tf}-{short}-{count}",symbol="XAUUSD",
        source="shared_fixture",as_of=datetime.fromtimestamp(bars[-1].closed_at,timezone.utc),
        timeframes={tf:rows},bid=100.,ask=100.2,data_freshness_ms=0)
    return setup,snap,proof,c


class PipelineIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/"isolated.db"

    def run_snapshot(self,setup,snap,proof=None,**kwargs):
        args=dict(db_path=self.path,sweep_opened_at=1200 if setup.timeframe=="M1" else 6000,
                  context_ref=setup.context_ref,location=proof)
        args.update(kwargs)
        return run_research_snapshot(snap,setup,**args)

    def test_complete_snapshot_to_persisted_gate_on_both_profiles_and_directions(self):
        for tf in ("M1","M5"):
            for short in (False,True):
                with self.subTest(tf=tf,short=short):
                    setup,snap,proof,_=sample(tf,short)
                    result=self.run_snapshot(setup,snap,proof,db_path=Path(self.temp.name)/f"{tf}-{short}.db")
                    self.assertEqual(result.status,"STRUCTURE_VERIFIED",result.blocks)
                    self.assertEqual(result.lifecycle_state,State.RETEST_CONFIRMED)
                    self.assertEqual(len(result.new_event_ids),9)
                    self.assertEqual(len(result.gate.persistent_event_ids),5)
                    self.assertEqual(result.candidate.binding,result.gate.binding)
                    self.assertFalse(result.publication_allowed)
                    self.assertFalse(result.gate.allowed)
                    events=LifecycleStore(Path(self.temp.name)/f"{tf}-{short}.db").recover(setup.setup_id)[1]
                    self.assertEqual(events[0]["at"],int(snap.as_of.timestamp()))

    def test_m1_m5_pipeline_uses_same_synchronized_snapshot_context_and_poi(self):
        setup1,snap1,proof1,_=sample("M1")
        setup5,snap5,proof5,_=sample("M5")
        offset=7800-1560
        shifted=[]; mapping={}
        for row in snap1.timeframes["M1"]:
            old=Candle("XAUUSD","M1",row["time"],row["closed_at"],row["open"],row["high"],row["low"],row["close"],snap1.source)
            new=replace(old,opened_at=old.opened_at+offset,closed_at=old.closed_at+offset)
            mapping[old.identity]=new.identity
            shifted.append({**row,"time":new.opened_at,"closed_at":new.closed_at})
        setup1=replace(setup1,created_at=setup1.created_at+offset,expires_at=setup1.expires_at+offset,
                       poi_origin=setup5.poi_origin,poi_eligible_at=setup5.poi_eligible_at)
        proof1=replace(proof1,selected_candle_id=mapping[proof1.selected_candle_id],
            approaching_candle_id=mapping[proof1.approaching_candle_id],touched_candle_id=mapping[proof1.touched_candle_id])
        synchronized=snap5.model_copy(update={"snapshot_id":"integration-synchronized-dual",
            "timeframes":{"M1":tuple(shifted),"M5":snap5.timeframes["M5"]}})
        m1=self.run_snapshot(setup1,synchronized,proof1,sweep_opened_at=1200+offset)
        m5=self.run_snapshot(setup5,synchronized,proof5)
        self.assertEqual(m1.status,"STRUCTURE_VERIFIED",m1.blocks)
        self.assertEqual(m5.status,"STRUCTURE_VERIFIED",m5.blocks)
        self.assertEqual(m1.gate.binding.snapshot_ref,m5.gate.binding.snapshot_ref)
        self.assertEqual(m1.gate.binding.context_ref,m5.gate.binding.context_ref)
        self.assertEqual(m1.gate.binding.decision_at,m5.gate.binding.decision_at)
        self.assertEqual(m1.candidate.poi_id,m5.candidate.poi_id)
        self.assertNotEqual(m1.setup_id,m5.setup_id)

    def test_invalid_snapshot_fails_before_creating_database(self):
        setup,snap,proof,_=sample()
        variants=(snap.model_copy(update={"data_freshness_ms":30001}),
                  snap.model_copy(update={"missing_data":("candles:H1",)}),
                  snap.model_copy(update={"ask":None}),
                  snap.model_copy(update={"timeframes":{}}))
        for invalid in variants:
            self.assertEqual(self.run_snapshot(setup,invalid,proof).status,"BLOCKED")
            self.assertFalse(self.path.exists())

    def test_legacy_missing_close_or_context_mismatch_never_writes(self):
        setup,snap,proof,_=sample()
        rows=[dict(r) for r in snap.timeframes["M1"]]; del rows[0]["closed_at"]
        invalid=snap.model_copy(update={"timeframes":{"M1":tuple(rows)}})
        self.assertEqual(self.run_snapshot(setup,invalid,proof).status,"BLOCKED")
        self.assertEqual(self.run_snapshot(setup,snap,proof,context_ref="different-context").status,"BLOCKED")
        self.assertFalse(self.path.exists())

    def test_invalid_detector_policy_fails_before_creating_database(self):
        setup,snap,proof,_=sample()
        for index,invalid in enumerate((0,False,{},"invalid")):
            with self.subTest(policy=invalid):
                self.path=Path(self.temp.name)/f"invalid-policy-{index}.db"
                result=self.run_snapshot(setup,snap,proof,policy=invalid)
                self.assertEqual(result.status,"BLOCKED")
                self.assertFalse(self.path.exists())

    def test_new_setup_requires_exact_chronological_location_evidence(self):
        setup,snap,proof,_=sample()
        for bad in (None,replace(proof,touched_candle_id="unknown"),
                    replace(proof,approaching_candle_id=proof.touched_candle_id),
                    replace(proof,max_approach_distance=.01)):
            self.assertEqual(self.run_snapshot(setup,snap,bad).status,"BLOCKED")
            self.assertFalse(self.path.exists())

    def test_partial_then_complete_then_retry_does_not_duplicate_history(self):
        setup,partial,proof,_=sample(count=21)
        first=self.run_snapshot(setup,partial,proof)
        self.assertEqual(first.status,"WATCH",first.blocks)
        self.assertEqual(first.lifecycle_state,State.LIQUIDITY_SWEPT)
        setup,full,_,_=sample()
        final=self.run_snapshot(setup,full)
        self.assertEqual(final.status,"STRUCTURE_VERIFIED",final.blocks)
        self.assertEqual(len(final.new_event_ids),4)
        again=self.run_snapshot(setup,full)
        self.assertEqual(again.new_event_ids,())
        self.assertEqual(again.candidate,final.candidate)
        self.assertEqual(len(LifecycleStore(self.path).recover(setup.setup_id)[1]),9)

    def test_forming_retest_is_not_stored_until_close(self):
        setup,snap,proof,_=sample()
        live=snap.model_copy(update={"as_of":datetime.fromtimestamp(1530,timezone.utc)})
        watching=self.run_snapshot(setup,live,proof)
        self.assertEqual(watching.status,"WATCH",watching.blocks)
        self.assertEqual(watching.lifecycle_state,State.FVG_CREATED)
        self.assertIsNone(watching.candidate)
        done=self.run_snapshot(setup,snap)
        self.assertEqual(done.status,"STRUCTURE_VERIFIED",done.blocks)
        self.assertEqual(len(done.new_event_ids),1)

    def test_later_closed_invalidation_blocks_old_candidate_and_survives_restart(self):
        setup,snap,proof,c=sample()
        first=self.run_snapshot(setup,snap,proof)
        invalid=c(26,100.,101.,88.,89.)
        row=dict(time=invalid.opened_at,closed_at=invalid.closed_at,open=invalid.open,
                 high=invalid.high,low=invalid.low,close=invalid.close)
        later=snap.model_copy(update={"snapshot_id":"integration-invalidated", "as_of":datetime.fromtimestamp(1620,timezone.utc),
            "timeframes":{"M1":(*snap.timeframes["M1"],row)}})
        result=self.run_snapshot(setup,later,candidate=first.candidate)
        self.assertEqual(result.status,"TERMINAL",result.blocks)
        self.assertEqual(result.lifecycle_state,State.INVALIDATED)
        gate=persisted_full_ict_research(LifecycleStore(self.path),first.analysis,first.candidate)
        self.assertFalse(gate.structure_allowed)
        repeated=self.run_snapshot(setup,later)
        self.assertEqual(repeated.status,"TERMINAL")
        self.assertEqual(repeated.new_event_ids,())

    def test_expiry_blocks_previously_complete_sequence(self):
        setup,snap,proof,_=sample()
        first=self.run_snapshot(setup,snap,proof)
        expired=snap.model_copy(update={"snapshot_id":"integration-expired", "as_of":datetime.fromtimestamp(setup.expires_at,timezone.utc)})
        result=self.run_snapshot(setup,expired,candidate=first.candidate)
        self.assertEqual(result.status,"TERMINAL",result.blocks)
        self.assertEqual(result.lifecycle_state,State.EXPIRED)

    def test_revised_committed_candle_and_foreign_candidate_cannot_advance(self):
        setup,snap,proof,_=sample()
        first=self.run_snapshot(setup,snap,proof)
        before=LifecycleStore(self.path).recover(setup.setup_id)[1]
        rows=[dict(r) for r in snap.timeframes["M1"]]; rows[20]["low"]=97.5
        revised=snap.model_copy(update={"timeframes":{"M1":tuple(rows)}})
        self.assertEqual(self.run_snapshot(setup,revised).status,"BLOCKED")
        wrong=replace(first.candidate,fvg_bounds=(1.,2.))
        self.assertEqual(self.run_snapshot(setup,snap,candidate=wrong).status,"BLOCKED")
        self.assertEqual(before,LifecycleStore(self.path).recover(setup.setup_id)[1])

    def test_provisional_poi_cannot_pass_persistent_gate(self):
        setup,snap,proof,_=sample()
        provisional=replace(setup,poi_qualified=False)
        result=self.run_snapshot(provisional,snap,proof)
        self.assertEqual(result.status,"BLOCKED",result.blocks)
        self.assertIn("poi_not_qualified",result.blocks)
        self.assertEqual(result.lifecycle_state,State.RETEST_CONFIRMED)

    def test_snapshot_backdating_and_stale_feed_do_not_mutate_existing_setup(self):
        setup,snap,proof,_=sample()
        self.run_snapshot(setup,snap,proof)
        before=LifecycleStore(self.path).recover(setup.setup_id)[1]
        for update in ({"data_freshness_ms":31000},{"as_of":datetime.fromtimestamp(1530,timezone.utc)}):
            result=self.run_snapshot(setup,snap.model_copy(update=update))
            self.assertEqual(result.status,"BLOCKED")
        self.assertEqual(before,LifecycleStore(self.path).recover(setup.setup_id)[1])

    def test_no_publication_reservation_or_trade_permission_is_created(self):
        setup,snap,proof,_=sample()
        result=self.run_snapshot(setup,snap,proof)
        self.assertFalse(result.publication_allowed)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM v33_publications").fetchone()[0],0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM v33_events WHERE state IN ('ENTRY_READY','SIGNAL_PUBLISHED')").fetchone()[0],0)

    def test_partial_pipeline_resumes_after_real_process_exit(self):
        script=r'''
import json,sys
sys.path.insert(0,'tests')
from test_agent_pipeline_v33_unittest import sample
from app.agent_system.research_pipeline_v33 import run_research_snapshot
setup,snap,proof,_=sample(count=21)
r=run_research_snapshot(snap,setup,db_path=sys.argv[1],sweep_opened_at=1200,context_ref=setup.context_ref,location=proof)
print(json.dumps(dict(status=r.status,state=r.lifecycle_state.value)))
'''
        child=subprocess.run([sys.executable,"-c",script,str(self.path)],cwd=Path(__file__).resolve().parents[1],
            capture_output=True,text=True,timeout=30)
        self.assertEqual(child.returncode,0,child.stderr)
        self.assertEqual(json.loads(child.stdout),{"status":"WATCH","state":"LIQUIDITY_SWEPT"})
        setup,snap,_,_=sample()
        result=self.run_snapshot(setup,snap)
        self.assertEqual(result.status,"STRUCTURE_VERIFIED",result.blocks)
        self.assertEqual(len(result.new_event_ids),4)


if __name__=="__main__": unittest.main()
