from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone

@dataclass(frozen=True)
class Quote:
    symbol: str
    bid: float
    ask: float
    ts: datetime
    @property
    def spread(self) -> float: return self.ask-self.bid
    @property
    def stale_age_seconds(self) -> float: return max(0.0,(datetime.now(timezone.utc)-self.ts.astimezone(timezone.utc)).total_seconds())

@dataclass(frozen=True)
class Candle:
    symbol: str
    timeframe: str
    open_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
