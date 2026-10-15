"""Shared, opt-in structural detector. No bias, POI qualification or publication.

Each invocation is anchored to one explicit sweep open time. Confirmed pivots use
strict comparisons and are frozen using only bars available BEFORE that sweep.
"""
from dataclasses import dataclass, asdict, replace
import json
from math import isfinite

from .lifecycle_evidence_v33 import (
    Candle, Sweep, MSS, Displacement, FVG, Retest, Decision,
    SECONDS, digest, encode_evidence, canonical,
)
from .lifecycle_snapshot_v33 import EvidenceFrame
from .setup_lifecycle_v33 import Setup, State, TERMINAL


@dataclass(frozen=True)
class DetectorPolicy:
    liquidity_window: int = 12
    swing_width: int = 2
    displacement_baseline: int = 12
    max_bar_age: int = 2

    def __post_init__(self):
        for name in ("liquidity_window","swing_width","displacement_baseline","max_bar_age"):
            if type(getattr(self,name)) is not int or getattr(self,name)<1:
                raise ValueError("positive integer detector policy required")
        if self.displacement_baseline<3:
            raise ValueError("at least three baseline candles required")


@dataclass(frozen=True)
class DetectedEvent:
    identity: str
    state: State
    evidence: Sweep | MSS | Displacement | FVG | Retest


@dataclass(frozen=True)
class SequenceResult:
    setup_id: str
    sequence_id: str
    snapshot_ref: str
    context_ref: str
    decision_at: int
    events: tuple[DetectedEvent,...]
    status: State
    blocks: tuple[str,...]
    invalidating_candle: Candle | None = None


def _validate(frame,setup):
    if type(frame) is not EvidenceFrame or type(setup) is not Setup:
        raise ValueError("validated evidence frame and immutable setup required")
    if (frame.symbol,frame.timeframe,frame.context_ref)!=(setup.symbol,setup.timeframe,setup.context_ref):
        raise ValueError("setup/snapshot context mismatch")
    if not frame.snapshot_ref or type(frame.decision_at) is not int or frame.decision_at<setup.created_at:
        raise ValueError("invalid decision reference/time")
    if not all(type(v) in (int,float) and isfinite(v) and v>0 for v in (frame.bid,frame.ask)) or frame.ask<frame.bid:
        raise ValueError("invalid executable quote")
    if type(frame.candles) is not tuple or not frame.candles:
        raise ValueError("immutable closed candle series required")
    prior=None
    for c in frame.candles:
        if type(c) is not Candle or (c.symbol,c.timeframe,c.source)!=(setup.symbol,setup.timeframe,setup.poi_origin.source):
            raise ValueError("candle provenance mismatch")
        if c.closed_at>frame.decision_at or prior is not None and prior.closed_at!=c.opened_at:
            raise ValueError("unclosed, overlapping or missing candle")
        prior=c


