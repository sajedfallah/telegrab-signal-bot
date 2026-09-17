from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import isfinite

from .contracts import Direction, MarketSnapshot, SupervisorDecision, WorkflowState


@dataclass(frozen=True)
class SignalPlan:
    symbol: str
    snapshot_id: str
    direction: Direction
    entry: float
    entry_low: float
    entry_high: float
    stop_loss: float
    take_profits: tuple[float, ...]
    rr: float
    created_at: datetime
    expires_at: datetime
    evidence: tuple[str, ...]
    invalidation: str


@dataclass(frozen=True)
class SignalBuildResult:
    plan: SignalPlan | None
    blocks: tuple[str, ...] = ()


def _rows(snapshot: MarketSnapshot, tf: str) -> tuple[dict, ...]:
    return snapshot.timeframes.get(tf, ())


def _quote_mid(snapshot: MarketSnapshot) -> float | None:
    if snapshot.bid is not None and snapshot.ask is not None:
        return (float(snapshot.bid) + float(snapshot.ask)) / 2.0
    if snapshot.last is not None:
        return float(snapshot.last)
    return None


def _latest_directional_fvg(rows: tuple[dict, ...], direction: Direction) -> tuple[float, float] | None:
    found = None
    for i in range(max(0, len(rows) - 100), len(rows) - 2):
        left, right = rows[i], rows[i + 2]
        if direction == Direction.LONG and float(left["high"]) < float(right["low"]):
            found = (float(left["high"]), float(right["low"]))
        elif direction == Direction.SHORT and float(left["low"]) > float(right["high"]):
            found = (float(right["high"]), float(left["low"]))
    return found


def _m5_liquidity_anchor(rows: tuple[dict, ...], direction: Direction) -> float | None:
    if len(rows) < 14:
        return None
    # The ICT assessor confirms the sweep on the penultimate closed 5M bar.
    sweep_bar = rows[-2]
    prior = rows[-14:-2]
    if direction == Direction.LONG:
        prior_low = min(float(x["low"]) for x in prior)
        if float(sweep_bar["low"]) < prior_low and float(sweep_bar["close"]) > prior_low:
            return float(sweep_bar["low"])
    elif direction == Direction.SHORT:
        prior_high = max(float(x["high"]) for x in prior)
        if float(sweep_bar["high"]) > prior_high and float(sweep_bar["close"]) < prior_high:
            return float(sweep_bar["high"])
    return None


def _targets(m15: tuple[dict, ...], entry: float, stop: float, direction: Direction) -> tuple[float, ...]:
    risk = abs(entry - stop)
    if risk <= 0:
        return ()
    # Structure/liquidity-derived targets only. No ATR or arbitrary percentage targets.
    recent = m15[-80:]
    if direction == Direction.LONG:
        candidates = sorted({float(x["high"]) for x in recent if float(x["high"]) > entry})
    else:
        candidates = sorted({float(x["low"]) for x in recent if float(x["low"]) < entry}, reverse=True)
    # Require at least 1R before a structural level can become TP1.
    eligible = [p for p in candidates if abs(p - entry) >= risk]
    if not eligible:
        return ()
    selected: list[float] = []
    for p in eligible:
        if not selected or abs(p - selected[-1]) >= risk * 0.5:
            selected.append(p)
        if len(selected) == 3:
            break
    return tuple(selected)


def build_signal(snapshot: MarketSnapshot, decision: SupervisorDecision) -> SignalBuildResult:
    """Construct a shadow signal from confirmed ICT market structure.

    Fail closed unless a fresh directional SIGNAL_CANDIDATE exists. Entry comes
    from the executable quote constrained by a directional 15M FVG when one is
    actionable. Stop is beyond the confirmed 5M liquidity sweep. Targets are
    existing 15M structural liquidity levels. Nothing is synthesized from ATR,
    percentages, or guessed pip distances.
    """
    blocks: list[str] = []
    if decision.state != WorkflowState.SIGNAL_CANDIDATE:
        blocks.append("not_signal_candidate")
    if decision.direction not in {Direction.LONG, Direction.SHORT}:
        blocks.append("missing_direction")
    if decision.snapshot_id != snapshot.snapshot_id:
        blocks.append("snapshot_mismatch")
    if snapshot.data_freshness_ms > 30_000:
        blocks.append("stale_market_data")
    if snapshot.missing_data:
        blocks.extend(f"missing:{x}" for x in snapshot.missing_data)
    price = _quote_mid(snapshot)
    if price is None or not isfinite(price) or price <= 0:
        blocks.append("missing_quote")
    m15, m5 = _rows(snapshot, "M15"), _rows(snapshot, "M5")
    if len(m15) < 20:
        blocks.append("candles:M15")
    if len(m5) < 20:
        blocks.append("candles:M5")
    if blocks:
        return SignalBuildResult(None, tuple(dict.fromkeys(blocks)))

    direction = decision.direction
    assert direction in {Direction.LONG, Direction.SHORT} and price is not None
    fvg = _latest_directional_fvg(m15, direction)
    sweep = _m5_liquidity_anchor(m5, direction)
    if sweep is None:
        return SignalBuildResult(None, ("5m_sweep_not_reverified",))

    entry = float(snapshot.ask if direction == Direction.LONG else snapshot.bid)
    if fvg is not None:
        low, high = fvg
        # A stale/remote FVG is context, not permission to fabricate a limit entry.
        if low <= price <= high:
            entry_low, entry_high = low, high
        else:
            entry_low = entry_high = entry
    else:
        entry_low = entry_high = entry

    stop = sweep
    if direction == Direction.LONG and stop >= entry:
        return SignalBuildResult(None, ("invalid_long_stop_structure",))
    if direction == Direction.SHORT and stop <= entry:
        return SignalBuildResult(None, ("invalid_short_stop_structure",))
    risk = abs(entry - stop)
    if risk <= 0:
        return SignalBuildResult(None, ("zero_signal_risk",))

    tps = _targets(m15, entry, stop, direction)
    if not tps:
        return SignalBuildResult(None, ("no_valid_structural_target",))
    rr = abs(tps[0] - entry) / risk
    if not isfinite(rr) or rr <= 0:
        return SignalBuildResult(None, ("invalid_rr",))

    evidence = ["fresh directional SIGNAL_CANDIDATE", "5M liquidity sweep/reclaim reverified", "SL anchored beyond confirmed 5M sweep", "TPs derived from existing 15M structural liquidity"]
    if fvg is not None:
        evidence.append(f"15M directional FVG {fvg[0]:g}-{fvg[1]:g}")
    invalidation = "5M confirmed sweep structure fails before/after entry"
    return SignalBuildResult(
        SignalPlan(
            symbol=snapshot.symbol,
            snapshot_id=snapshot.snapshot_id,
            direction=direction,
            entry=entry,
            entry_low=entry_low,
            entry_high=entry_high,
            stop_loss=stop,
            take_profits=tps,
            rr=rr,
            created_at=snapshot.as_of,
            expires_at=snapshot.as_of + timedelta(minutes=15),
            evidence=tuple(evidence),
            invalidation=invalidation,
        )
    )
