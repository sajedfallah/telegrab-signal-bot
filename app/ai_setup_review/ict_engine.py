from __future__ import annotations

from dataclasses import dataclass
from typing import Any


ICT_ENGINE_VERSION = "ai-ict-engine-v8-confirmed-breaker"


TRADE_MODES = {
    "SWING",
    "INTRADAY",
    "FAST_SCALP",
}


MODE_TIMEFRAME_WEIGHTS = {
    "SWING": {
        "D1": 5.0,
        "H4": 4.0,
        "H1": 3.0,
        "M15": 1.5,
        "M5": 0.5,
        "M1": 0.0,
    },
    "INTRADAY": {
        "D1": 1.0,
        "H4": 4.0,
        "H1": 3.0,
        "M15": 2.5,
        "M5": 2.0,
        "M1": 0.5,
    },
    "FAST_SCALP": {
        "D1": 0.0,
        "H4": 0.25,
        "H1": 0.50,
        "M15": 1.50,
        "M5": 3.00,
        "M1": 4.00,
    },
}


MODE_TIMEFRAME_ROLES = {
    "SWING": {
        "D1": "PRIMARY_CONTEXT",
        "H4": "PRIMARY_CONTEXT",
        "H1": "SETUP_CONTEXT",
        "M15": "ENTRY_REFINEMENT",
        "M5": "MICRO_CONTEXT",
        "M1": "IGNORE",
    },
    "INTRADAY": {
        "D1": "BACKGROUND",
        "H4": "PRIMARY_CONTEXT",
        "H1": "PRIMARY_CONTEXT",
        "M15": "SETUP",
        "M5": "TRIGGER",
        "M1": "MICRO_CONFIRMATION",
    },
    "FAST_SCALP": {
        "D1": "IGNORE",
        "H4": "BACKGROUND_ONLY",
        "H1": "BACKGROUND_ONLY",
        "M15": "LOCAL_BIAS",
        "M5": "PRIMARY_SETUP",
        "M1": "PRIMARY_TRIGGER",
    },
}


def normalize_trade_mode(value: str | None) -> str:
    mode = str(value or "INTRADAY").strip().upper()

    if mode not in TRADE_MODES:
        raise ValueError(
            "unsupported trade mode: "
            + str(value)
        )

    return mode



@dataclass
class ICTEvent:
    event_type: str
    timeframe: str
    direction: str
    price: float | None
    strength: float
    reason: str
    evidence: dict[str, Any]


def _clean(candles: list[dict[str, Any]]) -> list[dict[str, float]]:
    result = []

    for row in candles:
        try:
            result.append({
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
            })
        except Exception:
            continue

    return result


def _atr(candles: list[dict[str, float]], period: int = 14) -> float:
    if len(candles) < 2:
        return 0.0

    trs = []

    for i in range(1, len(candles)):
        high = candles[i]["high"]
        low = candles[i]["low"]
        prev_close = candles[i - 1]["close"]

        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close),
        )

        trs.append(tr)

    sample = trs[-period:]

    if not sample:
        return 0.0

    return sum(sample) / len(sample)


def detect_fvgs(
    candles: list[dict[str, Any]],
    timeframe: str,
) -> list[dict[str, Any]]:

    c = _clean(candles)
    result = []

    if len(c) < 3:
        return result

    for i in range(2, len(c)):
        a = c[i - 2]
        b = c[i - 1]
        d = c[i]

        # Bullish FVG:
        # candle 3 low remains above candle 1 high.
        if d["low"] > a["high"]:
            low = a["high"]
            high = d["low"]

            result.append({
                "type": "BULLISH_FVG",
                "timeframe": timeframe,
                "low": low,
                "high": high,
                "mid": (low + high) / 2.0,
                "index": i,
                "impulse_body": abs(
                    b["close"] - b["open"]
                ),
            })

        # Bearish FVG:
        # candle 3 high remains below candle 1 low.
        if d["high"] < a["low"]:
            low = d["high"]
            high = a["low"]

            result.append({
                "type": "BEARISH_FVG",
                "timeframe": timeframe,
                "low": low,
                "high": high,
                "mid": (low + high) / 2.0,
                "index": i,
                "impulse_body": abs(
                    b["close"] - b["open"]
                ),
            })

    return result


def detect_equal_highs_lows(
    candles: list[dict[str, Any]],
    timeframe: str,
    tolerance_atr: float = 0.12,
) -> dict[str, list[dict[str, Any]]]:

    c = _clean(candles)

    atr = _atr(c)

    tolerance = atr * tolerance_atr

    highs = []
    lows = []

    if atr <= 0 or len(c) < 5:
        return {
            "equal_highs": highs,
            "equal_lows": lows,
        }

    for i in range(2, len(c)):

        for j in range(
            max(0, i - 20),
            i,
        ):

            if abs(
                c[i]["high"] - c[j]["high"]
            ) <= tolerance:

                highs.append({
                    "timeframe": timeframe,
                    "price": (
                        c[i]["high"]
                        + c[j]["high"]
                    ) / 2.0,
                    "indices": [j, i],
                    "distance": abs(
                        c[i]["high"]
                        - c[j]["high"]
                    ),
                })

                break

        for j in range(
            max(0, i - 20),
            i,
        ):

            if abs(
                c[i]["low"] - c[j]["low"]
            ) <= tolerance:

                lows.append({
                    "timeframe": timeframe,
                    "price": (
                        c[i]["low"]
                        + c[j]["low"]
                    ) / 2.0,
                    "indices": [j, i],
                    "distance": abs(
                        c[i]["low"]
                        - c[j]["low"]
                    ),
                })

                break

    return {
        "equal_highs": highs[-10:],
        "equal_lows": lows[-10:],
    }



