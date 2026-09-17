from __future__ import annotations

from .agents.ict import assess_ict
from .contracts import Direction, MarketSnapshot, SupervisorDecision, WorkflowState


def reverify(previous: MarketSnapshot, fresh: MarketSnapshot, decision: SupervisorDecision) -> SupervisorDecision:
    """Promote an ARMED setup only when fresh ICT evidence still confirms it."""
    if decision.state != WorkflowState.ARMED:
        return decision

    if previous.symbol != fresh.symbol:
        return SupervisorDecision(
            symbol=fresh.symbol,
            snapshot_id=fresh.snapshot_id,
            state=WorkflowState.CANCELLED,
            direction=Direction.NEUTRAL,
            conflicts=("symbol changed during re-verification",),
            explanation="Armed setup cancelled because fresh snapshot does not match the original symbol",
        )

    if fresh.data_freshness_ms > 30_000 or fresh.bid is None or fresh.ask is None or fresh.missing_data:
        reasons = []
        if fresh.data_freshness_ms > 30_000:
            reasons.append("stale_market_data")
        if fresh.bid is None or fresh.ask is None:
            reasons.append("missing_quote")
        reasons.extend(f"missing:{x}" for x in fresh.missing_data)
        return SupervisorDecision(
            symbol=fresh.symbol,
            snapshot_id=fresh.snapshot_id,
            state=WorkflowState.CANCELLED,
            direction=Direction.NEUTRAL,
            conflicts=tuple(dict.fromkeys(reasons)) or ("fresh snapshot invalid",),
            explanation="Armed setup cancelled during mandatory fresh-data re-verification",
        )

    fresh_ict = assess_ict(fresh)
    if fresh_ict.missing_data:
        return SupervisorDecision(
            symbol=fresh.symbol,
            snapshot_id=fresh.snapshot_id,
            state=WorkflowState.WAIT,
            direction=Direction.NEUTRAL,
            required_confirmation=tuple(f"nexus-ict-v1:{x}" for x in fresh_ict.missing_data),
            explanation="Fresh ICT assessment is incomplete; setup cannot be promoted",
        )

    if fresh_ict.direction not in {Direction.LONG, Direction.SHORT}:
        return SupervisorDecision(
            symbol=fresh.symbol,
            snapshot_id=fresh.snapshot_id,
            state=WorkflowState.WAIT,
            direction=Direction.NEUTRAL,
            required_confirmation=("fresh ICT HTF/LTF alignment",),
            explanation="Fresh 5M/HTF evidence no longer confirms a directional setup",
        )

    if fresh_ict.direction != decision.direction:
        return SupervisorDecision(
            symbol=fresh.symbol,
            snapshot_id=fresh.snapshot_id,
            state=WorkflowState.WAIT,
            direction=Direction.NEUTRAL,
            conflicts=("fresh ICT direction conflicts with armed direction",),
            required_confirmation=("new specialist analysis cycle",),
            explanation="Armed direction changed during fresh ICT re-verification",
        )

    return SupervisorDecision(
        symbol=fresh.symbol,
        snapshot_id=fresh.snapshot_id,
        state=WorkflowState.SIGNAL_CANDIDATE,
        direction=decision.direction,
        agreement=tuple(dict.fromkeys((*decision.agreement, fresh_ict.agent_id))),
        explanation="Fresh ICT snapshot confirms the armed direction; deterministic RiskGate remains mandatory",
    )
