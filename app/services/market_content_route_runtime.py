from __future__ import annotations

"""Route NEXUS market editorial to a dedicated Telegram destination.

This override intentionally does not modify ``PUBLIC_CHANNEL_ID`` because that
setting is also used by the customer join gate. Market/news delivery can move
to another channel without changing membership checks or the public-channel
entry flow.
"""

import os
from typing import Any

from app.services import market_public_channel_runtime as market_public


def _parse_target(raw: str) -> int | str:
    value = str(raw or "").strip()
    if not value:
        raise ValueError("empty market content target")
    try:
        return int(value)
    except ValueError:
        return value


def install(main: Any) -> None:
    """Override only market editorial delivery when a dedicated target is set."""
    raw = os.getenv("MARKET_CONTENT_CHANNEL_ID", "").strip()
    if not raw:
        main.log.info(
            "[NEXUS][MARKET_CONTENT_ROUTE] dedicated target not configured; fallback=%s",
            getattr(main.settings, "public_channel_id", None),
        )
        return

    target = _parse_target(raw)

    def _market_content_target(_main: Any) -> int | str:
        return target

    # The focused market runtime resolves its target at send time, so replacing
    # this resolver after installation safely redirects morning brief, focused
    # market news and economic alerts without touching the Telegram join gate.
    market_public._public_target = _market_content_target
    main.log.info(
        "[NEXUS][MARKET_CONTENT_ROUTE][INSTALLED] target=%s source=MARKET_CONTENT_CHANNEL_ID",
        target,
    )
