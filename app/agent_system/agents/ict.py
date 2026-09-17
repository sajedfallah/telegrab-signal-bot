from __future__ import annotations

from datetime import timezone

from ..contracts import AgentAssessment, Direction, MarketSnapshot


def _rows(snapshot: MarketSnapshot, tf: str) -> tuple[dict, ...]:
    return snapshot.timeframes.get(tf, ())


def _pivots(rows: tuple[dict, ...], width: int = 2) -> tuple[list[float], list[float]]:
    highs: list[float] = []
    lows: list[float] = []
    for i in range(width, len(rows) - width):
        window = rows[i - width : i + width + 1]
        high = float(rows[i]["high"])
        low = float(rows[i]["low"])
        if high == max(float(x["high"]) for x in window):
            highs.append(high)
        if low == min(float(x["low"]) for x in window):
            lows.append(low)
    return highs, lows


def _h1_bias(rows: tuple[dict, ...]) -> tuple[Direction, str]:
    highs, lows = _pivots(rows[-80:])
    if len(highs) >= 2 and len(lows) >= 2:
        if highs[-1] > highs[-2] and lows[-1] > lows[-2]:
            return Direction.LONG, "1H structure HH/HL"
        if highs[-1] < highs[-2] and lows[-1] < lows[-2]:
            return Direction.SHORT, "1H structure LH/LL"
    recent = rows[-24:]
    midpoint = (max(float(x["high"]) for x in recent) + min(float(x["low"]) for x in recent)) / 2
    close = float(rows[-1]["close"])
    if close > midpoint and close >= float(rows[-6]["close"]):
        return Direction.LONG, "1H structure has bullish tendency"
    if close < midpoint and close <= float(rows[-6]["close"]):
        return Direction.SHORT, "1H structure has bearish tendency"
    return Direction.NEUTRAL, "1H structure is neutral/ranging"


def _latest_fvg(rows: tuple[dict, ...]) -> tuple[tuple[float, float] | None, tuple[float, float] | None]:
    bull = bear = None
    for i in range(max(0, len(rows) - 100), len(rows) - 2):
        left, right = rows[i], rows[i + 2]
        if float(left["high"]) < float(right["low"]):
            bull = (float(left["high"]), float(right["low"]))
        if float(left["low"]) > float(right["high"]):
            bear = (float(right["high"]), float(left["low"]))
    return bull, bear


def _latest_ob(rows: tuple[dict, ...]) -> tuple[tuple[float, float] | None, tuple[float, float] | None]:
    recent = rows[-60:]
    ranges = [float(x["high"]) - float(x["low"]) for x in recent[:-1]]
    avg = sum(ranges) / len(ranges) if ranges else 0
    bull = bear = None
    for i in range(1, len(recent)):
        cur, prev = recent[i], recent[i - 1]
        displacement = avg > 0 and float(cur["high"]) - float(cur["low"]) >= avg * 1.35
        if displacement and float(cur["close"]) > float(cur["open"]) and float(prev["close"]) < float(prev["open"]):
            bull = (float(prev["low"]), float(prev["high"]))
        if displacement and float(cur["close"]) < float(cur["open"]) and float(prev["close"]) > float(prev["open"]):
            bear = (float(prev["low"]), float(prev["high"]))
    return bull, bear


def _m5_trigger(rows: tuple[dict, ...]) -> tuple[Direction, tuple[str, ...]]:
    prior = rows[-14:-2]
    penultimate, last = rows[-2], rows[-1]
    prior_high = max(float(x["high"]) for x in prior)
    prior_low = min(float(x["low"]) for x in prior)
    bull_sweep = float(penultimate["low"]) < prior_low and float(penultimate["close"]) > prior_low
    bear_sweep = float(penultimate["high"]) > prior_high and float(penultimate["close"]) < prior_high
    bull_mss = float(last["close"]) > max(float(x["high"]) for x in rows[-7:-1])
    bear_mss = float(last["close"]) < min(float(x["low"]) for x in rows[-7:-1])
    evidence: list[str] = []
    if bull_sweep:
        evidence.append("5M sell-side liquidity sweep/reclaim")
    if bear_sweep:
        evidence.append("5M buy-side liquidity sweep/reclaim")
    if bull_mss:
        evidence.append("5M bullish displacement/MSS")
    if bear_mss:
        evidence.append("5M bearish displacement/MSS")
    if bull_sweep and bull_mss:
        return Direction.LONG, tuple(evidence)
    if bear_sweep and bear_mss:
        return Direction.SHORT, tuple(evidence)
    return Direction.NEUTRAL, tuple(evidence)


