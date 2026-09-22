from __future__ import annotations

import math
from typing import Any, Iterable


ENGINE_VERSION = "ai-level-engine-v2"

SUPPORTED_DIRECTIONS = {"BUY", "SELL"}


_TIMEFRAME_WEIGHT = {
    "H4": 4.0,
    "H1": 3.0,
    "M15": 2.0,
    "M5": 1.0,
}

_MIN_TARGET_RR = 0.90
_TARGET_RR_IDEALS = (1.0, 2.0, 3.0)


def _pivot_levels_tagged(
    candles: list[dict[str, float]],
    *,
    timeframe: str,
    window: int = 2,
) -> tuple[list[dict[str, float | str]], list[dict[str, float | str]]]:
    highs: list[dict[str, float | str]] = []
    lows: list[dict[str, float | str]] = []

    if len(candles) < (window * 2 + 1):
        return highs, lows

    for index in range(window, len(candles) - window):
        current = candles[index]

        left = candles[index - window:index]
        right = candles[index + 1:index + 1 + window]

        if all(current["high"] >= item["high"] for item in left + right):
            highs.append({
                "price": float(current["high"]),
                "timeframe": timeframe,
            })

        if all(current["low"] <= item["low"] for item in left + right):
            lows.append({
                "price": float(current["low"]),
                "timeframe": timeframe,
            })

    return highs, lows


def _merge_tagged_levels(
    levels: list[dict[str, float | str]],
    tolerance: float,
) -> list[dict[str, Any]]:
    if not levels:
        return []

    ordered = sorted(
        levels,
        key=lambda item: float(item["price"]),
    )

    groups: list[list[dict[str, float | str]]] = []

    for item in ordered:
        price = float(item["price"])

        if not groups:
            groups.append([item])
            continue

        previous_prices = [
            float(member["price"])
            for member in groups[-1]
        ]

        center = sum(previous_prices) / len(previous_prices)

        if abs(price - center) <= tolerance:
            groups[-1].append(item)
        else:
            groups.append([item])

    merged: list[dict[str, Any]] = []

    for group in groups:
        prices = [float(item["price"]) for item in group]
        timeframes = sorted({
            str(item["timeframe"])
            for item in group
        })

        weight = sum(
            _TIMEFRAME_WEIGHT.get(tf, 1.0)
            for tf in timeframes
        )

        merged.append({
            "price": sum(prices) / len(prices),
            "timeframes": timeframes,
            "weight": weight,
            "touches": len(group),
        })

    return merged


def _rank_target_candidates(
    *,
    direction: str,
    entry: float,
    stop: float,
    candidates: list[dict[str, Any]],
    digits: int,
) -> list[dict[str, Any]]:
    risk = (
        entry - stop
        if direction == "BUY"
        else stop - entry
    )

    if risk <= 0:
        return []

    ranked: list[dict[str, Any]] = []

    for item in candidates:
        price = float(item["price"])

        reward = (
            price - entry
            if direction == "BUY"
            else entry - price
        )

        if reward <= 0:
            continue

        rr = reward / risk

        if rr < _MIN_TARGET_RR:
            continue

        nearest_ideal = min(
            abs(rr - ideal)
            for ideal in _TARGET_RR_IDEALS
        )

        rr_quality = max(
            0.0,
            3.0 - nearest_ideal,
        )

        htf_weight = float(item.get("weight", 1.0))
        touches = int(item.get("touches", 1))

        score = (
            htf_weight * 10.0
            + min(touches, 5) * 2.0
            + rr_quality
        )

        ranked.append({
            "price": round(price, digits),
            "rr": round(rr, 3),
            "score": round(score, 3),
            "timeframes": item.get("timeframes", []),
            "touches": touches,
        })

    ranked.sort(
        key=lambda item: (
            -float(item["score"]),
            abs(float(item["rr"]) - 2.0),
        )
    )

    return ranked


def _finite(value: Any) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("non-finite market value")
    return value


def _clean_candles(candles: Iterable[dict[str, Any]]) -> list[dict[str, float]]:
    cleaned: list[dict[str, float]] = []

    for raw in candles:
        candle = {
            "time": int(raw["time"]),
            "open": _finite(raw["open"]),
            "high": _finite(raw["high"]),
            "low": _finite(raw["low"]),
            "close": _finite(raw["close"]),
        }

        if candle["high"] < max(candle["open"], candle["close"], candle["low"]):
            raise ValueError("invalid candle high")

        if candle["low"] > min(candle["open"], candle["close"], candle["high"]):
            raise ValueError("invalid candle low")

        cleaned.append(candle)

    cleaned.sort(key=lambda item: item["time"])
    return cleaned


