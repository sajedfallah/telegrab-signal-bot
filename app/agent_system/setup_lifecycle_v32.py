"""V3.2 shadow-only setup lifecycle store and conservative POI binding.

SQLite is isolated from MT5/production databases. No order or signal permissions.
"""
from __future__ import annotations

import json
import os
import sqlite3
from copy import deepcopy
from contextlib import closing
from pathlib import Path

from .poi_scanner_v23 import scan_pois
from .setup_tracker_v31 import track_ict_setup

_STAGES={"SWEEP_OBSERVED":1,"MSS_OBSERVED":2,"FVG_OBSERVED":3,"RETEST_OBSERVED":4}
_SCHEMA="""CREATE TABLE IF NOT EXISTS setup_lifecycle (
 setup_id TEXT PRIMARY KEY, symbol TEXT NOT NULL, timeframe TEXT NOT NULL,
 direction TEXT NOT NULL, sweep_time TEXT NOT NULL,
 poi_json TEXT NOT NULL, state TEXT NOT NULL,
 evidence_json TEXT NOT NULL, first_seen TEXT NOT NULL, last_seen TEXT NOT NULL
);"""


def _eligible_poi(snapshot, tracker):
    """Sweep candle must actually overlap a directional, non-rejected HTF POI."""
    rows=list(snapshot.timeframes.get(tracker["timeframe"],()))
    candle=next((r for r in rows[:-1] if str(r.get("time"))==str(tracker["sweep_time"])),None)
    if candle is None: return None
    low,high=float(candle["low"]),float(candle["high"])
    side=tracker["direction"]
    for p in scan_pois(snapshot):
        if (p["source"] not in {"FVG","OB","DAILY_QUADRANT"}
            or p["direction"] not in {side,"BOTH"}
            or p["quality"]=="TOO_WIDE"):
            continue
        if low<=float(p["high"]) and high>=float(p["low"]):
            return {k:p[k] for k in ("source","timeframe","low","high","direction","quality")}
    return None


def observe(snapshot, timeframe: str, db_path: str | None = None) -> dict:
    source=track_ict_setup(snapshot,timeframe)
    result=deepcopy(source)
    result["blocks"]=list(source.get("blocks") or [])
    result["timeframe"]=timeframe
    result["poi_bound"]=False
    result["bound_poi"]=None
    result["persistent"]=False
    if result.get("status") not in _STAGES or not result.get("setup_id"):
        return result
    poi=_eligible_poi(snapshot,result)
    if poi is None:
        result["blocks"].append("sweep_not_bound_to_qualified_htf_poi")
        # An existing identity must not silently survive loss of its POI.
        # Never create a database merely to record an unbound observation.
        if db_path:
            path=Path(db_path).resolve()
            if (path.is_file() and path.suffix.lower() in {".sqlite",".sqlite3",".db"}
                and not any(p.lower()=="nexus_deploy" for p in path.parts)):
                with closing(sqlite3.connect(str(path),timeout=10)) as db, db:
                    db.execute("BEGIN IMMEDIATE")
                    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='setup_lifecycle'").fetchone():
                        prior=db.execute("SELECT evidence_json FROM setup_lifecycle WHERE setup_id=?",(result["setup_id"],)).fetchone()
                        if prior:
                            result=json.loads(prior[0])
                            result.update(status="INVALIDATED",poi_bound=False,persistent=True,confirmed_for_signal=False)
                            result["blocks"]=list(dict.fromkeys([*result.get("blocks",[]),"bound_poi_unavailable"]))
                            db.execute("UPDATE setup_lifecycle SET state=?,evidence_json=?,last_seen=? WHERE setup_id=?",
                                       ("INVALIDATED",json.dumps(result),snapshot.as_of.isoformat(),result["setup_id"]))
        return result
    result["poi_bound"]=True
    result["bound_poi"]=poi
    # Explicit opt-in; no writes into legacy production DB.
    if not db_path:
        result["blocks"].append("lifecycle_persistence_not_configured")
        return result
    path=Path(db_path).resolve()
    if (path.suffix.lower() not in {".sqlite",".sqlite3",".db"}
        or any(p.lower()=="nexus_deploy" for p in path.parts)):
        result["blocks"].append("invalid_lifecycle_db_path")
        return result
    path.parent.mkdir(parents=True,exist_ok=True)
    now=snapshot.as_of.isoformat()
    with closing(sqlite3.connect(str(path),timeout=10)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        db.execute(_SCHEMA)
        existing=db.execute("SELECT state,poi_json,evidence_json FROM setup_lifecycle WHERE setup_id=?",
                            (result["setup_id"],)).fetchone()
        if existing:
            previous_state,previous_poi,previous_data=existing
            result["bound_poi"]=json.loads(previous_poi)
            if json.loads(previous_poi)!=poi:
                result["blocks"].append("poi_binding_changed")
                result["status"]="INVALIDATED"
            elif previous_state=="INVALIDATED":
                result["status"]="INVALIDATED"
                result["blocks"].append("previously_invalidated")
            elif _STAGES.get(previous_state,0)>_STAGES[result["status"]]:
                # Never regress from a previously observed later stage.
                # Restore recorded evidence instead of assembling a new sequence.
                prior=json.loads(previous_data)
                result.update({k:v for k,v in prior.items() if k in
                    {"status","mss_time","fvg_time","retest_time","fvg"}})
            db.execute("""UPDATE setup_lifecycle SET state=?,evidence_json=?,last_seen=?
                          WHERE setup_id=?""",(result["status"],json.dumps(result),now,result["setup_id"]))
        else:
            db.execute("""INSERT INTO setup_lifecycle
              (setup_id,symbol,timeframe,direction,sweep_time,poi_json,state,evidence_json,first_seen,last_seen)
              VALUES (?,?,?,?,?,?,?,?,?,?)""",(
              result["setup_id"],snapshot.symbol,timeframe,result["direction"],
              str(result["sweep_time"]),json.dumps(poi),result["status"],
              json.dumps(result),now,now))
        db.commit()
    result["persistent"]=True
    result["confirmed_for_signal"]=False
    return result


def observe_configured(snapshot,timeframe):
    path=os.getenv("NEXUS_AGENT_SETUP_DB_PATH","").strip()
    return observe(snapshot,timeframe,db_path=path or None)
