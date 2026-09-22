from __future__ import annotations

import math
from typing import Any


STRUCTURE_VERSION = "ai-market-structure-v1"

_TIMEFRAME_WEIGHTS = {
    "H4": 4.0,
    "H1": 3.0,
    "M15": 2.0,
    "M5": 1.0,
}


def _finite(value: Any) -> float:
    value = float(value)

    if not math.isfinite(value):
        raise ValueError("non-finite market value")

    return value


def _clean(
    candles: list[dict[str, Any]],
) -> list[dict[str, float]]:
    result: list[dict[str, float]] = []

    for raw in candles:
        result.append({
            "time": int(raw["time"]),
            "open": _finite(raw["open"]),
            "high": _finite(raw["high"]),
            "low": _finite(raw["low"]),
            "close": _finite(raw["close"]),
        })

    result.sort(
        key=lambda item: item["time"]
    )

    return result


def _atr(
    candles: list[dict[str, float]],
    period: int = 14,
) -> float | None:
    if len(candles) < 2:
        return None

    values: list[float] = []
    previous_close = candles[0]["close"]

    for candle in candles[1:]:
        values.append(
            max(
                candle["high"] - candle["low"],
                abs(
                    candle["high"]
                    - previous_close
                ),
                abs(
                    candle["low"]
                    - previous_close
                ),
            )
        )

        previous_close = candle["close"]

    if not values:
        return None

    sample = values[-period:]

    return sum(sample) / len(sample)


def _pivots(
    candles: list[dict[str, float]],
    window: int = 2,
) -> tuple[list[dict[str, float]], list[dict[str, float]]]:
    highs: list[dict[str, float]] = []
    lows: list[dict[str, float]] = []

    for index in range(
        window,
        len(candles) - window,
    ):
        current = candles[index]

        left = candles[
            index - window:index
        ]

        right = candles[
            index + 1:index + 1 + window
        ]

        if all(
            current["high"] >= item["high"]
            for item in left + right
        ):
            highs.append({
                "time": current["time"],
                "price": current["high"],
            })

        if all(
            current["low"] <= item["low"]
            for item in left + right
        ):
            lows.append({
                "time": current["time"],
                "price": current["low"],
            })

    return highs, lows


def _structure_label(
    highs: list[dict[str, float]],
    lows: list[dict[str, float]],
) -> tuple[str, dict[str, Any]]:
    evidence: dict[str, Any] = {
        "last_high": None,
        "previous_high": None,
        "last_low": None,
        "previous_low": None,
        "high_state": "UNKNOWN",
        "low_state": "UNKNOWN",
    }

    if len(highs) < 2 or len(lows) < 2:
        return "INSUFFICIENT", evidence

    previous_high = highs[-2]
    last_high = highs[-1]

    previous_low = lows[-2]
    last_low = lows[-1]

    high_state = (
        "HH"
        if last_high["price"] > previous_high["price"]
        else "LH"
    )

    low_state = (
        "HL"
        if last_low["price"] > previous_low["price"]
        else "LL"
    )

    evidence.update({
        "last_high": last_high,
        "previous_high": previous_high,
        "last_low": last_low,
        "previous_low": previous_low,
        "high_state": high_state,
        "low_state": low_state,
    })

    if high_state == "HH" and low_state == "HL":
        return "BULLISH", evidence

    if high_state == "LH" and low_state == "LL":
        return "BEARISH", evidence

    if high_state == "HH" and low_state == "LL":
        return "EXPANDING_RANGE", evidence

    if high_state == "LH" and low_state == "HL":
        return "COMPRESSION", evidence

    return "MIXED", evidence


def _range_position(
    candles: list[dict[str, float]],
    *,
    lookback: int = 20,
) -> dict[str, Any]:
    sample = candles[-lookback:]

    high = max(
        candle["high"]
        for candle in sample
    )

    low = min(
        candle["low"]
        for candle in sample
    )

    close = sample[-1]["close"]

    width = high - low

    if width <= 0:
        position = 0.5
    else:
        position = (
            close - low
        ) / width

    if position >= 0.75:
        zone = "PREMIUM"

    elif position <= 0.25:
        zone = "DISCOUNT"

    else:
        zone = "MIDRANGE"

    return {
        "high": high,
        "low": low,
        "close": close,
        "position": round(position, 4),
        "zone": zone,
    }