def build_liquidity_pools(
    candles: list[dict[str, Any]],
    timeframe: str,
) -> dict[str, list[dict[str, Any]]]:

    c = _clean(candles)

    if len(c) < 5:
        return {
            "buy_side": [],
            "sell_side": [],
        }

    atr = _atr(c)

    if atr <= 0:
        return {
            "buy_side": [],
            "sell_side": [],
        }

    raw = detect_equal_highs_lows(
        candles,
        timeframe,
    )

    tolerance = atr * 0.12

    def cluster(
        items: list[dict[str, Any]],
        side: str,
    ) -> list[dict[str, Any]]:

        if not items:
            return []

        ordered = sorted(
            items,
            key=lambda x: float(
                x["price"]
            ),
        )

        groups = []

        for item in ordered:

            price = float(
                item["price"]
            )

            indices = set(
                int(x)
                for x in item.get(
                    "indices",
                    [],
                )
            )

            matched = None

            for group in groups:

                if abs(
                    price
                    - group["price_sum"]
                    / group["count"]
                ) <= tolerance:
                    matched = group
                    break

            if matched is None:

                groups.append({
                    "price_sum": price,
                    "count": 1,
                    "indices": set(
                        indices
                    ),
                    "members": 1,
                })

            else:

                matched[
                    "price_sum"
                ] += price

                matched[
                    "count"
                ] += 1

                matched[
                    "indices"
                ].update(
                    indices
                )

                matched[
                    "members"
                ] += 1

        pools = []

        for group in groups:

            unique_indices = sorted(
                group["indices"]
            )

            if len(
                unique_indices
            ) < 2:
                continue

            price = (
                group["price_sum"]
                / group["count"]
            )

            last_index = max(
                unique_indices
            )

            bars_ago = max(
                0,
                len(c)
                - 1
                - last_index,
            )

            touch_count = len(
                unique_indices
            )

            if touch_count >= 4:
                strength = "HIGH"

            elif touch_count == 3:
                strength = "MEDIUM"

            else:
                strength = "LOW"

            swept = False
            sweep_index = None
            reclaim_confirmed = False

            for i in range(
                last_index + 1,
                len(c),
            ):

                bar = c[i]

                if side == "BUY_SIDE":

                    pierced = (
                        bar["high"]
                        > price
                    )

                    reclaimed = (
                        bar["close"]
                        < price
                    )

                else:

                    pierced = (
                        bar["low"]
                        < price
                    )

                    reclaimed = (
                        bar["close"]
                        > price
                    )

                if pierced:

                    swept = True

                    if sweep_index is None:
                        sweep_index = i

                    if reclaimed:
                        reclaim_confirmed = True
                        break

            pools.append({
                "type": (
                    "BSL_POOL"
                    if side == "BUY_SIDE"
                    else "SSL_POOL"
                ),
                "timeframe": timeframe,
                "side": side,
                "price": round(
                    price,
                    6,
                ),
                "touch_count": touch_count,
                "source_member_count": int(
                    group["members"]
                ),
                "indices": unique_indices,
                "last_touch_index": last_index,
                "bars_ago": bars_ago,
                "strength": strength,
                "swept": swept,
                "sweep_index": sweep_index,
                "reclaim_confirmed": reclaim_confirmed,
            })

        pools.sort(
            key=lambda x: (
                x["bars_ago"],
                -x["touch_count"],
            )
        )

        return pools[:10]

    return {
        "buy_side": cluster(
            raw.get(
                "equal_highs",
                [],
            ),
            "BUY_SIDE",
        ),
        "sell_side": cluster(
            raw.get(
                "equal_lows",
                [],
            ),
            "SELL_SIDE",
        ),
    }

def detect_liquidity_sweeps(
    candles: list[dict[str, Any]],
    timeframe: str,
    lookback: int = 20,
) -> list[dict[str, Any]]:

    c = _clean(candles)
    result = []

    if len(c) < 5:
        return result

    start = max(
        2,
        len(c) - lookback,
    )

    for i in range(start, len(c)):

        prior = c[
            max(0, i - lookback):i
        ]

        if not prior:
            continue

        prior_high = max(
            x["high"]
            for x in prior
        )

        prior_low = min(
            x["low"]
            for x in prior
        )

        bar = c[i]

        # Buy-side liquidity sweep + reclaim.
        if (
            bar["high"] > prior_high
            and bar["close"] < prior_high
        ):
            result.append({
                "type": "BSL_SWEEP",
                "timeframe": timeframe,
                "level": prior_high,
                "extreme": bar["high"],
                "close": bar["close"],
                "index": i,
                "validated_reclaim": True,
            })

        # Sell-side liquidity sweep + reclaim.
        if (
            bar["low"] < prior_low
            and bar["close"] > prior_low
        ):
            result.append({
                "type": "SSL_SWEEP",
                "timeframe": timeframe,
                "level": prior_low,
                "extreme": bar["low"],
                "close": bar["close"],
                "index": i,
                "validated_reclaim": True,
            })

    return result


def detect_displacement(
    candles: list[dict[str, Any]],
    timeframe: str,
) -> dict[str, Any]:

    c = _clean(candles)

    if not c:
        return {
            "timeframe": timeframe,
            "direction": "NONE",
            "ratio": 0.0,
            "strong": False,
        }

    atr = _atr(c)

    bar = c[-1]

    body = abs(
        bar["close"] - bar["open"]
    )

    ratio = (
        body / atr
        if atr > 0
        else 0.0
    )

    if bar["close"] > bar["open"]:
        direction = "BULLISH"

    elif bar["close"] < bar["open"]:
        direction = "BEARISH"

    else:
        direction = "NONE"

    return {
        "timeframe": timeframe,
        "direction": direction,
        "body": body,
        "atr": atr,
        "ratio": ratio,
        "strong": ratio >= 0.80,
    }