def _atr(candles: list[dict[str, float]], period: int = 14) -> float | None:
    if len(candles) < 2:
        return None

    ranges: list[float] = []
    previous_close = candles[0]["close"]

    for candle in candles[1:]:
        tr = max(
            candle["high"] - candle["low"],
            abs(candle["high"] - previous_close),
            abs(candle["low"] - previous_close),
        )
        ranges.append(tr)
        previous_close = candle["close"]

    if not ranges:
        return None

    sample = ranges[-max(1, int(period)):]
    return sum(sample) / len(sample)


def _pivot_levels(
    candles: list[dict[str, float]],
    *,
    window: int = 2,
) -> tuple[list[float], list[float]]:
    highs: list[float] = []
    lows: list[float] = []

    if len(candles) < (window * 2 + 1):
        return highs, lows

    for index in range(window, len(candles) - window):
        current = candles[index]

        left = candles[index - window:index]
        right = candles[index + 1:index + 1 + window]

        if all(current["high"] >= item["high"] for item in left + right):
            highs.append(current["high"])

        if all(current["low"] <= item["low"] for item in left + right):
            lows.append(current["low"])

    return highs, lows


def _unique_levels(levels: Iterable[float], tolerance: float) -> list[float]:
    result: list[float] = []

    for level in sorted(float(value) for value in levels):
        if not result or abs(level - result[-1]) > tolerance:
            result.append(level)

    return result


def _nearest_below(levels: Iterable[float], price: float) -> float | None:
    valid = [float(level) for level in levels if float(level) < price]
    return max(valid) if valid else None


def _nearest_above(levels: Iterable[float], price: float) -> float | None:
    valid = [float(level) for level in levels if float(level) > price]
    return min(valid) if valid else None


def _round(value: float | None, digits: int) -> float | None:
    if value is None:
        return None
    return round(float(value), max(0, int(digits)))


