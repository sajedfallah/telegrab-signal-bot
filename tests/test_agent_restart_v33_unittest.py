"""Real subprocess restarts/crashes against temporary fixture databases only."""
import json
from pathlib import Path
import subprocess
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor

import test_agent_lifecycle_v33_unittest as fixtures
from app.agent_system.lifecycle_evidence_v33 import Decision, Observation
from app.agent_system.setup_lifecycle_v33 import LifecycleStore, State


CHILD = r'''
import json, os, sqlite3, sys
from app.agent_system.setup_lifecycle_v33 import LifecycleStore, GATES
path,sid,mode=sys.argv[1:]
store=LifecycleStore(path)
if mode == "recover":
    spec,events=store.recover(sid)
    print(json.dumps(dict(setup_id=spec.setup_id,state=events[-1]["state"],events=len(events))))
elif mode == "reserve_crash":
    assert store.reserve_publication(sid,"fingerprint-1",at=1800,snapshot_ref="snapshot-1",
        context_ref="context-1",gates={g:True for g in GATES})
    os._exit(23)
elif mode == "uncommitted_crash":
    db=sqlite3.connect(path)
    db.execute("BEGIN IMMEDIATE")
    db.execute("""INSERT INTO v33_events(event_id,setup_id,event_key,state,at,snapshot_ref,payload)
        SELECT 'uncommitted-crash',setup_id,'crash','CANCELLED',1801,snapshot_ref,payload
        FROM v33_events WHERE setup_id=? ORDER BY seq DESC LIMIT 1""",(sid,))
    os._exit(29)
'''


class ProcessRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.LifecycleTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def child(self,mode,expected=0):
        result=subprocess.run([sys.executable,"-c",CHILD,str(self.fixture.path),self.fixture.sid,mode],
            cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,expected,result.stderr)
        return result

    def test_active_state_and_evidence_survive_fresh_process(self):
        self.fixture.sequence()
        data=json.loads(self.child("recover").stdout)
        self.assertEqual(data,{"setup_id":self.fixture.sid,"state":"ENTRY_READY","events":10})

    def test_committed_reservation_survives_crash_before_delivery(self):
        self.fixture.sequence()
        self.child("reserve_crash",23)
        self.fixture.store=LifecycleStore(self.fixture.path)
        self.assertFalse(self.fixture.claim())
        self.assertEqual(self.fixture.store.recover(self.fixture.sid)[1][-1]["state"],"ENTRY_READY")

    def test_uncommitted_event_is_rolled_back_after_abrupt_exit(self):
        self.fixture.sequence()
        before=self.fixture.store.recover(self.fixture.sid)
        self.child("uncommitted_crash",29)
        self.assertEqual(before,LifecycleStore(self.fixture.path).recover(self.fixture.sid))

    def test_invalidation_survives_fresh_process(self):
        self.fixture.event(State.INVALIDATED,Decision("poi_invalidated"))
        data=json.loads(self.child("recover").stdout)
        self.assertEqual(data["state"],"INVALIDATED")
        with self.assertRaises(ValueError):
            self.fixture.event(State.POI_SELECTED,Observation(fixtures.candle(10),"reactivate"))

    def test_expiration_survives_fresh_process(self):
        self.fixture.store.expire_due(at=6000,snapshot_ref="expiry")
        self.assertEqual(json.loads(self.child("recover").stdout)["state"],"EXPIRED")

    def test_concurrent_duplicate_events_append_once(self):
        def select(_):
            return self.fixture.event(State.POI_SELECTED,Observation(fixtures.candle(10),"select"))
        with ThreadPoolExecutor(max_workers=4) as pool:
            ids=list(pool.map(select,range(8)))
        self.assertEqual(len(set(ids)),1)
        self.assertEqual(len(self.fixture.store.recover(self.fixture.sid)[1]),2)


if __name__=="__main__": unittest.main()
