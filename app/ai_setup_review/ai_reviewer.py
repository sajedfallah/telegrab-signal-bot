from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import httpx

from .review_payload import build_setup_review_payload


REVIEWER_VERSION = "ai-setup-reviewer-v1"
PROMPT_VERSION = "ai-setup-review-prompt-v1"


def _load_secret_config() -> dict[str, str]:
    path = Path(
        ".secrets/ai_setup_reviewer.env"
    )

    if not path.exists():
        raise RuntimeError(
            "AI reviewer secret file missing"
        )

    cfg: dict[str, str] = {}

    for raw in path.read_text(
        encoding="utf-8",
        errors="strict",
    ).splitlines():

        line = raw.strip()

        if (
            not line
            or line.startswith("#")
            or "=" not in line
        ):
            continue

        key, value = line.split(
            "=",
            1,
        )

        cfg[
            key.strip()
        ] = value.strip()

    required = (
        "AI_REVIEWER_API_KEY",
        "AI_REVIEWER_BASE_URL",
        "AI_REVIEWER_MODEL",
    )

    for name in required:
        if not cfg.get(name):
            raise RuntimeError(
                "missing reviewer config: "
                + name
            )

    return cfg


def _allowed_prices(
    payload: dict[str, Any],
) -> set[float]:

    values: set[float] = set()

    market = payload["market"]

    for key in (
        "bid",
        "ask",
    ):
        value = market.get(key)

        if value is not None:
            values.add(
                round(float(value), 8)
            )

    numeric = payload[
        "numeric_analysis"
    ]

    key_levels = numeric[
        "key_levels"
    ]

    for key in (
        "nearest_support",
        "nearest_resistance",
        "sweep_low",
        "sweep_high",
    ):
        value = key_levels.get(key)

        if value is not None:
            values.add(
                round(float(value), 8)
            )

    setup = numeric[
        "suggested_setup"
    ]

    zone = setup[
        "preferred_entry_zone"
    ]

    for value in (
        zone.get("low"),
        zone.get("high"),
        setup.get("best_entry"),
        setup.get("structural_stop_loss"),
        setup.get("invalidation"),
        setup.get("wait_for_sweep_level"),
        setup.get("tp1"),
        setup.get("tp2"),
        setup.get("tp3"),
    ):
        if value is not None:
            values.add(
                round(float(value), 8)
            )

    for item in setup.get(
        "ranked_target_candidates",
        [],
    ):
        value = item.get("price")

        if value is not None:
            values.add(
                round(float(value), 8)
            )

    return values


def _price_is_allowed(
    value: Any,
    allowed: set[float],
) -> bool:

    if value is None:
        return True

    try:
        numeric = round(
            float(value),
            8,
        )
    except Exception:
        return False

    return numeric in allowed


def _validate_review(
    *,
    review: dict[str, Any],
    payload: dict[str, Any],
) -> None:

    allowed_statuses = {
        "WAIT",
        "CANDIDATE_OK",
        "CONTEXT_CONFLICT",
    }

    status = review.get(
        "status"
    )

    if status not in allowed_statuses:
        raise RuntimeError(
            "invalid AI review status: "
            + str(status)
        )

    expected_direction = payload[
        "setup_alignment"
    ]["direction"]

    if review.get(
        "direction"
    ) != expected_direction:
        raise RuntimeError(
            "AI changed requested direction"
        )

    allowed = _allowed_prices(
        payload
    )

    selected = review.get(
        "selected_setup",
        {},
    )

    price_fields = (
        "preferred_entry",
        "stop_loss",
        "tp1",
        "tp2",
        "tp3",
        "sweep_level",
        "invalidation",
    )

    for field in price_fields:
        value = selected.get(
            field
        )

        if not _price_is_allowed(
            value,
            allowed,
        ):
            raise RuntimeError(
                "AI invented unsupported price "
                + field
                + "="
                + str(value)
            )

    confidence = review.get(
        "confidence"
    )

    if not isinstance(
        confidence,
        (int, float),
    ):
        raise RuntimeError(
            "confidence must be numeric"
        )

    if (
        float(confidence) < 0
        or float(confidence) > 100
    ):
        raise RuntimeError(
            "confidence outside 0..100"
        )

    reasons = review.get(
        "reasons"
    )

    if not isinstance(
        reasons,
        list,
    ):
        raise RuntimeError(
            "reasons must be a list"
        )

    risks = review.get(
        "risks"
    )

    if not isinstance(
        risks,
        list,
    ):
        raise RuntimeError(
            "risks must be a list"
        )


