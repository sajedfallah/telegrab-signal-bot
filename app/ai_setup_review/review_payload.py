from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .level_engine import analyze_numeric_levels
from .market_snapshot import load_market_snapshot
from .ict_engine import build_ict_analysis, normalize_trade_mode
from .market_structure import analyze_market_structure


PAYLOAD_VERSION = "ai-setup-review-payload-v1"


def _now_iso() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def _quality_grade(
    *,
    quote_age: float | None,
    feed_age: float | None,
    required_timeframes_present: bool,
) -> tuple[str, list[str]]:

    reasons: list[str] = []

    if not required_timeframes_present:
        reasons.append(
            "required_timeframes_missing"
        )

    if quote_age is None:
        reasons.append(
            "quote_age_unknown"
        )
    elif quote_age > 30:
        reasons.append(
            "quote_stale"
        )

    if feed_age is None:
        reasons.append(
            "feed_age_unknown"
        )
    elif feed_age > 30:
        reasons.append(
            "feed_stale"
        )

    if reasons:
        return "UNUSABLE", reasons

    if quote_age <= 5 and feed_age <= 5:
        return "EXCELLENT", []

    if quote_age <= 15 and feed_age <= 15:
        return "GOOD", []

    return "ACCEPTABLE", []


def build_setup_review_payload(
    *,
    symbol: str,
    direction: str,
    user_entry: float | None = None,
    user_stop_loss: float | None = None,
    user_targets: list[float] | None = None,
    candle_limit: int = 200,
    trade_mode: str = "INTRADAY",
) -> dict[str, Any]:

    mode = normalize_trade_mode(
        trade_mode
    )

    required_timeframes = (
        (
            "H4",
            "H1",
            "M15",
            "M5",
            "M1",
        )
        if mode == "FAST_SCALP"
        else (
            "H4",
            "H1",
            "M15",
            "M5",
        )
    )

    snapshot = load_market_snapshot(
        symbol=symbol,
        timeframes=required_timeframes,
        candle_limit=candle_limit,
    )

    quote = snapshot["quote"]

    present = all(
        timeframe in snapshot["candles"]
        and len(snapshot["candles"][timeframe]) >= 20
        for timeframe in required_timeframes
    )

    quality_grade, quality_reasons = _quality_grade(
        quote_age=quote.get(
            "age_seconds"
        ),
        feed_age=snapshot.get(
            "max_feed_age_seconds"
        ),
        required_timeframes_present=present,
    )

    if quality_grade == "UNUSABLE":
        raise RuntimeError(
            "market data quality unusable: "
            + ",".join(quality_reasons)
        )

    digits = int(
        quote["digits"]
        if quote["digits"] is not None
        else 2
    )

    structure = analyze_market_structure(
        candles_by_timeframe=snapshot["candles"]
    )

    ict_analysis = build_ict_analysis(
        snapshot,
        trade_mode=mode,
    )

    levels = analyze_numeric_levels(
        symbol=snapshot["symbol"],
        direction=direction,
        bid=float(quote["bid"]),
        ask=float(quote["ask"]),
        digits=digits,
        candles_by_timeframe=snapshot["candles"],
        user_entry=user_entry,
        user_stop_loss=user_stop_loss,
        user_targets=user_targets,
    )

    tf_summary: dict[str, Any] = {}

    for timeframe in (
        "H4",
        "H1",
        "M15",
        "M5",
    ):
        item = structure["timeframes"][
            timeframe
        ]

        tf_summary[timeframe] = {
            "bias": item["bias"],
            "structure": item["structure"],
            "atr": round(
                float(item["atr"]),
                digits,
            ),
            "range_zone": item[
                "range"
            ]["zone"],
            "range_position": item[
                "range"
            ]["position"],
            "displacement": item[
                "displacement"
            ],
            "swing_evidence": item[
                "evidence"
            ],
        }

    setup = levels[
        "suggested_setup"
    ]

    user_setup = levels[
        "user_setup"
    ]

    alignment: dict[str, Any] = {
        "direction": str(
            direction
        ).upper(),
        "overall_bias": structure[
            "overall_bias"
        ],
        "weighted_bias_score": structure[
            "weighted_bias_score"
        ],
        "htf_alignment": structure[
            "htf_alignment"
        ],
        "ltf_alignment": structure[
            "ltf_alignment"
        ],
        "full_alignment": structure[
            "full_alignment"
        ],
    }

    requested_direction = str(
        direction
    ).upper()

    if structure["overall_bias"] == "MIXED":
        alignment[
            "direction_vs_context"
        ] = "MIXED_CONTEXT"

    elif (
        requested_direction
        == structure["overall_bias"]
    ):
        alignment[
            "direction_vs_context"
        ] = "ALIGNED"

    else:
        alignment[
            "direction_vs_context"
        ] = "COUNTER_CONTEXT"

    return {
        "payload_version": PAYLOAD_VERSION,
        "created_at": _now_iso(),
        "trade_mode": mode,
        "advisory_only": True,
        "execution_gate": False,

        "market": {
            "symbol": snapshot["symbol"],
            "broker_symbol": quote[
                "broker_symbol"
            ],
            "account_number": snapshot[
                "account_number"
            ],
            "source": snapshot[
                "source"
            ],
            "bid": quote["bid"],
            "ask": quote["ask"],
            "digits": digits,
            "quote_age_seconds": quote[
                "age_seconds"
            ],
            "max_feed_age_seconds": snapshot[
                "max_feed_age_seconds"
            ],
        },

        "data_quality": {
            "grade": quality_grade,
            "reasons": quality_reasons,
            "required_timeframes": list(
                required_timeframes
            ),
            "required_timeframes_present": present,
        },

        "market_context": {
            "structure_version": structure[
                "structure_version"
            ],
            "overall_bias": structure[
                "overall_bias"
            ],
            "weighted_bias_score": structure[
                "weighted_bias_score"
            ],
            "htf_alignment": structure[
                "htf_alignment"
            ],
            "ltf_alignment": structure[
                "ltf_alignment"
            ],
            "full_alignment": structure[
                "full_alignment"
            ],
            "timeframes": tf_summary,
            "ict_analysis": ict_analysis,
            "trade_mode": mode,
            "mode_policy": ict_analysis[
                "mode_policy"
            ],
        },

        "numeric_analysis": {
            "engine_version": levels[
                "engine_version"
            ],
            "market": levels[
                "market"
            ],
            "atr": levels[
                "atr"
            ],
            "key_levels": levels[
                "key_levels"
            ],
            "suggested_setup": setup,
        },

        "user_setup": user_setup,

        "setup_alignment": alignment,

        "review_contract": {
            "ai_must_not_invent_prices": True,
            "ai_must_reference_numeric_analysis": True,
            "ai_must_reference_market_context": True,
            "ai_may_recommend_wait": True,
            "ai_may_not_execute_trade": True,
            "ai_may_not_block_manual_execution": True,
            "fast_scalp_htf_conflict_is_not_automatic_rejection": True,
        },
    }
