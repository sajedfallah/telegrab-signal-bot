from __future__ import annotations

from dataclasses import dataclass

from .contracts import MarketSnapshot, WorkflowState


@dataclass(frozen=True)
class ScanDecision:
    state: WorkflowState
    triggers: tuple[str, ...]
    blocks: tuple[str, ...]


_REQUIRED_TF = ("H1", "M15", "M5")


def _rows(snapshot: MarketSnapshot, timeframe: str) -> tuple[dict, ...]:
    return snapshot.timeframes.get(timeframe, ())


def _near(value: float, target: float, tolerance: float) -> bool:
    return abs(value - target) <= tolerance


def scan(snapshot: MarketSnapshot, *, max_freshness_ms: int = 30_000) -> ScanDecision:
    """Cheap deterministic pre-filter before specialist agents.

    V1 intentionally detects only objective market events. It does not infer a
    trade direction and cannot produce SIGNAL_CANDIDATE.
    """
    blocks: list[str] = []
    if snapshot.data_freshness_ms > max_freshness_ms:
        blocks.append("stale_market_data")
    if "quote" in {x.lower() for x in snapshot.missing_data}:
        blocks.append("missing_quote")
    for tf in _REQUIRED_TF:
        if len(_rows(snapshot, tf)) < 20:
            blocks.append(f"insufficient_{tf.lower()}_candles")
    if blocks:
        return ScanDecision(WorkflowState.NO_TRADE, (), tuple(dict.fromkeys(blocks)))

    price = (float(snapshot.bid) + float(snapshot.ask)) / 2.0 if snapshot.bid and snapshot.ask else float(snapshot.last or 0)
    if price <= 0:
        return ScanDecision(WorkflowState.NO_TRADE, (), ("invalid_market_price",))

    m15 = _rows(snapshot, "M15")
    m5 = _rows(snapshot, "M5")
    triggers: list[str] = []

    # Nearby recent M15 range boundary / liquidity proxy.
    recent15 = m15[-32:]
    hi15 = max(float(x["high"]) for x in recent15)
    lo15 = min(float(x["low"]) for x in recent15)
    range15 = max(hi15 - lo15, price * 0.0001)
    tolerance = max(range15 * 0.08, price * 0.00015)
    if _near(price, hi15, tolerance):
        triggers.append("near_m15_buy_side_liquidity")
    if _near(price, lo15, tolerance):
        triggers.append("near_m15_sell_side_liquidity")

    # Objective 5M sweep/reclaim detection. Specialist ICT agent will later
    # decide whether this has directional meaning in HTF context.
    prior = m5[-14:-2]
    penultimate = m5[-2]
    last = m5[-1]
    prior_high = max(float(x["high"]) for x in prior)
    prior_low = min(float(x["low"]) for x in prior)
    if float(penultimate["low"]) < prior_low and float(penultimate["close"]) > prior_low:
        triggers.append("m5_sell_side_sweep_reclaim")
    if float(penultimate["high"]) > prior_high and float(penultimate["close"]) < prior_high:
        triggers.append("m5_buy_side_sweep_reclaim")
    if float(last["close"]) > max(float(x["high"]) for x in m5[-7:-1]):
        triggers.append("m5_bullish_displacement")
    if float(last["close"]) < min(float(x["low"]) for x in m5[-7:-1]):
        triggers.append("m5_bearish_displacement")

    if triggers:
        return ScanDecision(WorkflowState.WATCH, tuple(dict.fromkeys(triggers)), ())
    return ScanDecision(WorkflowState.WAIT, (), ())