def analyze_numeric_levels(
    *,
    symbol: str,
    direction: str,
    bid: float,
    ask: float,
    digits: int,
    candles_by_timeframe: dict[str, list[dict[str, Any]]],
    user_entry: float | None = None,
    user_stop_loss: float | None = None,
    user_targets: list[float] | None = None,
) -> dict[str, Any]:
    """
    Produce deterministic price-level candidates from supplied market data.

    Advisory only: this function does not publish, execute, modify,
    approve, reject, or gate a trade.
    """

    direction = str(direction or "").strip().upper()

    if direction not in SUPPORTED_DIRECTIONS:
        raise ValueError("direction must be BUY or SELL")

    bid = _finite(bid)
    ask = _finite(ask)

    if ask < bid:
        raise ValueError("ask must be >= bid")

    digits = max(0, min(10, int(digits)))
    mid = (bid + ask) / 2.0
    spread = ask - bid

    normalized: dict[str, list[dict[str, float]]] = {}

    for timeframe, candles in candles_by_timeframe.items():
        normalized[str(timeframe).upper()] = _clean_candles(candles)

    required = ("H1", "M15", "M5")
    missing = [tf for tf in required if len(normalized.get(tf, [])) < 5]

    if missing:
        raise ValueError(
            "insufficient candle data for: " + ", ".join(missing)
        )

    atrs = {
        tf: _atr(series)
        for tf, series in normalized.items()
    }

    structural_highs_tagged: list[dict[str, float | str]] = []
    structural_lows_tagged: list[dict[str, float | str]] = []

    for tf in ("H4", "H1", "M15", "M5"):
        series = normalized.get(tf, [])

        if not series:
            continue

        highs, lows = _pivot_levels_tagged(
            series,
            timeframe=tf,
        )

        structural_highs_tagged.extend(highs[-16:])
        structural_lows_tagged.extend(lows[-16:])

    reference_atr = (
        atrs.get("M15")
        or atrs.get("M5")
        or atrs.get("H1")
        or max(mid * 0.001, 10 ** (-digits))
    )

    tolerance = max(
        reference_atr * 0.08,
        10 ** (-digits),
    )

    merged_highs = _merge_tagged_levels(
        structural_highs_tagged,
        tolerance,
    )

    merged_lows = _merge_tagged_levels(
        structural_lows_tagged,
        tolerance,
    )

    nearest_resistance_obj = min(
        (
            item
            for item in merged_highs
            if float(item["price"]) > mid
        ),
        key=lambda item: float(item["price"]) - mid,
        default=None,
    )

    nearest_support_obj = min(
        (
            item
            for item in merged_lows
            if float(item["price"]) < mid
        ),
        key=lambda item: mid - float(item["price"]),
        default=None,
    )

    nearest_resistance = (
        float(nearest_resistance_obj["price"])
        if nearest_resistance_obj
        else None
    )

    nearest_support = (
        float(nearest_support_obj["price"])
        if nearest_support_obj
        else None
    )

    sweep_high = nearest_resistance
    sweep_low = nearest_support

    buffer_value = max(
        reference_atr * 0.15,
        spread * 2.0,
        10 ** (-digits),
    )

    if direction == "BUY":
        anchor = nearest_support

        if anchor is None:
            anchor = min(
                candle["low"]
                for candle in normalized["M15"][-10:]
            )

        zone_half = max(
            reference_atr * 0.12,
            spread,
        )

        entry_low = anchor - zone_half
        entry_high = anchor + zone_half
        best_entry = anchor

        structural_stop = anchor - max(
            reference_atr * 0.35,
            buffer_value,
        )

        invalidation = structural_stop
        risk = max(
            best_entry - structural_stop,
            tolerance,
        )

        directional_candidates = [
            item
            for item in merged_highs
            if float(item["price"]) > best_entry
        ]

        wait_for_sweep_level = sweep_low

    else:
        anchor = nearest_resistance

        if anchor is None:
            anchor = max(
                candle["high"]
                for candle in normalized["M15"][-10:]
            )

        zone_half = max(
            reference_atr * 0.12,
            spread,
        )

        entry_low = anchor - zone_half
        entry_high = anchor + zone_half
        best_entry = anchor

        structural_stop = anchor + max(
            reference_atr * 0.35,
            buffer_value,
        )

        invalidation = structural_stop
        risk = max(
            structural_stop - best_entry,
            tolerance,
        )

        directional_candidates = [
            item
            for item in merged_lows
            if float(item["price"]) < best_entry
        ]

        wait_for_sweep_level = sweep_high

    ranked_targets = _rank_target_candidates(
        direction=direction,
        entry=best_entry,
        stop=structural_stop,
        candidates=directional_candidates,
        digits=digits,
    )

    selected_targets: list[float] = []

    for ideal_rr in _TARGET_RR_IDEALS:
        eligible = [
            item
            for item in ranked_targets
            if float(item["price"]) not in selected_targets
        ]

        if eligible:
            chosen = min(
                eligible,
                key=lambda item: (
                    abs(float(item["rr"]) - ideal_rr),
                    -float(item["score"]),
                ),
            )

            selected_targets.append(
                float(chosen["price"])
            )

    while len(selected_targets) < 3:
        rr = _TARGET_RR_IDEALS[len(selected_targets)]

        fallback = (
            best_entry + risk * rr
            if direction == "BUY"
            else best_entry - risk * rr
        )

        selected_targets.append(fallback)

    if direction == "BUY":
        selected_targets = sorted(selected_targets)
    else:
        selected_targets = sorted(
            selected_targets,
            reverse=True,
        )

    target_values = selected_targets[:3]

    rr_values: list[float | None] = []

    for target in target_values:
        reward = (
            target - best_entry
            if direction == "BUY"
            else best_entry - target
        )

        rr_values.append(
            reward / risk
            if risk > 0 and reward > 0
            else None
        )

    user_review: dict[str, Any] = {
        "entry": _round(user_entry, digits) if user_entry is not None else None,
        "stop_loss": (
            _round(user_stop_loss, digits)
            if user_stop_loss is not None
            else None
        ),
        "targets": [
            _round(value, digits)
            for value in (user_targets or [])
        ],
    }

    if user_entry is not None:
        entry = float(user_entry)
        user_review["entry_inside_preferred_zone"] = (
            entry_low <= entry <= entry_high
        )

    return {
        "engine_version": ENGINE_VERSION,
        "symbol": str(symbol).upper(),
        "direction": direction,
        "market": {
            "bid": _round(bid, digits),
            "ask": _round(ask, digits),
            "mid": _round(mid, digits),
            "spread": _round(spread, digits),
        },
        "atr": {
            tf: _round(value, digits)
            for tf, value in atrs.items()
            if value is not None
        },
        "key_levels": {
            "nearest_support": _round(nearest_support, digits),
            "nearest_resistance": _round(nearest_resistance, digits),
            "sweep_low": _round(sweep_low, digits),
            "sweep_high": _round(sweep_high, digits),
            "support_evidence": (
                nearest_support_obj
                if nearest_support_obj
                else None
            ),
            "resistance_evidence": (
                nearest_resistance_obj
                if nearest_resistance_obj
                else None
            ),
        },
        "suggested_setup": {
            "preferred_entry_zone": {
                "low": _round(entry_low, digits),
                "high": _round(entry_high, digits),
            },
            "best_entry": _round(best_entry, digits),
            "structural_stop_loss": _round(structural_stop, digits),
            "invalidation": _round(invalidation, digits),
            "tp1": _round(target_values[0], digits),
            "tp2": _round(target_values[1], digits),
            "tp3": _round(target_values[2], digits),
            "wait_for_sweep_level": _round(
                wait_for_sweep_level,
                digits,
            ),
            "atr_buffer": _round(buffer_value, digits),
            "risk_reward": [
                round(value, 3) if value is not None else None
                for value in rr_values
            ],
            "ranked_target_candidates": ranked_targets[:10],
        },
        "user_setup": user_review,
        "advisory_only": True,
    }
