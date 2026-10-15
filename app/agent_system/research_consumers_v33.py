"""Opt-in research consumers of ONE shared analysis; no runtime replacements.

Bindings detect accidental mixing/revision; they are not signed attestations of
broker truth. This module cannot grant publication or execution permission.
"""
from dataclasses import asdict, dataclass, replace
import sqlite3

from .contracts import Direction
from .fast_scalp import FastScalpState
from .lifecycle_evidence_v33 import digest, FVG, Sweep, MSS, Displacement, Retest, canonical, encode_evidence
from .lifecycle_snapshot_v33 import EvidenceFrame
from .setup_lifecycle_v33 import Setup, State, TERMINAL, LifecycleStore
from .shared_detector_v33 import DetectorPolicy, SequenceResult, detect_sequence


@dataclass(frozen=True)
class ResearchAnalysis:
    setup: Setup
    frame: EvidenceFrame
    policy: DetectorPolicy
    sweep_opened_at: int
    result: SequenceResult
    integrity: str


def _integrity(setup,frame,policy,sweep_opened_at,result):
    return digest(dict(setup=asdict(setup),frame=asdict(frame),policy=asdict(policy),
                       sweep_opened_at=sweep_opened_at,result=asdict(result)))


def analyze_research(frame: EvidenceFrame, setup: Setup, *, sweep_opened_at: int,
                     policy: DetectorPolicy | None = None) -> ResearchAnalysis:
    policy=DetectorPolicy() if policy is None else policy
    result=detect_sequence(frame,setup,sweep_opened_at=sweep_opened_at,policy=policy)
    return ResearchAnalysis(setup,frame,policy,sweep_opened_at,result,
                           _integrity(setup,frame,policy,sweep_opened_at,result))


def _checked(analysis):
    if type(analysis) is not ResearchAnalysis:
        raise ValueError("shared research analysis required")
    if analysis.integrity!=_integrity(analysis.setup,analysis.frame,analysis.policy,
                                     analysis.sweep_opened_at,analysis.result):
        raise ValueError("shared analysis was revised")
    return analysis.result


@dataclass(frozen=True)
class EvidenceBinding:
    setup_id: str
    sequence_id: str
    snapshot_ref: str
    context_ref: str
    decision_at: int
    analysis_integrity: str
    events: tuple[tuple[str,str],...]


def _binding(analysis):
    result=_checked(analysis)
    return EvidenceBinding(result.setup_id,result.sequence_id,result.snapshot_ref,
        result.context_ref,result.decision_at,analysis.integrity,
        tuple((e.state.value,e.identity) for e in result.events))


def _gap(result):
    event=next((e for e in result.events if type(e.evidence) is FVG),None)
    if event is None: return None
    e=event.evidence
    return (e.left.high,e.right.low) if e.left.high<e.right.low else (e.right.high,e.left.low)


@dataclass(frozen=True)
class ResearchFastScalp:
    binding: EvidenceBinding
    strategy_id: str
    symbol: str
    timeframe: str
    direction: Direction
    state: FastScalpState
    lifecycle_state: State
    structural_retest_confirmed: bool
    poi_id: str
    poi_bounds: tuple[float,float]
    fvg_bounds: tuple[float,float] | None
    sweep_price: float | None
    blocks: tuple[str,...]
    publication_allowed: bool = False


def fast_scalp_research(analysis: ResearchAnalysis) -> ResearchFastScalp:
    result=_checked(analysis)
    if analysis.setup.timeframe!="M1":
        raise ValueError("Fast Scalp adapter requires the M1 profile")
    mapping={State.LIQUIDITY_SWEPT:FastScalpState.LIQUIDITY_SWEPT,
             State.MSS_CONFIRMED:FastScalpState.MSS_CONFIRMED,
             State.DISPLACEMENT_CONFIRMED:FastScalpState.MSS_CONFIRMED,
             State.FVG_CREATED:FastScalpState.RETEST,State.RETEST_CONFIRMED:FastScalpState.RETEST,
             State.INVALIDATED:FastScalpState.INVALIDATED,State.EXPIRED:FastScalpState.INVALIDATED}
    setup=analysis.setup
    sweep=next((e.evidence.candle for e in result.events if e.state==State.LIQUIDITY_SWEPT),None)
    return ResearchFastScalp(_binding(analysis),setup.strategy,setup.symbol,setup.timeframe,
        Direction(setup.direction),mapping.get(result.status,FastScalpState.SEARCHING),result.status,
        result.status==State.RETEST_CONFIRMED,setup.poi_id,(setup.poi_low,setup.poi_high),_gap(result),
        (sweep.low if setup.direction=="LONG" else sweep.high) if sweep else None,
        (*result.blocks,"research_only_no_entry_authority"))


@dataclass(frozen=True)
class ResearchTracker:
    binding: EvidenceBinding
    symbol: str
    timeframe: str
    direction: Direction
    lifecycle_state: State
    poi_id: str
    poi_bounds: tuple[float,float]
    candle_evidence: tuple[tuple[str,tuple[str,...]],...]
    event_times: tuple[tuple[str,int],...]
    fvg_bounds: tuple[float,float] | None
    confirmed_for_signal: bool = False


