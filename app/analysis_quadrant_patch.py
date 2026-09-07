from __future__ import annotations

import os
from dataclasses import replace

from . import analysis_center


_QUADRANT_RULES = (
    " NEXUS Quadrant rule: a Quadrant Zone is a high-importance DAILY reaction/reversal zone. "
    "It is identified by three internal percentage levels: 25%, 50%, and 75%. "
    "These percentage labels are structural quadrant levels, not price values. "
    "When such a red/gray three-level zone is visible on the chart, explicitly recognize it as 'ناحیه کوادرانت Daily' and refer to its internal levels as 25%, 50%, and 75%. "
    "Treat it as higher-timeframe context with more weight than ordinary M15 zones, but never treat touching a quadrant level as an entry signal. "
    "A trade still requires lower-timeframe confirmation, preferably on M5, such as liquidity sweep, displacement, MSS/CHOCH, and a valid FVG/OB entry model. "
    "If the chart's quadrant labels or boundaries are incorrectly drawn, state the correction clearly."
)


def _optional_int(raw: str | None) -> int | None:
    value = (raw or "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _chat_value(raw: str | None):
    value = (raw or "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return value


def install_quadrant_rules() -> None:
    """Apply NEXUS Daily Quadrant semantics and route fallbacks at runtime.

    ANALYSIS_TARGET_* remains authoritative. If it is absent, Analysis Center
    inherits FREE_SIGNAL_CHAT_ID/FREE_SIGNAL_TOPIC_ID so the admin does not need
    to maintain two Telegram route definitions.
    """
    original_prompt = analysis_center._base_system_prompt

    def patched_prompt() -> str:
        return original_prompt() + _QUADRANT_RULES

    analysis_center._base_system_prompt = patched_prompt

    cfg = analysis_center.analysis_settings
    target_chat = cfg.target_chat_id or _chat_value(os.getenv("FREE_SIGNAL_CHAT_ID"))
    target_thread = cfg.target_thread_id
    if target_thread is None:
        target_thread = _optional_int(os.getenv("FREE_SIGNAL_TOPIC_ID"))
    analysis_center.analysis_settings = replace(
        cfg,
        target_chat_id=target_chat,
        target_thread_id=target_thread,
    )
