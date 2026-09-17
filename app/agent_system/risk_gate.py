from __future__ import annotations

from .contracts import MarketSnapshot, RiskDecision, SupervisorDecision, WorkflowState


def evaluate_risk(snapshot: MarketSnapshot, decision: SupervisorDecision, *, min_rr: float = 1.5, proposed_rr: float | None = None) -> RiskDecision:
    blocks=[]; warnings=[]
    if decision.state != WorkflowState.SIGNAL_CANDIDATE: blocks.append("not_signal_candidate")
    if snapshot.data_freshness_ms > 30_000: blocks.append("stale_market_data")
    if snapshot.bid is None or snapshot.ask is None: blocks.append("missing_quote")
    elif snapshot.ask < snapshot.bid: blocks.append("invalid_spread")
    if snapshot.missing_data: blocks.extend(f"missing:{x}" for x in snapshot.missing_data)
    high_impact=[e for e in snapshot.scheduled_events if str(e.get("impact") or "").upper() in {"HIGH","CRITICAL"} and bool(e.get("active_window",False))]
    if high_impact: blocks.append("high_impact_news_window")
    if proposed_rr is None: blocks.append("rr_not_verified")
    elif proposed_rr < min_rr: blocks.append("rr_below_policy")
    if snapshot.session == "OFF_PEAK": warnings.append("off_peak_session")
    return RiskDecision(allowed=not blocks,hard_blocks=tuple(dict.fromkeys(blocks)),warnings=tuple(warnings),rr=proposed_rr,risk_policy_version="agent-pre-signal-v1")
