from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from .agents.ict import _h1_bias
from .contracts import Direction, MarketSnapshot
from .poi_scanner_v23 import scan_pois


@dataclass(frozen=True)
class FullICTGate:
    allowed: bool
    checks: tuple[str, ...]
    blocks: tuple[str, ...]
    poi: tuple[float, float] | None = None


def verify_full_ict(snapshot: MarketSnapshot, direction: Direction, timeframe: str,
                    entry: float, stop: float, targets: tuple[float, ...],
                    min_rr: float | None) -> FullICTGate:
    """Additional fail-closed gate for automatic SHADOW publication, never order execution.

    Requires a recent completed-candle sweep -> later MSS -> post-MSS directional
    FVG -> subsequent retest. POI must overlap sweep candle. Existing signal
    builder and risk gate still apply independently.
    """
    blocks: list[str] = []
    checks: list[str] = []
    if timeframe not in {"M1", "M5"} or direction not in {Direction.LONG, Direction.SHORT}:
        return FullICTGate(False, (), ("unsupported_strategy",))
    if snapshot.data_freshness_ms > 30_000 or snapshot.missing_data:
        blocks.append("stale_or_missing_feed")
    if snapshot.bid is None or snapshot.ask is None or snapshot.ask < snapshot.bid:
        blocks.append("invalid_quote")
    if min_rr is None or not isfinite(min_rr) or min_rr <= 0:
        blocks.append("risk_policy_missing")
    rows = snapshot.timeframes.get(timeframe, ())
    h1 = snapshot.timeframes.get("H1", ())
    if len(rows) < 30 or len(h1) < 24:
        blocks.append("insufficient_candles")
    if any(not isfinite(v) for v in (entry, stop, *targets)) or not targets:
        blocks.append("invalid_plan")
    if blocks:
        return FullICTGate(False, tuple(checks), tuple(blocks))
    bias, _ = _h1_bias(h1)
    if bias != direction:
        return FullICTGate(False, tuple(checks), ("h1_bias_mismatch",))
    checks.append("htf_bias")

    if (direction == Direction.LONG and (stop >= entry or targets[0] <= entry)) or (
        direction == Direction.SHORT and (stop <= entry or targets[0] >= entry)
    ):
        return FullICTGate(False, tuple(checks), ("invalid_directional_plan",))
    if entry == stop:
        return FullICTGate(False, tuple(checks), ("zero_risk",))
    rr = abs(targets[0] - entry) / abs(entry - stop)
    if not isfinite(rr) or rr < min_rr:
        return FullICTGate(False, tuple(checks), ("rr_below_policy",))
    checks.append("risk_reward")

    # Use prior fully closed candles; last candle may still be forming.
    bars = rows[:-1]
    pois = [p for p in scan_pois(snapshot)
            if p["source"] in {"FVG", "OB", "DAILY_QUADRANT"}
            and p["direction"] in {direction.value, "BOTH"}]
    if not pois:
        return FullICTGate(False, tuple(checks), ("no_directional_poi",))
    # A recent sequence must genuinely touch a directional HTF zone.
    start = max(12, len(bars)-16)
    for sweep_i in range(start, len(bars)-4):
        candle = bars[sweep_i]
        prior = bars[sweep_i-12:sweep_i]
        lo, hi, close = (float(candle[k]) for k in ("low", "high", "close"))
        if direction == Direction.LONG:
            ref = min(float(b["low"]) for b in prior)
            swept = lo < ref < close
        else:
            ref = max(float(b["high"]) for b in prior)
            swept = hi > ref > close
        if not swept:
            continue
        matching = next((p for p in pois if lo <= p["high"] and hi >= p["low"]), None)
        if matching is None:
            continue
        for mss_i in range(sweep_i+1, len(bars)-3):
            pivot = bars[mss_i]
            prev = bars[max(sweep_i,mss_i-6):mss_i]
            if not prev:
                continue
            mss = (float(pivot["close"]) > max(float(x["high"]) for x in prev)
                   if direction == Direction.LONG
                   else float(pivot["close"]) < min(float(x["low"]) for x in prev))
            if not mss:
                continue
            # Distinct displacement candle body versus recent typical body.
            body = abs(float(pivot["close"])-float(pivot["open"]))
            body_sizes = [abs(float(x["close"])-float(x["open"])) for x in bars[max(0,mss_i-12):mss_i]]
            typical = sum(body_sizes)/len(body_sizes) if body_sizes else 0
            if not typical or body < typical*1.3:
                continue
            for gap_i in range(mss_i, len(bars)-3):
                left, right = bars[gap_i], bars[gap_i+2]
                if direction == Direction.LONG:
                    low, high = float(left["high"]), float(right["low"])
                else:
                    low, high = float(right["high"]), float(left["low"])
                if low >= high:
                    continue
                # A later closed candle must actually touch the FVG.
                retested = any(float(b["low"]) <= high and float(b["high"]) >= low
                               for b in bars[gap_i+3:])
                if not retested:
                    continue
                if not low <= entry <= high:
                    continue
                return FullICTGate(True, tuple((*checks,"qualified_poi_touch","sweep_reclaim",
                                                "mss_displacement","post_mss_fvg","later_retest")),
                                   (), (matching["low"],matching["high"]))
    return FullICTGate(False, tuple(checks), ("full_ict_sequence_unverified",))