def _displacement(
    candles: list[dict[str, float]],
    atr: float | None,
) -> dict[str, Any]:
    candle = candles[-1]

    body = abs(
        candle["close"] - candle["open"]
    )

    direction = (
        "BULLISH"
        if candle["close"] > candle["open"]
        else "BEARISH"
        if candle["close"] < candle["open"]
        else "NEUTRAL"
    )

    if not atr or atr <= 0:
        ratio = None
        strong = False

    else:
        ratio = body / atr
        strong = ratio >= 0.80

    return {
        "direction": direction,
        "body": body,
        "body_atr_ratio": (
            round(ratio, 4)
            if ratio is not None
            else None
        ),
        "strong": strong,
    }


def analyze_timeframe_structure(
    *,
    timeframe: str,
    candles: list[dict[str, Any]],
) -> dict[str, Any]:
    tf = str(timeframe).upper()
    cleaned = _clean(candles)

    if len(cleaned) < 20:
        raise ValueError(
            f"insufficient candles for {tf}"
        )

    atr = _atr(cleaned)

    highs, lows = _pivots(cleaned)

    structure, evidence = _structure_label(
        highs,
        lows,
    )

    range_info = _range_position(
        cleaned,
        lookback=20,
    )

    displacement = _displacement(
        cleaned,
        atr,
    )

    if structure == "BULLISH":
        bias = "BULLISH"
        bias_score = 1.0

    elif structure == "BEARISH":
        bias = "BEARISH"
        bias_score = -1.0

    elif structure == "EXPANDING_RANGE":
        bias = "NEUTRAL"
        bias_score = 0.0

    elif structure == "COMPRESSION":
        bias = "NEUTRAL"
        bias_score = 0.0

    else:
        bias = "NEUTRAL"
        bias_score = 0.0

    return {
        "timeframe": tf,
        "structure": structure,
        "bias": bias,
        "bias_score": bias_score,
        "atr": atr,
        "range": range_info,
        "displacement": displacement,
        "pivot_high_count": len(highs),
        "pivot_low_count": len(lows),
        "evidence": evidence,
    }


def analyze_market_structure(
    *,
    candles_by_timeframe: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:

    timeframe_results: dict[str, Any] = {}

    weighted_score = 0.0
    total_weight = 0.0

    for timeframe in (
        "H4",
        "H1",
        "M15",
        "M5",
    ):
        candles = candles_by_timeframe.get(
            timeframe,
            [],
        )

        if not candles:
            continue

        result = analyze_timeframe_structure(
            timeframe=timeframe,
            candles=candles,
        )

        timeframe_results[timeframe] = result

        weight = _TIMEFRAME_WEIGHTS.get(
            timeframe,
            1.0,
        )

        weighted_score += (
            float(result["bias_score"])
            * weight
        )

        total_weight += weight

    if not timeframe_results:
        raise ValueError(
            "no timeframe data"
        )

    normalized_score = (
        weighted_score / total_weight
        if total_weight > 0
        else 0.0
    )

    if normalized_score >= 0.35:
        overall_bias = "BULLISH"

    elif normalized_score <= -0.35:
        overall_bias = "BEARISH"

    else:
        overall_bias = "MIXED"

    htf = [
        timeframe_results.get("H4", {}).get("bias"),
        timeframe_results.get("H1", {}).get("bias"),
    ]

    ltf = [
        timeframe_results.get("M15", {}).get("bias"),
        timeframe_results.get("M5", {}).get("bias"),
    ]

    htf_clean = [
        value
        for value in htf
        if value
    ]

    ltf_clean = [
        value
        for value in ltf
        if value
    ]

    htf_alignment = (
        len(set(htf_clean)) == 1
        if len(htf_clean) >= 2
        else False
    )

    ltf_alignment = (
        len(set(ltf_clean)) == 1
        if len(ltf_clean) >= 2
        else False
    )

    full_alignment = (
        htf_alignment
        and ltf_alignment
        and htf_clean
        and ltf_clean
        and htf_clean[0] == ltf_clean[0]
    )

    return {
        "structure_version": STRUCTURE_VERSION,
        "overall_bias": overall_bias,
        "weighted_bias_score": round(
            normalized_score,
            4,
        ),
        "htf_alignment": htf_alignment,
        "ltf_alignment": ltf_alignment,
        "full_alignment": bool(
            full_alignment
        ),
        "timeframes": timeframe_results,
        "advisory_only": True,
    }
