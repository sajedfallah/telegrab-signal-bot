from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Mapping


def explain_ict_analysis(record: Mapping[str, object]) -> str | None:
    """Optional, non-executing AI commentary; the deterministic report remains authoritative."""
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key or os.environ.get("NEXUS_AGENT_AI_ENABLED", "false").lower() != "true":
        return None
    assessment = next((a for a in (record.get("assessments") or [])
                       if isinstance(a, Mapping) and str(a.get("agent", "")).startswith("nexus-ict")), {})
    payload = {
        "symbol": record.get("symbol"),
        "timeframe": record.get("analysis_timeframe"),
        "snapshot_id": record.get("snapshot_id"),
        "bid": record.get("bid"),
        "ask": record.get("ask"),
        "ict_direction": record.get("direction"),
        "ict_evidence": list(assessment.get("evidence", []))[:30],
        "ict_invalidations": list(assessment.get("invalidation", []))[:12],
        "ict_missing_data": list(assessment.get("missing_data", [])),
        "fast_scalp": record.get("fast_scalp"),
        "recent_high": record.get("m5_recent_high"),
        "recent_low": record.get("m5_recent_low"),
        "verified_shadow_scenarios": record.get("shadow_scenarios_v2"),
    }
    if payload["ict_missing_data"] or payload["bid"] is None or payload["ask"] is None:
        return None
    instructions = (
        "You are a concise Persian ICT observer. Write ONLY ONE short Persian sentence "
        "(max 25 words) indicating the primary missing condition for the selected timeframe. "
        "Use verified_shadow_scenarios status and blocks as authoritative; "
        "never claim a sweep/MSS/retest/POI is confirmed just from general ICT evidence. "
        "Do not invent entry/SL/TP, recommendations, prices, or news. "
        "No headings, disclaimers, or additional paragraphs."
    )
    request_body = {
        "model": os.environ.get("NEXUS_AGENT_AI_MODEL", "gpt-4.1-mini"),
        "instructions": instructions,
        "input": json.dumps(payload, ensure_ascii=False, default=str),
        "max_output_tokens": 120,
        "store": False,
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(request_body).encode("utf-8"),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=18) as response:
            body = json.load(response)
        parts = []
        for item in body.get("output", []):
            if item.get("type") == "message":
                for part in item.get("content", []):
                    if part.get("type") == "output_text":
                        parts.append(str(part.get("text", "")))
        result = "\n".join(parts).strip()
        return result[:2500] if result else None
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError):
        return None