def tracker_research(analysis: ResearchAnalysis) -> ResearchTracker:
    result=_checked(analysis)
    source=[]; times=[]
    for event in result.events:
        e=event.evidence
        if type(e) is FVG:
            candles=(e.left,e.middle,e.right)
        elif type(e) is Sweep:
            candles=(e.candle,e.liquidity)
        elif type(e) is MSS:
            candles=(e.candle,e.swing,e.swing_confirmation)
        elif type(e) is Displacement:
            candles=(e.candle,*e.baseline)
        else:
            candles=(e.candle,)
        source.append((event.state.value,tuple(c.identity for c in candles)))
        times.append((event.state.value,e.right.closed_at if type(e) is FVG else e.candle.closed_at))
    setup=analysis.setup
    return ResearchTracker(_binding(analysis),setup.symbol,setup.timeframe,Direction(setup.direction),
        result.status,setup.poi_id,(setup.poi_low,setup.poi_high),tuple(source),tuple(times),_gap(result))


@dataclass(frozen=True)
class ResearchCandidate:
    """Evidence-only candidate. Deliberately contains no fabricated entry/SL/TP."""
    binding: EvidenceBinding
    symbol: str
    strategy_id: str
    timeframe: str
    direction: Direction
    poi_id: str
    poi_bounds: tuple[float,float]
    fvg_bounds: tuple[float,float]
    source_candles: tuple[tuple[str,tuple[str,...]],...]


def research_candidate(analysis: ResearchAnalysis) -> ResearchCandidate:
    result=_checked(analysis)
    if result.status!=State.RETEST_CONFIRMED:
        raise ValueError("complete shared structural sequence required")
    view=tracker_research(analysis)
    if view.fvg_bounds is None:
        raise ValueError("exact bound FVG required")
    return ResearchCandidate(view.binding,view.symbol,analysis.setup.strategy,view.timeframe,
        view.direction,view.poi_id,view.poi_bounds,view.fvg_bounds,view.candle_evidence)


@dataclass(frozen=True)
class ResearchICTGate:
    binding: EvidenceBinding
    structure_allowed: bool
    checks: tuple[str,...]
    structure_blocks: tuple[str,...]
    publication_blocks: tuple[str,...] = ("research_only_no_publication", "independent_entry_risk_and_publication_gates_required")
    allowed: bool = False
    persistent_event_ids: tuple[str,...] = ()


def full_ict_research(analysis: ResearchAnalysis, candidate: ResearchCandidate | None) -> ResearchICTGate:
    result=_checked(analysis)
    blocks=[]
    checks=[]
    if result.status in TERMINAL:
        blocks.append("terminal_setup")
    if result.status!=State.RETEST_CONFIRMED:
        blocks.append("shared_sequence_incomplete")
    if analysis.setup.poi_qualified is not True:
        blocks.append("poi_not_qualified")
    if type(candidate) is not ResearchCandidate:
        blocks.append("evidence_candidate_missing")
    elif candidate.binding!=_binding(analysis):
        blocks.append("candidate_setup_sequence_snapshot_context_or_evidence_mismatch")
    elif result.status==State.RETEST_CONFIRMED and candidate!=research_candidate(analysis):
        blocks.append("candidate_geometry_direction_or_source_candles_mismatch")
    if not blocks:
        checks.extend(("same_setup","same_sequence","same_snapshot","same_context",
                       "same_candles","same_fvg","closed_structural_retest","qualified_poi"))
    return ResearchICTGate(_binding(analysis),not blocks,tuple(checks),tuple(blocks))


def persisted_full_ict_research(store: LifecycleStore, analysis: ResearchAnalysis,
                               candidate: ResearchCandidate | None) -> ResearchICTGate:
    """Read-only comparison to exact persisted core events and current state.

    Publication would still require an atomic independent reservation recheck;
    this research read is not a lock or an authorization to send.
    """
    gate=full_ict_research(analysis,candidate)
    if not gate.structure_allowed:
        return gate

    def reject(reason):
        return replace(gate,structure_allowed=False,structure_blocks=(*gate.structure_blocks,reason))

    if not isinstance(store,LifecycleStore):
        return reject("isolated_persistent_store_required")
    try:
        saved,history=store.recover(analysis.setup.setup_id)
    except (KeyError,sqlite3.Error):
        return reject("persistent_lifecycle_unavailable")
    if saved!=analysis.setup or not history:
        return reject("persistent_setup_mismatch")
    if history[-1]["state"]!=State.RETEST_CONFIRMED.value:
        return reject("persistent_current_state_not_confirmed")
    if not history[-1]["at"]<=analysis.frame.decision_at<saved.expires_at:
        return reject("persistent_decision_clock_or_expiry_mismatch")
    expected=analysis.result.events
    states={e.state.value for e in expected}
    recorded=[e for e in history if e["state"] in states]
    if len(recorded)!=len(expected):
        return reject("persistent_event_prefix_mismatch")
    actual={}
    ids=[]
    for event,old in zip(expected,recorded):
        ev=event.evidence
        if type(ev) is MSS: ev=replace(ev,sweep_event=actual[ev.sweep_event])
        elif type(ev) is Displacement: ev=replace(ev,mss_event=actual[ev.mss_event])
        elif type(ev) is FVG: ev=replace(ev,displacement_event=actual[ev.displacement_event])
        elif type(ev) is Retest: ev=replace(ev,fvg_event=actual[ev.fvg_event])
        if (old["event_key"]!="shared:"+event.identity or old["state"]!=event.state.value
            or old["payload"]!=canonical(encode_evidence(ev))):
            return reject("persistent_event_identity_or_evidence_mismatch")
        actual[event.identity]=old["event_id"]
        ids.append(old["event_id"])
    return replace(gate,checks=(*gate.checks,"persistent_current_state","persistent_exact_events"),
                   persistent_event_ids=tuple(ids))