def detect_sequence(frame: EvidenceFrame, setup: Setup, *, sweep_opened_at: int,
                    policy: DetectorPolicy | None = None) -> SequenceResult:
    policy=policy or DetectorPolicy()
    if type(policy) is not DetectorPolicy or type(sweep_opened_at) is not int:
        raise ValueError("explicit sweep anchor and policy required")
    _validate(frame,setup)
    bars=frame.candles
    anchor=digest(dict(setup=setup.setup_id,sweep_opened_at=sweep_opened_at,policy=asdict(policy)))
    events=[]

    def finish(status,reason=None,invalidating=None):
        return SequenceResult(setup.setup_id,anchor,frame.snapshot_ref,frame.context_ref,
            frame.decision_at,tuple(events),status,(reason,) if reason else (),invalidating)

    def emit(state,evidence):
        event_id=digest(dict(sequence=anchor,state=state.value,evidence=encode_evidence(evidence)))
        event=DetectedEvent(event_id,state,evidence)
        events.append(event)
        return event_id

    if frame.decision_at>=setup.expires_at:
        return finish(State.EXPIRED,"absolute_setup_deadline")
    if frame.decision_at-bars[-1].closed_at>policy.max_bar_age*SECONDS[setup.timeframe]:
        return finish(State.POI_TOUCHED,"closed_series_stale")
    sweep_i=next((i for i,c in enumerate(bars) if c.opened_at==sweep_opened_at),None)
    if sweep_i is None or sweep_i<policy.liquidity_window:
        return finish(State.POI_TOUCHED,"sweep_anchor_or_history_unavailable")
    sweep=bars[sweep_i]
    if sweep.opened_at<setup.poi_eligible_at or sweep.closed_at<setup.created_at:
        return finish(State.POI_TOUCHED,"sweep_predates_setup_or_poi")
    long=setup.direction=="LONG"
    prior=bars[sweep_i-policy.liquidity_window:sweep_i]
    liquidity=(min(prior,key=lambda c:(c.low,-c.opened_at)) if long
               else max(prior,key=lambda c:(c.high,c.opened_at)))
    level=liquidity.low if long else liquidity.high
    reclaimed=(sweep.low<level<sweep.close if long else sweep.high>level>sweep.close)
    if not reclaimed or sweep.low>setup.poi_high or sweep.high<setup.poi_low:
        return finish(State.POI_TOUCHED,"bound_poi_sweep_reclaim_unverified")
    sweep_id=emit(State.LIQUIDITY_SWEPT,Sweep(sweep,liquidity))
    # Observe every later close, including inactivity between structural events.
    invalid=next((c for c in bars[sweep_i:] if
        (c.close<=setup.invalidation_price if long else c.close>=setup.invalidation_price)),None)
    if invalid:
        return finish(State.INVALIDATED,"structural_close_invalidation",invalid)
    width=policy.swing_width
    pivots=[]
    for i in range(width,sweep_i-width):
        c=bars[i]
        neighbors=(*bars[i-width:i],*bars[i+1:i+width+1])
        confirmed=bars[i+width]
        is_pivot=(all(c.high>x.high for x in neighbors) if long else all(c.low<x.low for x in neighbors))
        already_broken=any((b.close>c.high if long else b.close<c.low)
                           for b in bars[i+width+1:sweep_i+1])
        if is_pivot and not already_broken and confirmed.closed_at<=sweep.opened_at:
            pivots.append((c,confirmed))
    if not pivots:
        return finish(State.LIQUIDITY_SWEPT,"confirmed_pre_sweep_swing_unavailable")
    swing,confirmation=pivots[-1]
    mss_i=next((i for i in range(sweep_i+1,len(bars)) if
        (bars[i].close>swing.high if long else bars[i].close<swing.low)),None)
    if mss_i is None:
        return finish(State.LIQUIDITY_SWEPT,"waiting_for_later_swing_break_close")
    mss_id=emit(State.MSS_CONFIRMED,MSS(bars[mss_i],swing,confirmation,sweep_id))
    displacement_i=None
    start=mss_i if setup.allow_same_candle_displacement else mss_i+1
    for i in range(start,len(bars)):
        base=bars[max(0,i-policy.displacement_baseline):i]
        if len(base)<policy.displacement_baseline:
            continue
        typical=sum(abs(c.close-c.open) for c in base)/len(base)
        c=bars[i]
        if typical>0 and abs(c.close-c.open)>=typical*setup.displacement_body_ratio and (c.close>c.open if long else c.close<c.open):
            displacement_i=i
            break
    if displacement_i is None:
        return finish(State.MSS_CONFIRMED,"waiting_for_measured_directional_displacement")
    baseline=bars[displacement_i-policy.displacement_baseline:displacement_i]
    disp_id=emit(State.DISPLACEMENT_CONFIRMED,Displacement(bars[displacement_i],baseline,mss_id))
    gap_i=None
    for i in range(displacement_i,len(bars)-2):
        left,middle,right=bars[i:i+3]
        directional=(middle.close>middle.open if long else middle.close<middle.open)
        if directional and (left.high<right.low if long else right.high<left.low):
            gap_i=i
            break
    if gap_i is None:
        return finish(State.DISPLACEMENT_CONFIRMED,"waiting_for_post_displacement_fvg")
    left,middle,right=bars[gap_i:gap_i+3]
    fvg_id=emit(State.FVG_CREATED,FVG(left,middle,right,disp_id))
    low,high=(left.high,right.low) if long else (right.high,left.low)
    retest=next((c for c in bars[gap_i+3:] if c.low<=high and c.high>=low),None)
    if retest is None:
        return finish(State.FVG_CREATED,"waiting_for_later_closed_retest")
    emit(State.RETEST_CONFIRMED,Retest(retest,fvg_id))
    return finish(State.RETEST_CONFIRMED,"independent_poi_mtf_entry_and_risk_gates_required")