def _extract_output_text(
    data: dict[str, Any],
) -> str:

    direct = data.get(
        "output_text"
    )

    if direct:
        return str(direct)

    pieces: list[str] = []

    for item in data.get(
        "output",
        [],
    ):
        for content in item.get(
            "content",
            [],
        ):
            text = content.get(
                "text"
            )

            if text:
                pieces.append(
                    str(text)
                )

    return "".join(
        pieces
    )


def review_setup(
    *,
    symbol: str,
    direction: str,
    trade_mode: str = "INTRADAY",
) -> dict[str, Any]:

    payload = build_setup_review_payload(
        symbol=symbol,
        direction=direction,
        user_entry=None,
        user_stop_loss=None,
        user_targets=[],
        candle_limit=200,
        trade_mode=trade_mode,
    )

    cfg = _load_secret_config()

    setup = payload[
        "numeric_analysis"
    ]["suggested_setup"]

    allowed_prices = sorted(
        _allowed_prices(
            payload
        )
    )

    market_context_for_ai = dict(
        payload["market_context"]
    )

    full_ict_analysis = (
        market_context_for_ai.pop(
            "ict_analysis",
            {},
        )
    )

    ict_decision_evidence = (
        full_ict_analysis.get(
            "decision_evidence",
            {},
        )
    )

    market_context_for_ai[
        "ict_decision_evidence"
    ] = ict_decision_evidence

    ai_input = {
        "trade_mode": payload[
            "trade_mode"
        ],
        "symbol": payload[
            "market"
        ]["symbol"],
        "market": payload[
            "market"
        ],
        "data_quality": payload[
            "data_quality"
        ],
        "market_context": market_context_for_ai,
        "ict_decision_evidence": ict_decision_evidence,
        "setup_alignment": payload[
            "setup_alignment"
        ],
        "candidate_setup": setup,
        "key_levels": payload[
            "numeric_analysis"
        ]["key_levels"],
        "allowed_prices": allowed_prices,
    }

    system_prompt = """
You are the advisory NEXUS AI Setup Reviewer.

You review deterministic market-analysis output.
You do NOT execute trades.
You do NOT block manual execution.
You do NOT invent prices.

All price fields in your JSON response MUST be either:
1. an exact numeric value already present in allowed_prices, or
2. null.

Do not calculate a new entry, stop loss, target, sweep,
invalidation, midpoint, average, projection, or derived price.

Evaluate the requested direction using the supplied trade_mode.

Trade mode hierarchy:

SWING:
- D1/H4 are primary context when supplied.
- H1 is setup context.
- M15 is entry refinement.

INTRADAY:
- H4/H1 are primary context.
- M15 is setup context.
- M5 is trigger context.

FAST_SCALP:
- H4 and H1 are BACKGROUND/RISK context only.
- M15 defines local bias.
- M5 is the PRIMARY SETUP timeframe.
- M1 is the PRIMARY TRIGGER timeframe.
- H1 or H4 opposing direction MUST NOT by itself produce CONTEXT_CONFLICT.
- A counter-trend fast scalp may still be valid when M5 setup and M1 trigger are strong.
- Report HTF disagreement as a risk.
- Prefer WAIT when the M1 trigger is absent or inadequate.
- Use CONTEXT_CONFLICT for FAST_SCALP only when the LOCAL M15/M5/M1 evidence materially invalidates the requested direction.

Evidence policy:
- ict_decision_evidence is the ONLY decision-grade advanced ICT evidence.
- Do not treat omitted raw ICT events as confirmation.
- Do not promote LOW-quality or stale evidence into a trade thesis.
- A price gap, structure event, or order block omitted from ict_decision_evidence must not be used as confirmation.
- Breakers are not decision-grade until retest confirmation is implemented.

Also evaluate:
- ICT liquidity context only when supplied as decision-grade evidence
- FVG evidence from ict_decision_evidence
- displacement
- equal highs/equal lows
- MTF alignment appropriate to trade_mode
- deterministic candidate setup
- risk/reward values
- data quality

Allowed status values:
WAIT
CANDIDATE_OK
CONTEXT_CONFLICT

Use CANDIDATE_OK only when the candidate is reasonably supported
by the supplied deterministic context.

Use CONTEXT_CONFLICT when the candidate direction materially conflicts
with the supplied structure/context.

Use WAIT when context is mixed, confirmation is inadequate,
or timing is poor.

Return ONLY valid JSON with this exact structure:

{
  "status": "WAIT|CANDIDATE_OK|CONTEXT_CONFLICT",
  "direction": "BUY|SELL",
  "confidence": 0,
  "selected_setup": {
    "preferred_entry": null,
    "stop_loss": null,
    "tp1": null,
    "tp2": null,
    "tp3": null,
    "sweep_level": null,
    "invalidation": null
  },
  "context_summary": {
    "h4": "",
    "h1": "",
    "m15": "",
    "m5": "",
    "m1": "",
    "mtf": ""
  },
  "reasons": [],
  "risks": [],
  "wait_for": []
}

Do not use markdown.
Do not include commentary outside JSON.
""".strip()

    user_prompt = (
        "Review this NEXUS deterministic setup payload.\n"
        + json.dumps(
            ai_input,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )

    endpoint = (
        cfg[
            "AI_REVIEWER_BASE_URL"
        ].rstrip("/")
        + "/responses"
    )

    request_payload = {
        "model": cfg[
            "AI_REVIEWER_MODEL"
        ],
        "input": [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": system_prompt,
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": user_prompt,
                    }
                ],
            },
        ],
        "max_output_tokens": 1200,
    }

    timeout = float(
        cfg.get(
            "AI_REVIEWER_TIMEOUT",
            "90",
        )
    )

    headers = {
        "Authorization": (
            "Bearer "
            + cfg[
                "AI_REVIEWER_API_KEY"
            ]
        ),
        "Content-Type": "application/json",
    }

    with httpx.Client(
        timeout=timeout,
    ) as client:

        response = client.post(
            endpoint,
            headers=headers,
            json=request_payload,
        )

    if response.status_code >= 400:
        raise RuntimeError(
            "AI reviewer HTTP "
            + str(
                response.status_code
            )
            + ": "
            + response.text[:500]
        )

    data = response.json()

    raw_text = _extract_output_text(
        data
    ).strip()

    raw_text = re.sub(
        r"^```(?:json)?\s*",
        "",
        raw_text,
        flags=re.IGNORECASE,
    )

    raw_text = re.sub(
        r"\s*```$",
        "",
        raw_text,
    )

    try:
        review = json.loads(
            raw_text
        )

    except Exception as exc:
        raise RuntimeError(
            "AI returned invalid JSON: "
            + str(exc)
            + " RAW="
            + raw_text[:1000]
        )

    _validate_review(
        review=review,
        payload=payload,
    )

    return {
        "reviewer_version": REVIEWER_VERSION,
        "prompt_version": PROMPT_VERSION,
        "provider": cfg.get(
            "AI_REVIEWER_PROVIDER",
            "openai",
        ),
        "model": cfg[
            "AI_REVIEWER_MODEL"
        ],
        "payload_version": payload[
            "payload_version"
        ],
        "engine_version": payload[
            "numeric_analysis"
        ]["engine_version"],
        "structure_version": payload[
            "market_context"
        ]["structure_version"],
        "data_quality": payload[
            "data_quality"
        ],
        "market": payload[
            "market"
        ],
        "setup_alignment": payload[
            "setup_alignment"
        ],
        "deterministic_setup": setup,
        "ai_review": review,
        "raw_ai_response": raw_text,
        "advisory_only": True,
        "execution_gate": False,
    }