def detect_daily_quadrant(
    candles: list[dict[str, Any]],
) -> dict[str, Any] | None:

    c = _clean(candles)

    if len(c) < 2:
        return None

    # Exclude current Daily candle.
    sample = c[
        max(0, len(c) - 11):-1
    ]

    if not sample:
        return None

    best = None
    best_size = -1.0

    for index, bar in enumerate(sample):

        body_high = max(
            bar["open"],
            bar["close"],
        )

        body_low = min(
            bar["open"],
            bar["close"],
        )

        upper_wick = (
            bar["high"]
            - body_high
        )

        lower_wick = (
            body_low
            - bar["low"]
        )

        if upper_wick >= lower_wick:
            wick_start = body_high
            wick_end = bar["high"]
            wick_type = "UPPER"
            size = upper_wick

        else:
            wick_start = body_low
            wick_end = bar["low"]
            wick_type = "LOWER"
            size = lower_wick

        if size > best_size:
            best_size = size

            best = {
                "sample_index": index,
                "wick_type": wick_type,
                "wick_start": wick_start,
                "wick_end": wick_end,
                "wick_size": size,
            }

    if not best:
        return None

    start = float(
        best["wick_start"]
    )

    end = float(
        best["wick_end"]
    )

    delta = (
        end - start
    )

    return {
        **best,
        "level_25": start + delta * 0.25,
        "level_50": start + delta * 0.50,
        "level_75": start + delta * 0.75,
        "priority": {
            "25": 1.0,
            "50": 2.0,
            "75": 2.5,
        },
    }



def _pivot_points(
    candles: list[dict[str, Any]],
    *,
    window: int = 2,
) -> dict[str, list[dict[str, Any]]]:

    c = _clean(candles)

    highs: list[dict[str, Any]] = []
    lows: list[dict[str, Any]] = []

    if len(c) < window * 2 + 1:
        return {
            "highs": highs,
            "lows": lows,
        }

    for i in range(
        window,
        len(c) - window,
    ):

        high = c[i]["high"]
        low = c[i]["low"]

        left = c[i - window:i]
        right = c[i + 1:i + window + 1]

        if (
            all(high > x["high"] for x in left)
            and all(high >= x["high"] for x in right)
        ):
            highs.append({
                "index": i,
                "price": high,
            })

        if (
            all(low < x["low"] for x in left)
            and all(low <= x["low"] for x in right)
        ):
            lows.append({
                "index": i,
                "price": low,
            })

    return {
        "highs": highs,
        "lows": lows,
    }


def detect_structure_events(
    candles: list[dict[str, Any]],
    timeframe: str,
) -> dict[str, Any]:

    c = _clean(candles)
    pivots = _pivot_points(c)

    highs = pivots["highs"]
    lows = pivots["lows"]

    events: list[dict[str, Any]] = []

    if len(c) < 5:
        return {
            "timeframe": timeframe,
            "events": events,
            "latest_event": None,
            "state": "UNKNOWN",
        }

    broken_highs: set[int] = set()
    broken_lows: set[int] = set()

    prior_state = "UNKNOWN"

    for i, bar in enumerate(c):

        prior_highs = [
            p for p in highs
            if p["index"] < i
        ]

        prior_lows = [
            p for p in lows
            if p["index"] < i
        ]

        if not prior_highs or not prior_lows:
            continue

        swing_high = prior_highs[-1]
        swing_low = prior_lows[-1]

        bullish_break = (
            bar["close"] > swing_high["price"]
            and swing_high["index"] not in broken_highs
        )

        bearish_break = (
            bar["close"] < swing_low["price"]
            and swing_low["index"] not in broken_lows
        )

        if bullish_break:
            event_type = (
                "BULLISH_BOS"
                if prior_state in (
                    "BULLISH",
                    "UNKNOWN",
                )
                else "BULLISH_MSS"
            )

            events.append({
                "type": event_type,
                "timeframe": timeframe,
                "direction": "BULLISH",
                "index": i,
                "broken_pivot_index": swing_high["index"],
                "broken_level": swing_high["price"],
                "close": bar["close"],
            })

            broken_highs.add(
                swing_high["index"]
            )

            prior_state = "BULLISH"

        if bearish_break:
            event_type = (
                "BEARISH_BOS"
                if prior_state in (
                    "BEARISH",
                    "UNKNOWN",
                )
                else "BEARISH_MSS"
            )

            events.append({
                "type": event_type,
                "timeframe": timeframe,
                "direction": "BEARISH",
                "index": i,
                "broken_pivot_index": swing_low["index"],
                "broken_level": swing_low["price"],
                "close": bar["close"],
            })

            broken_lows.add(
                swing_low["index"]
            )

            prior_state = "BEARISH"

    latest = (
        events[-1]
        if events
        else None
    )

    return {
        "timeframe": timeframe,
        "state": prior_state,
        "pivot_high_count": len(highs),
        "pivot_low_count": len(lows),
        "events": events[-12:],
        "latest_event": latest,
    }


