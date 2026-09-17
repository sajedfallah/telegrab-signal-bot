from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.agent_system import (
    Direction,
    InvalidTransition,
    MarketSnapshot,
    RiskDecision,
    SupervisorDecision,
    WorkflowState,
    require_transition,
)


def _snapshot(**overrides):
    data = {
        "snapshot_id": "snap-20260917-0001",
        "symbol": "XAUUSD",
        "as_of": datetime(2026, 9, 17, 8, 0, tzinfo=timezone.utc),
        "source": "MT5_MARKET_FEED",
        "timeframes": {"H1": (), "M15": (), "M5": ()},
        "bid": 3650.10,
        "ask": 3650.30,
        "last": None,
        "session": "LONDON",
        "data_freshness_ms": 900,
    }
    data.update(overrides)
    return MarketSnapshot(**data)


def test_snapshot_is_immutable_and_quote_consistent():
    snapshot = _snapshot()
    assert snapshot.symbol == "XAUUSD"
    with pytest.raises(ValidationError):
        snapshot.bid = 1.0
    with pytest.raises(ValidationError):
        _snapshot(bid=10.0, ask=9.0)


def test_missing_quote_must_be_explicit():
    with pytest.raises(ValidationError):
        _snapshot(bid=None, ask=None, last=None)
    snapshot = _snapshot(bid=None, ask=None, last=None, missing_data=("quote",))
    assert "quote" in snapshot.missing_data


def test_signal_candidate_requires_trade_direction():
    with pytest.raises(ValidationError):
        SupervisorDecision(
            symbol="US30",
            snapshot_id="snap-20260917-0002",
            state=WorkflowState.SIGNAL_CANDIDATE,
            direction=Direction.NEUTRAL,
            explanation="not enough directional evidence",
        )


def test_blocked_risk_decision_requires_reason():
    with pytest.raises(ValidationError):
        RiskDecision(allowed=False, risk_policy_version="v1")
    decision = RiskDecision(
        allowed=False,
        hard_blocks=("stale_market_data",),
        risk_policy_version="v1",
    )
    assert not decision.allowed


def test_primary_progression_and_no_unsafe_jump():
    assert require_transition(WorkflowState.SCAN, WorkflowState.WATCH) == WorkflowState.WATCH
    assert require_transition(WorkflowState.WATCH, WorkflowState.ARMED) == WorkflowState.ARMED
    assert require_transition(WorkflowState.ARMED, WorkflowState.SIGNAL_CANDIDATE) == WorkflowState.SIGNAL_CANDIDATE
    with pytest.raises(InvalidTransition):
        require_transition(WorkflowState.SCAN, WorkflowState.SIGNAL_CANDIDATE)


def test_no_trade_is_first_class_and_replay_can_restart_scan():
    assert require_transition(WorkflowState.SCAN, WorkflowState.NO_TRADE) == WorkflowState.NO_TRADE
    assert require_transition(WorkflowState.NO_TRADE, WorkflowState.SCAN) == WorkflowState.SCAN
