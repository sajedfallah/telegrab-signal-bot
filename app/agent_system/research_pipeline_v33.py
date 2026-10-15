"""Snapshot -> shared evidence -> isolated lifecycle -> persisted research gate.

No application entry point imports this opt-in pipeline. It never publishes,
reserves delivery or executes. Bad input fails closed before setup advancement.
"""
from dataclasses import dataclass
from pathlib import Path
from math import isfinite
import sqlite3

from .contracts import MarketSnapshot
from .lifecycle_evidence_v33 import Observation, canonical, encode_evidence
from .lifecycle_snapshot_v33 import evidence_frame
from .setup_lifecycle_v33 import LifecycleStore, Setup, State, TERMINAL
from .shared_detector_v33 import DetectorPolicy, apply_research_sequence
from .research_consumers_v33 import (
    ResearchAnalysis, ResearchCandidate, ResearchICTGate, analyze_research,
    full_ict_research, persisted_full_ict_research, research_candidate,
)


LOCATION_STAGES=(State.POI_SELECTED,State.APPROACHING_POI,State.POI_TOUCHED)


@dataclass(frozen=True)
class LocationProof:
    selected_candle_id: str
    approaching_candle_id: str
    touched_candle_id: str
    max_approach_distance: float


@dataclass(frozen=True)
class PipelineResult:
    status: str
    setup_id: str
    snapshot_ref: str
    lifecycle_state: State | None
    analysis: ResearchAnalysis | None
    candidate: ResearchCandidate | None
    gate: ResearchICTGate | None
    new_event_ids: tuple[str,...]
    blocks: tuple[str,...]
    publication_allowed: bool = False


def _location_evidence(proof,frame,setup,sweep_opened_at):
    if type(proof) is not LocationProof or type(proof.max_approach_distance) not in (int,float):
        raise ValueError("explicit immutable location proof required")
    if not isfinite(proof.max_approach_distance) or proof.max_approach_distance<=0:
        raise ValueError("finite positive approach-distance policy required")
    by_id={c.identity:c for c in frame.candles}
    candles=tuple(by_id[key] for key in (proof.selected_candle_id,proof.approaching_candle_id,proof.touched_candle_id))
    selected,approaching,touched=candles
    if not (setup.created_at<=selected.closed_at<=approaching.opened_at
            and approaching.closed_at<=touched.opened_at and touched.closed_at<=sweep_opened_at):
        raise ValueError("location proof is not available before sweep")
    if selected.closed_at<setup.poi_eligible_at:
        raise ValueError("selection predates POI eligibility")
    distance=max(setup.poi_low-approaching.close,approaching.close-setup.poi_high,0.)
    if not 0<distance<=proof.max_approach_distance:
        raise ValueError("approach outside explicit distance policy")
    if touched.low>setup.poi_high or touched.high<setup.poi_low:
        raise ValueError("POI touch not established")
    return tuple((state,Observation(c,"validated_location:"+state.value))
                 for state,c in zip(LOCATION_STAGES,candles))