def detect_order_blocks(
    candles: list[dict[str, Any]],
    timeframe: str,
    structure: dict[str, Any],
) -> list[dict[str, Any]]:

    c = _clean(candles)
    result: list[dict[str, Any]] = []

    for event in structure.get(
        "events",
        [],
    ):

        break_index = int(
            event["index"]
        )

        direction = event[
            "direction"
        ]

        if break_index <= 0:
            continue

        search_start = max(
            0,
            break_index - 8,
        )

        selected = None

        for i in range(
            break_index - 1,
            search_start - 1,
            -1,
        ):

            bar = c[i]

            bearish_candle = (
                bar["close"]
                < bar["open"]
            )

            bullish_candle = (
                bar["close"]
                > bar["open"]
            )

            if (
                direction == "BULLISH"
                and bearish_candle
            ):
                selected = (i, bar)
                break

            if (
                direction == "BEARISH"
                and bullish_candle
            ):
                selected = (i, bar)
                break

        if selected is None:
            continue

        index, bar = selected

        ob_low = bar["low"]
        ob_high = bar["high"]

        mitigated = False
        invalidated = False
        first_mitigation_index = None
        invalidation_index = None

        for j in range(
            break_index + 1,
            len(c),
        ):

            later = c[j]

            touched = (
                later["high"] >= ob_low
                and later["low"] <= ob_high
            )

            if (
                touched
                and not mitigated
            ):
                mitigated = True
                first_mitigation_index = j

            if (
                direction == "BULLISH"
                and later["close"] < ob_low
                and invalidation_index is None
            ):
                invalidated = True
                invalidation_index = j

            if (
                direction == "BEARISH"
                and later["close"] > ob_high
                and invalidation_index is None
            ):
                invalidated = True
                invalidation_index = j

        result.append({
            "type": (
                "BULLISH_OB"
                if direction == "BULLISH"
                else "BEARISH_OB"
            ),
            "timeframe": timeframe,
            "direction": direction,
            "index": index,
            "low": ob_low,
            "high": ob_high,
            "mid": (
                ob_low + ob_high
            ) / 2.0,
            "source_structure_event": event["type"],
            "break_index": break_index,
            "mitigated": mitigated,
            "first_mitigation_index": first_mitigation_index,
            "invalidated": invalidated,
            "invalidation_index": invalidation_index,
            "active": not invalidated,
        })

    return result[-10:]


def detect_breakers(
    candles: list[dict[str, Any]],
    order_blocks: list[dict[str, Any]],
) -> list[dict[str, Any]]:

    c = _clean(candles)

    breakers: list[dict[str, Any]] = []

    for ob in order_blocks:

        if not ob.get(
            "invalidated"
        ):
            continue

        activation_index = ob.get(
            "invalidation_index"
        )

        if activation_index is None:
            continue

        activation_index = int(
            activation_index
        )

        original_direction = ob[
            "direction"
        ]

        breaker_direction = (
            "BEARISH"
            if original_direction == "BULLISH"
            else "BULLISH"
        )

        low = float(
            ob["low"]
        )

        high = float(
            ob["high"]
        )

        mid = (
            low + high
        ) / 2.0

        retest_index = None
        confirmation_index = None
        rejection_index = None

        status = "UNTESTED"

        for i in range(
            activation_index + 1,
            len(c),
        ):

            bar = c[i]

            touched = (
                bar["high"] >= low
                and bar["low"] <= high
            )

            if (
                touched
                and retest_index is None
            ):
                retest_index = i

            if retest_index is None:
                continue

            if breaker_direction == "BEARISH":

                rejected = (
                    bar["close"] > high
                )

                confirmed = (
                    bar["close"] < mid
                    and bar["close"] < bar["open"]
                )

            else:

                rejected = (
                    bar["close"] < low
                )

                confirmed = (
                    bar["close"] > mid
                    and bar["close"] > bar["open"]
                )

            if rejected:
                status = "REJECTED"
                rejection_index = i
                break

            if confirmed:
                status = "CONFIRMED"
                confirmation_index = i
                break

            status = "TESTED_UNCONFIRMED"

        bars_since_activation = max(
            0,
            len(c)
            - 1
            - activation_index,
        )

        bars_since_retest = (
            max(
                0,
                len(c)
                - 1
                - retest_index,
            )
            if retest_index is not None
            else None
        )

        source_event_tier = ob.get(
            "source_event_quality_tier",
            "LOW",
        )

        source_event_score = float(
            ob.get(
                "quality_score",
                0.0,
            )
        )

        decision_eligible = (
            status == "CONFIRMED"
            and source_event_tier
            in (
                "HIGH",
                "MEDIUM",
            )
        )

        breakers.append({
            "type": (
                "BEARISH_BREAKER"
                if breaker_direction == "BEARISH"
                else "BULLISH_BREAKER"
            ),
            "timeframe": ob[
                "timeframe"
            ],
            "direction": breaker_direction,
            "low": low,
            "high": high,
            "mid": mid,
            "source_order_block": ob[
                "type"
            ],
            "source_index": ob[
                "index"
            ],
            "activation_index": activation_index,
            "retest_index": retest_index,
            "confirmation_index": confirmation_index,
            "rejection_index": rejection_index,
            "status": status,
            "bars_since_activation": bars_since_activation,
            "bars_since_retest": bars_since_retest,
            "source_event_quality_tier": source_event_tier,
            "source_event_quality_score": source_event_score,
            "decision_eligible": decision_eligible,
            "candidate_only": not decision_eligible,
        })

    return breakers[-10:]

