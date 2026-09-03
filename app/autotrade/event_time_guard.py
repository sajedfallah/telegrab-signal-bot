from __future__ import annotations

"""MT5 lifecycle event-time parser installed into ``app.main``.

The v0.6.5 lifecycle bridge calls ``_mt5_event_datetime(payload)`` for OPEN and
CLOSE events.  Some release paths referenced that helper without defining it,
which left otherwise valid CLOSE notifications retrying forever with NameError.

This module keeps the parser isolated and makes installation idempotent.  The
runtime installer writes the helper into ``app.main``'s module globals, so the
existing lifecycle code can use it without changing its call contract.
"""

import logging
import sys
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger("nexus-mt5-event-time")


def mt5_event_datetime(payload: dict[str, Any]) -> datetime:
    """Return a timezone-aware UTC timestamp for an MT5 lifecycle payload.

    Preferred source is ``event_time_ms`` because direct EA lifecycle events
    carry broker event time as Unix milliseconds.  ISO ``event_time`` is used as
    a secondary source.  Values that look like broker deal tickets (for example
    75,000,000) are deliberately not interpreted as epoch time.

    If neither field is usable, return current UTC.  Delivery must not fail just
    because an optional timestamp is absent; broker execution identity and P/L
    remain authoritative.
    """
    raw_ms = payload.get("event_time_ms")
    try:
        value = int(float(raw_ms)) if raw_ms not in (None, "") else 0
    except (TypeError, ValueError, OverflowError):
        value = 0

    # Contemporary Unix milliseconds.  Lower values are commonly MT5 deal
    # tickets and must never be treated as timestamps.
    if 1_000_000_000_000 <= value <= 9_999_999_999_999:
        try:
            return datetime.fromtimestamp(value / 1000.0, tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            pass

    raw_iso = str(payload.get("event_time") or "").strip()
    if raw_iso:
        try:
            dt = datetime.fromisoformat(raw_iso.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except (TypeError, ValueError, OverflowError):
            pass

    return datetime.now(timezone.utc)


def install_mt5_event_datetime_helper() -> bool:
    """Install the parser into the already-loaded ``app.main`` module."""
    module = sys.modules.get("app.main")
    if module is None:
        return False
    current = getattr(module, "_mt5_event_datetime", None)
    if current is not mt5_event_datetime:
        setattr(module, "_mt5_event_datetime", mt5_event_datetime)
        log.info("[NEXUS][MT5_EVENT_TIME][INSTALLED]")
    return True


__all__ = ["mt5_event_datetime", "install_mt5_event_datetime_helper"]
