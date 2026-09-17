from __future__ import annotations

from .contracts import AgentAssessment, Direction, MarketSnapshot, SupervisorDecision, WorkflowState


def supervise(snapshot: MarketSnapshot, assessments: tuple[AgentAssessment, ...]) -> SupervisorDecision:
    """Combine independent assessments without arbitrary numeric weights."""
    if not assessments:
        return SupervisorDecision(symbol=snapshot.symbol, snapshot_id=snapshot.snapshot_id, state=WorkflowState.NO_TRADE, direction=Direction.NEUTRAL, explanation="No specialist assessments available")
    bad = [a.agent_id for a in assessments if a.snapshot_id != snapshot.snapshot_id or a.symbol != snapshot.symbol]
    if bad:
        return SupervisorDecision(symbol=snapshot.symbol, snapshot_id=snapshot.snapshot_id, state=WorkflowState.NO_TRADE, direction=Direction.NEUTRAL, conflicts=tuple(f"snapshot mismatch: {x}" for x in bad), explanation="Specialists must evaluate the same immutable snapshot")
    ict = next((a for a in assessments if a.agent_id.startswith("nexus-ict")), None)
    if ict is None or ict.direction == Direction.NEUTRAL:
        return SupervisorDecision(symbol=snapshot.symbol, snapshot_id=snapshot.snapshot_id, state=WorkflowState.WAIT, direction=Direction.NEUTRAL, required_confirmation=("valid ICT HTF/LTF alignment",), explanation="ICT has not produced a directional setup")
    opposing = [a.agent_id for a in assessments if a.direction not in {Direction.NEUTRAL, ict.direction}]
    missing = [f"{a.agent_id}:{x}" for a in assessments for x in a.missing_data]
    if opposing:
        return SupervisorDecision(symbol=snapshot.symbol, snapshot_id=snapshot.snapshot_id, state=WorkflowState.WAIT, direction=Direction.NEUTRAL, conflicts=tuple(f"{x} opposes ICT" for x in opposing), explanation="Specialist conflict requires fresh re-verification")
    if missing:
        return SupervisorDecision(symbol=snapshot.symbol, snapshot_id=snapshot.snapshot_id, state=WorkflowState.ARMED, direction=ict.direction, agreement=tuple(a.agent_id for a in assessments if a.direction == ict.direction), required_confirmation=tuple(missing), explanation="Technical setup exists but contextual evidence is incomplete")
    return SupervisorDecision(symbol=snapshot.symbol, snapshot_id=snapshot.snapshot_id, state=WorkflowState.SIGNAL_CANDIDATE, direction=ict.direction, agreement=tuple(a.agent_id for a in assessments if a.direction == ict.direction), explanation="ICT direction has no specialist conflict and required structured context is present; candidate still requires RiskGate")