def classify_fvg_lifecycle(
    candles: list[dict[str, Any]],
    fvgs: list[dict[str, Any]],
) -> list[dict[str, Any]]:

    c = _clean(candles)
    result: list[dict[str, Any]] = []

    for item in fvgs:

        fvg = dict(item)

        created_index = int(
            fvg["index"]
        )

        low = float(
            fvg["low"]
        )

        high = float(
            fvg["high"]
        )

        midpoint = (
            low + high
        ) / 2.0

        touched = False
        midpoint_mitigated = False
        fully_filled = False
        invalidated = False
        first_touch_index = None

        direction = (
            "BULLISH"
            if fvg["type"] == "BULLISH_FVG"
            else "BEARISH"
        )

        for i in range(
            created_index + 1,
            len(c),
        ):

            bar = c[i]

            overlaps = (
                bar["high"] >= low
                and bar["low"] <= high
            )

            if (
                overlaps
                and not touched
            ):
                touched = True
                first_touch_index = i

            if (
                bar["low"] <= midpoint
                <= bar["high"]
            ):
                midpoint_mitigated = True

            if direction == "BULLISH":

                if bar["low"] <= low:
                    fully_filled = True

                if bar["close"] < low:
                    invalidated = True

            else:

                if bar["high"] >= high:
                    fully_filled = True

                if bar["close"] > high:
                    invalidated = True

        if invalidated:
            status = "INVALIDATED"

        elif fully_filled:
            status = "FILLED"

        elif midpoint_mitigated:
            status = "MIDPOINT_MITIGATED"

        elif touched:
            status = "PARTIALLY_MITIGATED"

        else:
            status = "UNMITIGATED"

        fvg.update({
            "direction": direction,
            "status": status,
            "touched": touched,
            "midpoint_mitigated": midpoint_mitigated,
            "fully_filled": fully_filled,
            "invalidated": invalidated,
            "first_touch_index": first_touch_index,
        })

        result.append(fvg)

    return result



def _quality_thresholds(
    timeframe: str,
) -> dict[str, float]:

    tf = str(
        timeframe
    ).upper()

    policies = {
        "M1": {
            "structure_body": 0.45,
            "structure_break": 0.10,
            "fvg_gap": 0.15,
            "high_recent_bars": 20,
            "medium_recent_bars": 45,
        },
        "M5": {
            "structure_body": 0.50,
            "structure_break": 0.10,
            "fvg_gap": 0.12,
            "high_recent_bars": 18,
            "medium_recent_bars": 40,
        },
        "M15": {
            "structure_body": 0.50,
            "structure_break": 0.10,
            "fvg_gap": 0.10,
            "high_recent_bars": 16,
            "medium_recent_bars": 36,
        },
        "H1": {
            "structure_body": 0.45,
            "structure_break": 0.08,
            "fvg_gap": 0.08,
            "high_recent_bars": 14,
            "medium_recent_bars": 30,
        },
        "H4": {
            "structure_body": 0.40,
            "structure_break": 0.07,
            "fvg_gap": 0.07,
            "high_recent_bars": 12,
            "medium_recent_bars": 24,
        },
    }

    return policies.get(
        tf,
        policies["M15"],
    )


def _recency_tier(
    *,
    index: int,
    candle_count: int,
    high_recent_bars: int,
    medium_recent_bars: int,
) -> tuple[str, int, float]:

    bars_ago = max(
        0,
        candle_count - 1 - index,
    )

    if bars_ago <= high_recent_bars:
        return (
            "RECENT",
            bars_ago,
            1.0,
        )

    if bars_ago <= medium_recent_bars:
        return (
            "AGING",
            bars_ago,
            0.70,
        )

    return (
        "STALE",
        bars_ago,
        0.35,
    )