def run_research_snapshot(snapshot: MarketSnapshot, setup: Setup, *, db_path,
                          sweep_opened_at: int, context_ref: str, location: LocationProof | None = None,
                          policy: DetectorPolicy | None = None,
                          candidate: ResearchCandidate | None = None) -> PipelineResult:
    """Advance only evidenced research states and verify against persisted state.

    Location evidence is mandatory for a new identity or incomplete location
    prefix. Existing valid core evidence resumes without inventing location.
    Writes are atomic PER EVENT, not an all-or-nothing snapshot transaction.
    """
    analysis=None; gate=None
    snapshot_ref=snapshot.snapshot_id
    setup_id=setup.setup_id
    stage="snapshot_validation"
    current=None
    before_ids=set()

    def result(status,blocks=(),new_ids=(),selected_candidate=None):
        return PipelineResult(status,setup_id,snapshot_ref,current,analysis,selected_candidate,
                              gate,tuple(new_ids),tuple(blocks))

    try:
        frame=evidence_frame(snapshot,setup.timeframe,context_ref=context_ref)
        analysis=analyze_research(frame,setup,sweep_opened_at=sweep_opened_at,policy=policy)
        structural=analysis.result
        if structural.status==State.POI_TOUCHED and structural.blocks:
            return result("BLOCKED",structural.blocks)
        stage="candidate_validation"
        if candidate is not None and structural.status not in {State.INVALIDATED,State.EXPIRED}:
            gate=full_ict_research(analysis,candidate)
            if not gate.structure_allowed:
                return result("BLOCKED",gate.structure_blocks)
        stage="location_validation"
        location_events=_location_evidence(location,frame,setup,sweep_opened_at) if location is not None else ()
        stage="persistent_store"
        path=Path(db_path).resolve()
        if not path.is_file() and (not location_events or structural.status==State.EXPIRED):
            return result("BLOCKED",("existing_setup_or_pre_sweep_location_required",))
        store=LifecycleStore(path)
        try:
            saved,history=store.recover(setup_id)
            if saved!=setup:
                return result("BLOCKED",("persistent_setup_mismatch",))
            before_ids={e["event_id"] for e in history}
        except KeyError:
            if not location_events or structural.status==State.EXPIRED:
                return result("BLOCKED",("existing_setup_or_pre_sweep_location_required",))
            store.create(setup,snapshot_ref=snapshot_ref,observed_at=frame.decision_at)
            _,history=store.recover(setup_id)
        current=State(history[-1]["state"])
        stage="persistent_clock"
        if frame.decision_at<history[-1]["at"]:
            return result("BLOCKED",("retroactive_snapshot_decision",))
        if current in TERMINAL:
            return result("TERMINAL",("persistent_terminal_setup",))
        stage="location_persistence"
        if current in (State.DISCOVERED,*LOCATION_STAGES[:-1]) and not location_events and structural.status!=State.EXPIRED:
            return result("BLOCKED",("pre_sweep_location_proof_required",))
        if structural.status!=State.EXPIRED:
            recorded={e["state"]:e for e in history if e["state"] in {s.value for s in LOCATION_STAGES}}
            for state,ev in location_events:
                key="pipeline_location:"+state.value+":"+ev.candle.identity
                if state.value in recorded:
                    old=recorded[state.value]
                    if old["event_key"]!=key or old["payload"]!=canonical(encode_evidence(ev)):
                        return result("BLOCKED",("persistent_location_evidence_changed",))
                else:
                    store.advance(setup_id,state,ev,event_key=key,at=frame.decision_at,
                                  snapshot_ref=snapshot_ref,feed_fresh=True)
        stage="structural_persistence"
        apply_research_sequence(store,setup,structural)
        _,history=store.recover(setup_id)
        current=State(history[-1]["state"])
        new_ids=tuple(e["event_id"] for e in history if e["event_id"] not in before_ids)
        if current in TERMINAL:
            return result("TERMINAL",("persistent_terminal_setup",),new_ids)
        stage="persistent_candidate_gate"
        selected=candidate
        if selected is None and structural.status==State.RETEST_CONFIRMED:
            selected=research_candidate(analysis)
        gate=persisted_full_ict_research(store,analysis,selected)
        if gate.structure_allowed:
            return result("STRUCTURE_VERIFIED",(),new_ids,selected)
        status="WATCH" if structural.status!=State.RETEST_CONFIRMED else "BLOCKED"
        return result(status,tuple(dict.fromkeys((*structural.blocks,*gate.structure_blocks))),new_ids,selected)
    except (ValueError,KeyError,TypeError,OSError,sqlite3.Error):
        # Fail closed without leaking paths/credentials or claiming rollback of
        # earlier valid per-event commits. Retrying resumes the recorded prefix.
        return result("BLOCKED",("failed:"+stage,))
