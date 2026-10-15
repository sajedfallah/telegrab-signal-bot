"""Isolated synthetic fixtures only. Run with Python's standard unittest runner."""
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing

from app.agent_system.lifecycle_evidence_v33 import Candle, Decision, Displacement, FVG, MSS, Observation, Retest, Sweep
from app.agent_system.setup_lifecycle_v33 import GATES, LifecycleStore, Setup, State


def candle(t, o=100., h=102., l=98., c=100., tf="M1"):
    seconds = 60 if tf == "M1" else 300
    return Candle("XAUUSD", tf, t * seconds, (t+1)*seconds, o, h, l, c, "isolated_fixture")


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/"lifecycle.db"
        self.store = LifecycleStore(self.path)
        self.spec = Setup("XAUUSD", "ICT_FAST_SCALP_M1", "LONG", "M1", "context-1",
                          "poi-1", candle(0), 60, 97., 103., True, 90., 600, 6000)
        self.sid = self.store.create(self.spec, snapshot_ref="snapshot-1")

    def event(self, state, evidence, at=None, key=None, **kwargs):
        at=getattr(self,"clock",1800) if at is None else at
        return self.store.advance(self.sid, state, evidence, event_key=key or state.value,
                                  at=at, snapshot_ref="snapshot-1", feed_fresh=True, **kwargs)

    def c(self,*args):
        return candle(*args,tf=self.spec.timeframe)

    def location(self):
        for stage in (State.POI_SELECTED, State.APPROACHING_POI, State.POI_TOUCHED):
            self.event(stage, Observation(self.c(10), "bound POI location"))

    def sequence(self, through=State.ENTRY_READY):
        self.location()
        self.sweep = Sweep(self.c(11,100.,102.,96.,100.), self.c(9))
        self.sweep_id = self.event(State.LIQUIDITY_SWEPT, self.sweep)
        if through == State.LIQUIDITY_SWEPT: return
        self.mss = MSS(self.c(12,100.,106.,99.,105.), self.c(8), self.c(9), self.sweep_id)
        self.mss_id = self.event(State.MSS_CONFIRMED, self.mss)
        if through == State.MSS_CONFIRMED: return
        self.displacement = Displacement(self.c(13,105.,110.,104.,109.),
            tuple(self.c(t,100.,102.,98.,101.) for t in (7,8,9)), self.mss_id)
        self.disp_id = self.event(State.DISPLACEMENT_CONFIRMED, self.displacement)
        if through == State.DISPLACEMENT_CONFIRMED: return
        self.fvg = FVG(self.displacement.candle, self.c(14,109.,114.,108.,113.),
                       self.c(15,113.,115.,112.,114.), self.disp_id)
        self.fvg_id = self.event(State.FVG_CREATED, self.fvg)
        if through == State.FVG_CREATED: return
        self.retest = Retest(self.c(16,113.,114.,110.,111.), self.fvg_id)
        self.event(State.RETEST_CONFIRMED, self.retest)
        if through == State.RETEST_CONFIRMED: return
        self.event(State.ENTRY_READY, Decision("research readiness only"))

    def claim(self, **overrides):
        args = dict(at=1800, snapshot_ref="snapshot-1", context_ref="context-1", gates={g:True for g in GATES})
        args.update(overrides)
        return self.store.reserve_publication(self.sid,"fingerprint-1",**args)

    def test_complete_recovery_and_append_only(self):
        self.sequence()
        original = self.store.recover(self.sid)
        self.assertEqual(original, LifecycleStore(self.path).recover(self.sid))
        self.assertEqual(original[1][-1]["state"], "ENTRY_READY")
        self.assertEqual(len(original[1]), 10)
        with closing(sqlite3.connect(self.path)) as db:
            for sql in ("UPDATE v33_events SET state='ENTRY_READY'", "DELETE FROM v33_events", "UPDATE v33_setups SET spec='{}'"):
                with self.assertRaises(sqlite3.IntegrityError): db.execute(sql)

    def test_immutable_identity(self):
        with self.assertRaises(FrozenInstanceError): self.spec.poi_id = "other"
        self.assertNotEqual(replace(self.spec, poi_id="other").setup_id, self.sid)
        self.assertEqual(self.sid, self.store.create(self.spec,snapshot_ref="snapshot-2"))
        self.assertEqual(len(self.store.recover(self.sid)[1]),1)

    def test_cannot_skip_stages(self):
        with self.assertRaises(ValueError): self.event(State.ENTRY_READY, Decision("skip"))
        self.assertEqual(len(self.store.recover(self.sid)[1]),1)

    def test_duplicate_event_is_idempotent(self):
        ev = Observation(candle(10),"select")
        a = self.event(State.POI_SELECTED,ev)
        b = self.event(State.POI_SELECTED,ev)
        self.assertEqual(a,b)
        self.assertEqual(len(self.store.recover(self.sid)[1]),2)
        with self.assertRaises(ValueError): self.event(State.POI_SELECTED,Observation(candle(10),"changed"))

    def test_terminal_states_cannot_reactivate(self):
        for state in (State.INVALIDATED, State.CANCELLED, State.EXPIRED):
            with self.subTest(state=state):
                spec=replace(self.spec,poi_id=state.value)
                self.sid=self.store.create(spec,snapshot_ref="s")
                self.event(state,Decision("terminal"),at=6000 if state == State.EXPIRED else 1800)
                with self.assertRaises(ValueError): self.event(State.POI_SELECTED,Observation(candle(10),"retry"),at=6001)

    def test_expiration_and_early_expiration(self):
        with self.assertRaises(ValueError): self.event(State.EXPIRED,Decision("too early"),at=5999)
        with self.assertRaises(ValueError): self.event(State.POI_SELECTED,Observation(candle(10),"late"),at=6000)
        self.event(State.EXPIRED,Decision("deadline reached"),at=6000)

    def test_stale_missing_and_unclosed_fail(self):
        for fresh in (False, None, 1):
            with self.assertRaises(ValueError):
                self.store.advance(self.sid,State.POI_SELECTED,Observation(candle(10),"location"),
                    event_key="select",at=1800,snapshot_ref="s",feed_fresh=fresh)
        with self.assertRaises(ValueError): self.event(State.POI_SELECTED,Observation(candle(30),"future"))

    def test_foreign_candle_and_source(self):
        for c in (replace(candle(10),symbol="EURUSD"), candle(10,tf="M5"), replace(candle(10),source="other")):
            with self.assertRaises(ValueError): self.event(State.POI_SELECTED,Observation(c,"foreign"))

    def test_mss_before_sweep_and_cross_setup_reference(self):
        self.sequence(State.LIQUIDITY_SWEPT)
        for ev in (MSS(candle(10,100.,106.,99.,105.),candle(8),candle(9),self.sweep_id),
                   MSS(candle(12,100.,106.,99.,105.),candle(8),candle(9),"another-setup")):
            with self.assertRaises(ValueError): self.event(State.MSS_CONFIRMED,ev)

    def test_pre_mss_fvg_rejected(self):
        self.sequence(State.DISPLACEMENT_CONFIRMED)
        with self.assertRaises(ValueError):
            self.event(State.FVG_CREATED,FVG(candle(10),candle(11),candle(12),self.disp_id))

    def test_retest_before_formation_or_other_setup(self):
        self.sequence(State.FVG_CREATED)
        for ev in (Retest(candle(15),self.fvg_id),Retest(candle(16),"foreign-fvg")):
            with self.assertRaises(ValueError): self.event(State.RETEST_CONFIRMED,ev)

    def test_displacement_requires_measured_body(self):
        self.sequence(State.MSS_CONFIRMED)
        with self.assertRaises(ValueError):
            self.event(State.DISPLACEMENT_CONFIRMED,Displacement(candle(13),tuple(candle(t,100.,102.,98.,101.) for t in (7,8,9)),self.mss_id))

    def test_same_candle_displacement_is_explicit_exception(self):
        self.sequence(State.MSS_CONFIRMED)
        ev=Displacement(self.mss.candle,tuple(candle(t,100.,102.,98.,101.) for t in (7,8,9)),self.mss_id)
        with self.assertRaises(ValueError): self.event(State.DISPLACEMENT_CONFIRMED,ev)
        self.spec=replace(self.spec,allow_same_candle_displacement=True)
        self.sid=self.store.create(self.spec,snapshot_ref="snapshot-1")
        self.sequence(State.MSS_CONFIRMED)
        self.event(State.DISPLACEMENT_CONFIRMED,replace(ev,mss_event=self.mss_id))

    def test_provisional_poi_never_entry_ready(self):
        self.sid=self.store.create(replace(self.spec,poi_qualified=False),snapshot_ref="snapshot-1")
        self.sequence(State.RETEST_CONFIRMED)
        with self.assertRaises(ValueError): self.event(State.ENTRY_READY,Decision("provisional"))

    def test_publication_persists_deduplication(self):
        self.sequence()
        self.assertTrue(self.claim())
        self.store=LifecycleStore(self.path)
        self.assertFalse(self.claim())
        first=self.store.confirm_publication(self.sid,"fingerprint-1","telegram-shadow-receipt",at=1801)
        again=self.store.confirm_publication(self.sid,"fingerprint-1","telegram-shadow-receipt",at=1801)
        self.assertEqual(first,again)
        self.assertEqual(self.store.recover(self.sid)[1][-1]["state"],"SIGNAL_PUBLISHED")

    def test_publication_cannot_bypass_gate_or_identity(self):
        self.sequence()
        for args in (dict(snapshot_ref="other"),dict(context_ref="other"),dict(at=6000),dict(gates={g:False for g in GATES})):
            with self.assertRaises(ValueError): self.claim(**args)
        with self.assertRaises(ValueError): self.event(State.SIGNAL_PUBLISHED,Decision("bypass"))

    def test_concurrent_claim_only_once(self):
        self.sequence()
        with ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(lambda _:self.claim(),range(8)))
        self.assertEqual(results.count(True),1)

    def test_reject_unknown_and_legacy_schema(self):
        for version in (0,99):
            path=Path(self.temp.name)/f"unknown-{version}.db"
            with closing(sqlite3.connect(path)) as db:
                db.execute("CREATE TABLE unrelated (x INTEGER)")
                db.execute(f"PRAGMA user_version={version}")
                db.commit()
            with self.assertRaises(ValueError): LifecycleStore(path)

    def test_m5_uses_same_contract(self):
        self.spec=replace(self.spec,strategy="ICT_STANDARD_M5",timeframe="M5",poi_origin=candle(0,tf="M5"),poi_eligible_at=300,created_at=3000,expires_at=30000)
        self.sid=self.store.create(self.spec,snapshot_ref="snapshot-1")
        self.clock=9000
        self.sequence()
        self.assertEqual(self.store.recover(self.sid)[1][-1]["state"],"ENTRY_READY")

    def test_expiry_batch_is_deterministic_and_idempotent(self):
        self.assertEqual(self.store.expire_due(at=5999,snapshot_ref="clock-1"),())
        self.assertEqual(len(self.store.expire_due(at=6000,snapshot_ref="clock-2")),1)
        self.assertEqual(self.store.expire_due(at=6001,snapshot_ref="clock-3"),())
        self.assertEqual(self.store.recover(self.sid)[1][-1]["at"],6000)

    def test_invalid_evidence_rolls_back(self):
        self.sequence(State.LIQUIDITY_SWEPT)
        before=self.store.recover(self.sid)
        with self.assertRaises(ValueError):
            self.event(State.MSS_CONFIRMED,MSS(candle(12),candle(8),candle(9),self.sweep_id))
        self.assertEqual(before,self.store.recover(self.sid))

    def test_mutable_displacement_baseline_rejected(self):
        self.sequence(State.MSS_CONFIRMED)
        with self.assertRaises(ValueError):
            self.event(State.DISPLACEMENT_CONFIRMED,Displacement(candle(13),[candle(9)],self.mss_id))

    def test_stale_publication_and_unreserved_receipt_rejected(self):
        self.sequence()
        with self.assertRaises(ValueError): self.claim(at=1831)
        with self.assertRaises(ValueError): self.store.confirm_publication(self.sid,"missing","receipt",at=1801)

    def test_invalid_candles_and_backdated_event(self):
        with self.assertRaises(ValueError): candle(0,h=float("nan"))
        with self.assertRaises(ValueError): candle(0,l=110.)
        self.event(State.POI_SELECTED,Observation(candle(10),"select"))
        with self.assertRaises(ValueError): self.event(State.APPROACHING_POI,Observation(candle(10),"backdated"),at=1799)


if __name__ == "__main__":
    unittest.main()
