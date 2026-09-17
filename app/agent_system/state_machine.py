from __future__ import annotations

from .contracts import WorkflowState


class InvalidTransition(ValueError):
    pass


_ALLOWED: dict[WorkflowState, frozenset[WorkflowState]] = {
    WorkflowState.SCAN: frozenset({WorkflowState.WATCH, WorkflowState.WAIT, WorkflowState.NO_TRADE, WorkflowState.CANCELLED}),
    WorkflowState.WATCH: frozenset({WorkflowState.ARMED, WorkflowState.WAIT, WorkflowState.NO_TRADE, WorkflowState.CANCELLED}),
    WorkflowState.ARMED: frozenset({WorkflowState.SIGNAL_CANDIDATE, WorkflowState.WAIT, WorkflowState.NO_TRADE, WorkflowState.CANCELLED}),
    WorkflowState.SIGNAL_CANDIDATE: frozenset({WorkflowState.WAIT, WorkflowState.NO_TRADE, WorkflowState.CANCELLED}),
    WorkflowState.WAIT: frozenset({WorkflowState.SCAN, WorkflowState.WATCH, WorkflowState.CANCELLED, WorkflowState.NO_TRADE}),
    WorkflowState.CANCELLED: frozenset({WorkflowState.SCAN}),
    WorkflowState.NO_TRADE: frozenset({WorkflowState.SCAN}),
}


def can_transition(current: WorkflowState, target: WorkflowState) -> bool:
    current = WorkflowState(current)
    target = WorkflowState(target)
    return target in _ALLOWED[current]


def require_transition(current: WorkflowState, target: WorkflowState) -> WorkflowState:
    current = WorkflowState(current)
    target = WorkflowState(target)
    if not can_transition(current, target):
        raise InvalidTransition(f"unsafe agent workflow transition: {current.value} -> {target.value}")
    return target
