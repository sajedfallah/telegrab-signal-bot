from __future__ import annotations

from .contracts import Direction, MarketSnapshot, SupervisorDecision, WorkflowState


def reverify(previous: MarketSnapshot, fresh: MarketSnapshot, decision: SupervisorDecision) -> SupervisorDecision:
    if decision.state != WorkflowState.SIGNAL_CANDIDATE:
        return decision
    if previous.symbol != fresh.symbol or fresh.data_freshness_ms > 30_000 or fresh.bid is None or fresh.ask is None:
        return SupervisorDecision(symbol=fresh.symbol,snapshot_id=fresh.snapshot_id,state=WorkflowState.CANCELLED,direction=Direction.NEUTRAL,conflicts=("fresh snapshot invalid or stale",),explanation="Candidate cancelled during mandatory fresh-data re-verification")
    old=(float(previous.bid)+float(previous.ask))/2 if previous.bid and previous.ask else float(previous.last or 0)
    new=(float(fresh.bid)+float(fresh.ask))/2
    if old<=0:
        return SupervisorDecision(symbol=fresh.symbol,snapshot_id=fresh.snapshot_id,state=WorkflowState.CANCELLED,direction=Direction.NEUTRAL,conflicts=("previous reference price unavailable",),explanation="Candidate cannot be re-verified")
    move=abs(new-old)/old
    if move>0.003:
        return SupervisorDecision(symbol=fresh.symbol,snapshot_id=fresh.snapshot_id,state=WorkflowState.WAIT,direction=Direction.NEUTRAL,required_confirmation=("rerun specialist assessments on materially changed price",),explanation="Market moved materially since candidate snapshot")
    return SupervisorDecision(symbol=fresh.symbol,snapshot_id=fresh.snapshot_id,state=WorkflowState.SIGNAL_CANDIDATE,direction=decision.direction,agreement=decision.agreement,conflicts=decision.conflicts,required_confirmation=decision.required_confirmation,explanation="Fresh snapshot re-verification passed; RiskGate remains mandatory")
