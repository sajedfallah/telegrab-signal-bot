from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DailyQuadrant:
    candle_time: int
    wick_side: str
    low: float
    high: float
    level_25: float
    level_50: float
    level_75: float

    def contains(self, price: float) -> bool:
        return self.low <= price <= self.high


def derive_daily_quadrant(d1: tuple[dict, ...], *, lookback: int = 10) -> DailyQuadrant | None:
    """Apply the NEXUS Daily Quadrant rule to closed D1 candles.

    Inspect at most the last 10 closed candles, select the longest individual
    wick, and split that wick range into 25/50/75 structural levels.
    """
    if not d1:
        return None
    candidates = d1[-max(1, min(10, lookback)):]
    best = None
    best_len = -1.0
    for row in candidates:
        o, h, l, c = (float(row[x]) for x in ("open", "high", "low", "close"))
        body_high, body_low = max(o, c), min(o, c)
        upper = max(0.0, h - body_high)
        lower = max(0.0, body_low - l)
        if upper > best_len:
            best_len = upper
            best = (row, "UPPER", body_high, h)
        if lower > best_len:
            best_len = lower
            best = (row, "LOWER", l, body_low)
    if best is None or best_len <= 0:
        return None
    row, side, low, high = best
    span = high - low
    return DailyQuadrant(
        candle_time=int(row["time"]), wick_side=side, low=low, high=high,
        level_25=low + span * 0.25, level_50=low + span * 0.50,
        level_75=low + span * 0.75,
    )
