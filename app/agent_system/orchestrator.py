from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .agents.ict import assess_ict
from .agents.macro import assess_macro
from .agents.news import assess_news
from .contracts import AgentAssessment, Direction, MarketSnapshot, RiskDecision, SupervisorDecision, WorkflowState
from .journal import JournalRecord, append_jsonl
from .reverify import reverify
from .risk_gate import RiskPolicy, evaluate_risk
from .scanner import ScanDecision, scan
from .signal_engine import SignalBuildResult, SignalPlan, build_signal
from .snapshot_adapter import build_mt5_snapshot
from .supervisor import supervise


@dataclass(frozen=True)
class ShadowRunResult:
    initial_snapshot: MarketSnapshot
    scan: ScanDecision
    assessments: tuple[AgentAssessment, ...]
    supervisor: SupervisorDecision
    fresh_snapshot: MarketSnapshot | None
    final_decision: SupervisorDecision
    risk: RiskDecision | None
    signal: SignalPlan | None = None
    signal_blocks: tuple[str, ...] = ()


def _scanner_terminal(snapshot: MarketSnapshot, scan_result: ScanDecision) -> SupervisorDecision:
    state = WorkflowState.NO_TRADE if scan_result.state == WorkflowState.NO_TRADE else WorkflowState.WAIT
    explanation = "Scanner blocked deeper analysis" if state == WorkflowState.NO_TRADE else "Scanner found no objective event requiring specialist escalation"
    return SupervisorDecision(
        symbol=snapshot.symbol,
        snapshot_id=snapshot.snapshot_id,
        state=state,
        direction=Direction.NEUTRAL,
        conflicts=scan_result.blocks,
        required_confirmation=scan_result.triggers,
        explanation=explanation,
    )


def run_shadow(
    account: str,
    symbol: str,
    *,
    proposed_rr: float | None = None,
    risk_policy: RiskPolicy | None = None,
    journal_path: str | Path | None = None,
    snapshot_builder: Callable[[str, str], MarketSnapshot] = build_mt5_snapshot,
) -> ShadowRunResult:
    """Run one observation-only NEXUS decision cycle.

    No Telegram publication, AutoTrade mutation, MT5 command, or order placement
    exists in this orchestrator. It only reads snapshots and optionally journals.
    """
    initial = snapshot_builder(account, symbol)
    scan_result = scan(initial)
    assessments: tuple[AgentAssessment, ...] = ()
    fresh: MarketSnapshot | None = None
    risk: RiskDecision | None = None
    signal: SignalPlan | None = None
    signal_blocks: tuple[str, ...] = ()

    if scan_result.state != WorkflowState.WATCH:
        supervisor = _scanner_terminal(initial, scan_result)
        final = supervisor
    else:
        assessments = (assess_ict(initial), assess_macro(initial), assess_news(initial))
        supervisor = supervise(initial, assessments)
        final = supervisor
        if supervisor.state == WorkflowState.ARMED:
            fresh = snapshot_builder(account, symbol)
            final = reverify(initial, fresh, supervisor)
            if final.state == WorkflowState.SIGNAL_CANDIDATE:
                built: SignalBuildResult = build_signal(fresh, final)
                signal, signal_blocks = built.plan, built.blocks
                if signal is not None:
                    risk = evaluate_risk(fresh, final, proposed_rr=signal.rr, policy=risk_policy)

    result = ShadowRunResult(initial, scan_result, assessments, supervisor, fresh, final, risk, signal, signal_blocks)
    if journal_path is not None:
        journal_snapshot = fresh if fresh is not None else initial
        append_jsonl(
            journal_path,
            JournalRecord(snapshot=journal_snapshot, assessments=assessments, supervisor=final, risk=risk),
        )
    return result
