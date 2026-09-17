from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from math import isfinite
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"


class WorkflowState(str, Enum):
    SCAN = "SCAN"
    WATCH = "WATCH"
    ARMED = "ARMED"
    SIGNAL_CANDIDATE = "SIGNAL_CANDIDATE"
    WAIT = "WAIT"
    CANCELLED = "CANCELLED"
    NO_TRADE = "NO_TRADE"


class FrozenContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class MarketSnapshot(FrozenContract):
    snapshot_id: str = Field(min_length=8, max_length=128)
    symbol: str = Field(min_length=2, max_length=32)
    as_of: datetime
    source: str = Field(min_length=2, max_length=64)
    timeframes: dict[str, tuple[dict[str, Any], ...]] = Field(default_factory=dict)
    bid: float | None = Field(default=None, gt=0)
    ask: float | None = Field(default=None, gt=0)
    last: float | None = Field(default=None, gt=0)
    session: str | None = Field(default=None, max_length=32)
    scheduled_events: tuple[dict[str, Any], ...] = ()
    news_context: tuple[dict[str, Any], ...] = ()
    data_freshness_ms: int = Field(ge=0)
    missing_data: tuple[str, ...] = ()

    @field_validator("as_of")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("as_of must be timezone-aware")
        return value.astimezone(timezone.utc)

    @field_validator("bid", "ask", "last")
    @classmethod
    def finite_price(cls, value: float | None) -> float | None:
        if value is not None and not isfinite(float(value)):
            raise ValueError("prices must be finite")
        return value

    @model_validator(mode="after")
    def quote_is_consistent(self):
        if self.bid is not None and self.ask is not None and self.ask < self.bid:
            raise ValueError("ask must be greater than or equal to bid")
        if self.bid is None and self.ask is None and self.last is None:
            if "quote" not in {x.lower() for x in self.missing_data}:
                raise ValueError("missing quote must be explicit in missing_data")
        return self


class AgentAssessment(FrozenContract):
    agent_id: str = Field(min_length=2, max_length=64)
    symbol: str = Field(min_length=2, max_length=32)
    snapshot_id: str = Field(min_length=8, max_length=128)
    direction: Direction
    confidence: float | None = Field(default=None, ge=0, le=1)
    evidence: tuple[str, ...] = ()
    invalidations: tuple[str, ...] = ()
    missing_data: tuple[str, ...] = ()
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def created_at_timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        return value.astimezone(timezone.utc)


class SupervisorDecision(FrozenContract):
    symbol: str = Field(min_length=2, max_length=32)
    snapshot_id: str = Field(min_length=8, max_length=128)
    state: WorkflowState
    direction: Direction | None = None
    agreement: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    required_confirmation: tuple[str, ...] = ()
    explanation: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def candidate_requires_direction(self):
        if self.state == WorkflowState.SIGNAL_CANDIDATE and self.direction not in {Direction.LONG, Direction.SHORT}:
            raise ValueError("SIGNAL_CANDIDATE requires LONG or SHORT direction")
        if self.state in {WorkflowState.NO_TRADE, WorkflowState.CANCELLED} and self.direction not in {None, Direction.NEUTRAL}:
            raise ValueError("terminal no-trade states cannot carry a trade direction")
        return self


class RiskDecision(FrozenContract):
    allowed: bool
    hard_blocks: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    rr: float | None = Field(default=None, gt=0)
    risk_policy_version: str = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def blocks_are_authoritative(self):
        if self.allowed and self.hard_blocks:
            raise ValueError("allowed risk decision cannot contain hard blocks")
        if not self.allowed and not self.hard_blocks:
            raise ValueError("blocked risk decision must explain at least one hard block")
        return self