def qualify_structure_events(
    candles: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:

    c = _clean(candles)
    atr = _atr(c)

    result: list[dict[str, Any]] = []

    if atr <= 0:
        return result

    for event in events:

        index = int(
            event["index"]
        )

        if (
            index < 0
            or index >= len(c)
        ):
            continue

        timeframe = str(
            event.get(
                "timeframe",
                "M15",
            )
        ).upper()

        policy = _quality_thresholds(
            timeframe
        )

        bar = c[index]

        body = abs(
            bar["close"]
            - bar["open"]
        )

        broken_level = float(
            event["broken_level"]
        )

        close = float(
            bar["close"]
        )

        break_distance = abs(
            close - broken_level
        )

        body_atr_ratio = (
            body / atr
        )

        break_atr_ratio = (
            break_distance / atr
        )

        direction = event[
            "direction"
        ]

        correct_close_side = (
            (
                direction == "BULLISH"
                and close > broken_level
            )
            or
            (
                direction == "BEARISH"
                and close < broken_level
            )
        )

        recency, bars_ago, recency_factor = (
            _recency_tier(
                index=index,
                candle_count=len(c),
                high_recent_bars=int(
                    policy[
                        "high_recent_bars"
                    ]
                ),
                medium_recent_bars=int(
                    policy[
                        "medium_recent_bars"
                    ]
                ),
            )
        )

        body_score = min(
            1.0,
            body_atr_ratio
            / max(
                policy[
                    "structure_body"
                ],
                0.0001,
            ),
        )

        break_score = min(
            1.0,
            break_atr_ratio
            / max(
                policy[
                    "structure_break"
                ],
                0.0001,
            ),
        )

        quality_score = (
            body_score * 0.45
            + break_score * 0.35
            + recency_factor * 0.20
        ) * 100.0

        hard_pass = (
            correct_close_side
            and body_atr_ratio
            >= policy[
                "structure_body"
            ]
            and break_atr_ratio
            >= policy[
                "structure_break"
            ]
        )

        if (
            hard_pass
            and quality_score >= 85
            and recency != "STALE"
        ):
            quality_tier = "HIGH"

        elif (
            correct_close_side
            and quality_score >= 65
        ):
            quality_tier = "MEDIUM"

        else:
            quality_tier = "LOW"

        qualified = (
            quality_tier
            in (
                "HIGH",
                "MEDIUM",
            )
        )

        reasons = []

        if not correct_close_side:
            reasons.append(
                "close_not_beyond_structure"
            )

        if (
            body_atr_ratio
            < policy[
                "structure_body"
            ]
        ):
            reasons.append(
                "weak_body_vs_atr"
            )

        if (
            break_atr_ratio
            < policy[
                "structure_break"
            ]
        ):
            reasons.append(
                "shallow_break_vs_atr"
            )

        if recency == "STALE":
            reasons.append(
                "stale_structure_event"
            )

        item = dict(event)

        item.update({
            "qualified": qualified,
            "quality_tier": quality_tier,
            "quality_score": round(
                quality_score,
                2,
            ),
            "body_atr_ratio": round(
                body_atr_ratio,
                4,
            ),
            "break_atr_ratio": round(
                break_atr_ratio,
                4,
            ),
            "recency": recency,
            "bars_ago": bars_ago,
            "qualification_reasons": reasons,
            "quality_policy": policy,
        })

        result.append(item)

    return result


def qualify_fvgs(
    candles: list[dict[str, Any]],
    fvgs: list[dict[str, Any]],
) -> list[dict[str, Any]]:

    c = _clean(candles)
    atr = _atr(c)

    result: list[dict[str, Any]] = []

    if atr <= 0:
        return result

    for fvg in fvgs:

        timeframe = str(
            fvg.get(
                "timeframe",
                "M15",
            )
        ).upper()

        policy = _quality_thresholds(
            timeframe
        )

        low = float(
            fvg["low"]
        )

        high = float(
            fvg["high"]
        )

        gap_size = max(
            0.0,
            high - low,
        )

        gap_atr_ratio = (
            gap_size / atr
        )

        index = int(
            fvg["index"]
        )

        recency, bars_ago, recency_factor = (
            _recency_tier(
                index=index,
                candle_count=len(c),
                high_recent_bars=int(
                    policy[
                        "high_recent_bars"
                    ]
                ),
                medium_recent_bars=int(
                    policy[
                        "medium_recent_bars"
                    ]
                ),
            )
        )

        gap_score = min(
            1.0,
            gap_atr_ratio
            / max(
                policy[
                    "fvg_gap"
                ],
                0.0001,
            ),
        )

        lifecycle = str(
            fvg.get(
                "status",
                "UNKNOWN",
            )
        )

        lifecycle_factor = (
            1.0
            if lifecycle
            in (
                "UNMITIGATED",
                "PARTIALLY_MITIGATED",
            )
            else (
                0.75
                if lifecycle
                == "MIDPOINT_MITIGATED"
                else 0.30
            )
        )

        quality_score = (
            gap_score * 0.55
            + recency_factor * 0.25
            + lifecycle_factor * 0.20
        ) * 100.0

        hard_gap_pass = (
            gap_atr_ratio
            >= policy[
                "fvg_gap"
            ]
        )

        active_lifecycle = (
            lifecycle
            in (
                "UNMITIGATED",
                "PARTIALLY_MITIGATED",
                "MIDPOINT_MITIGATED",
            )
        )

        if (
            hard_gap_pass
            and active_lifecycle
            and recency != "STALE"
            and quality_score >= 80
        ):
            quality_tier = "HIGH"

        elif (
            active_lifecycle
            and quality_score >= 60
        ):
            quality_tier = "MEDIUM"

        else:
            quality_tier = "LOW"

        qualified = (
            quality_tier
            in (
                "HIGH",
                "MEDIUM",
            )
        )

        item = dict(fvg)

        item.update({
            "gap_size": gap_size,
            "gap_atr_ratio": round(
                gap_atr_ratio,
                4,
            ),
            "qualified": qualified,
            "quality_tier": quality_tier,
            "quality_score": round(
                quality_score,
                2,
            ),
            "recency": recency,
            "bars_ago": bars_ago,
            "noise_flag": (
                quality_tier == "LOW"
            ),
            "quality_policy": policy,
        })

        result.append(item)

    return result


def qualify_order_blocks(
    order_blocks: list[dict[str, Any]],
    qualified_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:

    event_map = {
        (
            item["type"],
            int(item["index"]),
        ): item
        for item in qualified_events
    }

    result = []

    for ob in order_blocks:

        source_key = (
            ob[
                "source_structure_event"
            ],
            int(
                ob["break_index"]
            ),
        )

        source_event = event_map.get(
            source_key
        )

        event_qualified = bool(
            source_event
            and source_event.get(
                "qualified"
            )
        )

        event_quality_tier = (
            source_event.get(
                "quality_tier"
            )
            if source_event
            else "LOW"
        )

        event_quality_score = (
            float(
                source_event.get(
                    "quality_score",
                    0.0,
                )
            )
            if source_event
            else 0.0
        )

        if ob.get(
            "invalidated"
        ):
            freshness = "INVALIDATED"

        elif ob.get(
            "mitigated"
        ):
            freshness = "MITIGATED"

        else:
            freshness = "FRESH"

        freshness_factor = {
            "FRESH": 1.0,
            "MITIGATED": 0.65,
            "INVALIDATED": 0.0,
        }[
            freshness
        ]

        quality_score = (
            event_quality_score
            * freshness_factor
        )

        if (
            event_quality_tier == "HIGH"
            and freshness == "FRESH"
            and quality_score >= 80
        ):
            quality_tier = "HIGH"

        elif (
            event_qualified
            and freshness
            != "INVALIDATED"
            and quality_score >= 55
        ):
            quality_tier = "MEDIUM"

        else:
            quality_tier = "LOW"

        item = dict(ob)

        item.update({
            "source_event_qualified": event_qualified,
            "source_event_quality_tier": event_quality_tier,
            "freshness": freshness,
            "quality_score": round(
                quality_score,
                2,
            ),
            "quality_tier": quality_tier,
            "qualified": (
                quality_tier
                in (
                    "HIGH",
                    "MEDIUM",
                )
            ),
        })

        result.append(item)

    return result

def build_advanced_ict_structure(
    candles: list[dict[str, Any]],
    timeframe: str,
) -> dict[str, Any]:

    structure = detect_structure_events(
        candles,
        timeframe,
    )

    qualified_structure_events = (
        qualify_structure_events(
            candles,
            structure[
                "events"
            ],
        )
    )

    fvgs = detect_fvgs(
        candles,
        timeframe,
    )

    fvg_lifecycle = classify_fvg_lifecycle(
        candles,
        fvgs,
    )

    qualified_fvg_lifecycle = (
        qualify_fvgs(
            candles,
            fvg_lifecycle,
        )
    )

    order_blocks = detect_order_blocks(
        candles,
        timeframe,
        structure,
    )

    qualified_order_blocks = (
        qualify_order_blocks(
            order_blocks,
            qualified_structure_events,
        )
    )

    breakers = detect_breakers(
        candles,
        qualified_order_blocks,
    )

    active_fvgs = [
        item
        for item in qualified_fvg_lifecycle
        if item["status"] in (
            "UNMITIGATED",
            "PARTIALLY_MITIGATED",
            "MIDPOINT_MITIGATED",
        )
    ]

    qualified_active_fvgs = [
        item
        for item in active_fvgs
        if item.get(
            "qualified"
        )
    ]

    active_order_blocks = [
        item
        for item in qualified_order_blocks
        if item["active"]
    ]

    qualified_active_order_blocks = [
        item
        for item in active_order_blocks
        if item.get(
            "qualified"
        )
    ]

    qualified_events_only = [
        item
        for item in qualified_structure_events
        if item.get(
            "qualified"
        )
    ]

    return {
        "structure": structure,
        "qualified_structure_events": qualified_events_only[-12:],
        "structure_events_with_quality": qualified_structure_events[-12:],

        "order_blocks": qualified_order_blocks,
        "active_order_blocks": active_order_blocks[-6:],
        "qualified_active_order_blocks": qualified_active_order_blocks[-6:],

        "breakers": breakers,

        "fvg_lifecycle": qualified_fvg_lifecycle[-20:],
        "active_fvgs": active_fvgs[-10:],
        "qualified_active_fvgs": qualified_active_fvgs[-10:],

        "quality_policy": {
            "adaptive_by_timeframe": True,
            "recency_weighted": True,
            "quality_tiers": [
                "HIGH",
                "MEDIUM",
                "LOW",
            ],
            "breaker_requires_retest_confirmation": True,
        },
    }

def analyze_ict_timeframe(
    candles: list[dict[str, Any]],
    timeframe: str,
    *,
    weight: float = 1.0,
    role: str = "CONTEXT",
) -> dict[str, Any]:

    advanced = build_advanced_ict_structure(
        candles,
        timeframe,
    )

    return {
        "timeframe": timeframe,
        "weight": float(weight),
        "role": role,
        "displacement": detect_displacement(
            candles,
            timeframe,
        ),
        "fvg": detect_fvgs(
            candles,
            timeframe,
        )[-12:],
        "liquidity": detect_equal_highs_lows(
            candles,
            timeframe,
        ),
        "liquidity_pools": build_liquidity_pools(
            candles,
            timeframe,
        ),
        "sweeps": detect_liquidity_sweeps(
            candles,
            timeframe,
        )[-10:],
        "advanced_structure": advanced,
    }



def build_decision_evidence(
    *,
    analysis: dict[str, Any],
    candles_by_timeframe: dict[str, Any],
    trade_mode: str,
) -> dict[str, Any]:

    mode = normalize_trade_mode(
        trade_mode
    )

    mode_policy = {
        "FAST_SCALP": {
            "M15": 24,
            "M5": 24,
            "M1": 20,
        },
        "INTRADAY": {
            "H1": 24,
            "M15": 32,
            "M5": 36,
        },
        "SWING": {
            "H4": 20,
            "H1": 30,
            "M15": 40,
        },
    }

    max_bars = mode_policy[
        mode
    ]

    result: dict[str, Any] = {}

    for timeframe, limit in (
        max_bars.items()
    ):

        item = analysis.get(
            timeframe
        )

        if not item:
            continue

        advanced = item.get(
            "advanced_structure",
            {},
        )

        candles = (
            candles_by_timeframe.get(
                timeframe,
                [],
            )
        )

        candle_count = len(
            candles
        )

        structure_events = []

        for event in advanced.get(
            "structure_events_with_quality",
            [],
        ):

            tier = event.get(
                "quality_tier"
            )

            bars_ago = int(
                event.get(
                    "bars_ago",
                    999999,
                )
            )

            policy = event.get(
                "quality_policy",
                {},
            )

            body_ok = (
                float(
                    event.get(
                        "body_atr_ratio",
                        0.0,
                    )
                )
                >= float(
                    policy.get(
                        "structure_body",
                        999999.0,
                    )
                )
            )

            break_ok = (
                float(
                    event.get(
                        "break_atr_ratio",
                        0.0,
                    )
                )
                >= float(
                    policy.get(
                        "structure_break",
                        999999.0,
                    )
                )
            )

            if (
                tier in (
                    "HIGH",
                    "MEDIUM",
                )
                and bars_ago <= limit
                and body_ok
                and break_ok
            ):
                structure_events.append(
                    event
                )

        active_fvgs = []

        for fvg in advanced.get(
            "active_fvgs",
            [],
        ):

            tier = fvg.get(
                "quality_tier"
            )

            bars_ago = int(
                fvg.get(
                    "bars_ago",
                    999999,
                )
            )

            policy = fvg.get(
                "quality_policy",
                {},
            )

            gap_ok = (
                float(
                    fvg.get(
                        "gap_atr_ratio",
                        0.0,
                    )
                )
                >= float(
                    policy.get(
                        "fvg_gap",
                        999999.0,
                    )
                )
            )

            active_status = (
                fvg.get(
                    "status"
                )
                in (
                    "UNMITIGATED",
                    "PARTIALLY_MITIGATED",
                    "MIDPOINT_MITIGATED",
                )
            )

            if (
                tier in (
                    "HIGH",
                    "MEDIUM",
                )
                and bars_ago <= limit
                and gap_ok
                and active_status
            ):
                active_fvgs.append(
                    fvg
                )

        confirmed_breakers = []

        for breaker in advanced.get(
            "breakers",
            [],
        ):

            if not breaker.get(
                "decision_eligible"
            ):
                continue

            activation_index = int(
                breaker.get(
                    "activation_index",
                    -1,
                )
            )

            bars_ago = (
                max(
                    0,
                    candle_count
                    - 1
                    - activation_index,
                )
                if activation_index >= 0
                else 999999
            )

            if bars_ago > limit:
                continue

            enriched_breaker = dict(
                breaker
            )

            enriched_breaker[
                "bars_ago"
            ] = bars_ago

            confirmed_breakers.append(
                enriched_breaker
            )

        active_obs = []

        for ob in advanced.get(
            "order_blocks",
            [],
        ):

            tier = ob.get(
                "quality_tier"
            )

            break_index = int(
                ob.get(
                    "break_index",
                    -1,
                )
            )

            bars_ago = (
                max(
                    0,
                    candle_count
                    - 1
                    - break_index,
                )
                if break_index >= 0
                else 999999
            )

            freshness = ob.get(
                "freshness"
            )

            if (
                tier in (
                    "HIGH",
                    "MEDIUM",
                )
                and bars_ago <= limit
                and freshness
                in (
                    "FRESH",
                    "MITIGATED",
                )
            ):
                enriched = dict(
                    ob
                )

                enriched[
                    "bars_ago"
                ] = bars_ago

                active_obs.append(
                    enriched
                )

        result[
            timeframe
        ] = {
            "role": item.get(
                "role"
            ),
            "weight": item.get(
                "weight"
            ),
            "max_decision_bars": limit,
            "displacement": item.get(
                "displacement"
            ),
            "structure_events": (
                structure_events[-5:]
            ),
            "active_fvgs": (
                active_fvgs[-5:]
            ),
            "active_order_blocks": (
                active_obs[-5:]
            ),
            "confirmed_breakers": (
                confirmed_breakers[-5:]
            ),
        }

    return {
        "trade_mode": mode,
        "policy": {
            "raw_evidence_is_decision_grade": False,
            "low_quality_allowed": False,
            "stale_evidence_allowed": False,
            "hard_structure_threshold_required": True,
            "hard_fvg_gap_threshold_required": True,
            "breaker_evidence_enabled": True,
            "breaker_requires_status": "CONFIRMED",
            "breaker_requires_post_invalidation_retest": True,
            "breaker_rejected_is_decision_grade": False,
            "breaker_untested_is_decision_grade": False,
        },
        "timeframes": result,
    }

def build_ict_analysis(
    snapshot: dict[str, Any],
    *,
    trade_mode: str = "INTRADAY",
) -> dict[str, Any]:

    mode = normalize_trade_mode(
        trade_mode
    )

    series = snapshot.get(
        "candles",
        {},
    )

    weights = MODE_TIMEFRAME_WEIGHTS[
        mode
    ]

    roles = MODE_TIMEFRAME_ROLES[
        mode
    ]

    analysis: dict[str, Any] = {}

    for timeframe in (
        "D1",
        "H4",
        "H1",
        "M15",
        "M5",
        "M1",
    ):

        candles = series.get(
            timeframe,
            [],
        )

        if not candles:
            continue

        analysis[
            timeframe
        ] = analyze_ict_timeframe(
            candles,
            timeframe,
            weight=weights.get(
                timeframe,
                0.0,
            ),
            role=roles.get(
                timeframe,
                "CONTEXT",
            ),
        )

    d1 = series.get(
        "D1",
        [],
    )

    daily_quadrant = (
        detect_daily_quadrant(d1)
        if d1
        else None
    )

    decision_evidence = build_decision_evidence(
        analysis=analysis,
        candles_by_timeframe=series,
        trade_mode=mode,
    )

    return {
        "ict_engine_version": ICT_ENGINE_VERSION,
        "trade_mode": mode,
        "timeframe_weights": weights,
        "timeframe_roles": roles,
        "timeframes": analysis,
        "decision_evidence": decision_evidence,
        "daily_quadrant": daily_quadrant,
        "mode_policy": {
            "htf_conflict_is_veto": (
                False
                if mode == "FAST_SCALP"
                else True
            ),
            "primary_setup_timeframe": (
                "M5"
                if mode == "FAST_SCALP"
                else (
                    "M15"
                    if mode == "INTRADAY"
                    else "H1"
                )
            ),
            "primary_trigger_timeframe": (
                "M1"
                if mode == "FAST_SCALP"
                else (
                    "M5"
                    if mode == "INTRADAY"
                    else "M15"
                )
            ),
        },
        "advisory_only": True,
        "execution_gate": False,
    }