def apply_research_sequence(store,setup: Setup,result: SequenceResult):
    """Persist core evidence only after caller-established POI_TOUCHED.

    Progress is committed per validated event. Retries resume a matching prefix;
    conflicting anchors/policies/evidence reject instead of merging sequences.
    This function never advances ENTRY_READY or reserves/sends a publication.
    """
    saved,history=store.recover(result.setup_id)
    if saved!=setup or result.setup_id!=setup.setup_id or result.context_ref!=setup.context_ref:
        raise ValueError("persistent setup/context mismatch")
    current=State(history[-1]["state"])
    if current in TERMINAL:
        return ()
    if result.status==State.EXPIRED:
        return (store.advance(setup.setup_id,State.EXPIRED,Decision("absolute_setup_deadline"),
            event_key="shared-expiry",at=result.decision_at,snapshot_ref=result.snapshot_ref,feed_fresh=False),)
    core={State.LIQUIDITY_SWEPT,State.MSS_CONFIRMED,State.DISPLACEMENT_CONFIRMED,State.FVG_CREATED,State.RETEST_CONFIRMED}
    previous=[e for e in history if State(e["state"]) in core]
    if not previous and current!=State.POI_TOUCHED:
        raise ValueError("caller must establish location stages before shared evidence")
    if previous and result.events and previous[0]["event_key"]!="shared:"+result.events[0].identity:
        raise ValueError("different persistent sweep/policy anchor")
    if result.status==State.INVALIDATED:
        if result.invalidating_candle is None:
            raise ValueError("exact invalidating candle required")
        store.monitor(setup.setup_id,result.invalidating_candle,at=result.decision_at,
                      snapshot_ref=result.snapshot_ref,feed_fresh=True)
        return ()
    if len(previous)>len(result.events):
        raise ValueError("recorded evidence prefix unavailable; do not reconstruct")
    actual={}
    appended=[]
    for index,event in enumerate(result.events):
        ev=event.evidence
        if type(ev) is MSS: ev=replace(ev,sweep_event=actual[ev.sweep_event])
        elif type(ev) is Displacement: ev=replace(ev,mss_event=actual[ev.mss_event])
        elif type(ev) is FVG: ev=replace(ev,displacement_event=actual[ev.displacement_event])
        elif type(ev) is Retest: ev=replace(ev,fvg_event=actual[ev.fvg_event])
        if index<len(previous):
            old=previous[index]
            if old["event_key"]!="shared:"+event.identity or old["state"]!=event.state.value or old["payload"]!=canonical(encode_evidence(ev)):
                raise ValueError("persistent sequence evidence differs")
            actual[event.identity]=old["event_id"]
        else:
            actual[event.identity]=store.advance(setup.setup_id,event.state,ev,
                event_key="shared:"+event.identity,at=result.decision_at,
                snapshot_ref=result.snapshot_ref,feed_fresh=True)
            appended.append(actual[event.identity])
    return tuple(appended)
