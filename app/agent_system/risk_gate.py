from __future__ import annotations

from dataclasses import dataclass

from .contracts import MarketSnapshot, RiskDecision, SupervisorDecision, WorkflowState


@dataclass(frozen=True)
class RiskPolicy:
    """Explicit pre-signal policy. V1 never invents production thresholds."""

    version: str = "agent-pre-signal-v1"
    max_freshness_ms: int = 30_000
    min_rr: float | None = None


def evaluate_risk(
    snapshot: MarketSnapshot,
    decision: SupervisorDecision,
    *,
    proposed_rr: float | None = None,
    policy: RiskPolicy | None = None,
) -> RiskDecision:
    policy = policy or RiskPolicy()
    blocks: list[str] = []
    warnings: list[str] = []

    if decision.state != WorkflowState.SIGNAL_CANDIDATE:
        blocks.append("not_signal_candidate")
    if snapshot.data_freshness_ms > policy.max_freshness_ms:
        blocks.append("stale_market_data")
    if snapshot.bid is None or snapshot.ask is None:
        blocks.append("missing_quote")
    elif snapshot.ask < snapshot.bid:
        blocks.append("invalid_spread")
    if snapshot.missing_data:
        blocks.extend(f"missing:{x}" for x in snapshot.missing_data)

    high_impact = [
        e
        for e in snapshot.scheduled_events
        if str(e.get("impact") or "").upper() in {"HIGH", "CRITICAL"}
        and bool(e.get("active_window", False))
    ]
    if high_impact:
        blocks.append("high_impact_news_window")

    if proposed_rr is None:
        blocks.append("rr_not_verified")
    elif policy.min_rr is None:
        # RR is known, but V1 has no validated production threshold to compare
        # against. Fail closed rather than silently inventing one.
        blocks.append("risk_policy_missing:min_rr")
    elif proposed_rr < policy.min_rr:
        blocks.append("rr_below_policy")

    if snapshot.session == "OFF_PEAK":
        warnings.append("off_peak_session")

    return RiskDecision(
        allowed=not blocks,
        hard_blocks=tuple(dict.fromkeys(blocks)),
        warnings=tuple(warnings),
        rr=proposed_rr,
        risk_policy_version=policy.version,
    )