def assess_ict(snapshot: MarketSnapshot) -> AgentAssessment:
    """Assess NEXUS ICT evidence from one immutable snapshot.

    V1 is deterministic and observation-only. Confidence is deliberately left
    unset until journal/backtest/paper evidence supports calibration.
    """
    missing = list(snapshot.missing_data)
    h1, m15, m5 = (_rows(snapshot, tf) for tf in ("H1", "M15", "M5"))
    for tf, rows in (("H1", h1), ("M15", m15), ("M5", m5)):
        if len(rows) < 20:
            missing.append(f"candles:{tf}")
    if snapshot.data_freshness_ms > 30_000:
        missing.append("stale_market_data")

    if missing:
        return AgentAssessment(
            agent_id="nexus-ict-v1", symbol=snapshot.symbol, snapshot_id=snapshot.snapshot_id,
            direction=Direction.NEUTRAL, confidence=None,
            evidence=("ICT assessment failed closed because required market inputs are incomplete",),
            invalidations=("fresh H1/M15/M5 snapshot required",),
            missing_data=tuple(dict.fromkeys(missing)), created_at=snapshot.as_of.astimezone(timezone.utc),
        )

    bias, bias_note = _h1_bias(h1)
    bull_fvg, bear_fvg = _latest_fvg(m15)
    bull_ob, bear_ob = _latest_ob(m15)
    trigger, trigger_evidence = _m5_trigger(m5)
    evidence: list[str] = [bias_note]
    invalidations: list[str] = []

    if bull_fvg:
        evidence.append(f"15M bullish FVG {bull_fvg[0]:g}-{bull_fvg[1]:g}")
    if bear_fvg:
        evidence.append(f"15M bearish FVG {bear_fvg[0]:g}-{bear_fvg[1]:g}")
    if bull_ob:
        evidence.append(f"15M bullish OB {bull_ob[0]:g}-{bull_ob[1]:g}")
    if bear_ob:
        evidence.append(f"15M bearish OB {bear_ob[0]:g}-{bear_ob[1]:g}")
    evidence.extend(trigger_evidence)

    # Direction requires HTF bias and a same-direction 5M sweep+MSS trigger.
    # FVG/OB are evidence/context, not sufficient entry triggers by themselves.
    direction = Direction.NEUTRAL
    if bias == Direction.LONG and trigger == Direction.LONG:
        direction = Direction.LONG
        invalidations.append("invalidate if 5M bullish structure fails after trigger")
    elif bias == Direction.SHORT and trigger == Direction.SHORT:
        direction = Direction.SHORT
        invalidations.append("invalidate if 5M bearish structure fails after trigger")
    elif trigger != Direction.NEUTRAL and trigger != bias:
        evidence.append("5M trigger conflicts with 1H bias; wait")
        invalidations.append("HTF/LTF alignment required")
    else:
        invalidations.append("valid 5M liquidity sweep + MSS confirmation required")

    # Daily Quadrant is intentionally not inferred from generic candles in V1.
    # It will be injected as explicit structured HTF context once its dedicated
    # deterministic adapter is implemented; touching it can never be an entry.
    evidence.append("Daily Quadrant: explicit structured context not yet attached in V1")

    return AgentAssessment(
        agent_id="nexus-ict-v1", symbol=snapshot.symbol, snapshot_id=snapshot.snapshot_id,
        direction=direction, confidence=None, evidence=tuple(evidence),
        invalidations=tuple(invalidations), missing_data=(), created_at=snapshot.as_of.astimezone(timezone.utc),
    )
