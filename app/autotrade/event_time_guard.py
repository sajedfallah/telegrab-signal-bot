from __future__ import annotations

"""MT5 lifecycle event-time parser installed into ``app.main``.

The v0.6.5 lifecycle bridge calls ``_mt5_event_datetime(payload)`` for OPEN and
CLOSE events. Some release paths referenced that helper without defining it,
which left otherwise valid CLOSE notifications retrying forever with NameError.

This module also protects the backend timeline from broker-server timestamps
that are encoded as Unix milliseconds without first being converted from the
broker timezone to UTC. In the live ePlanet test this appeared as an exact
+03:00 shift and produced a false three-hour holding duration for a trade that
was open for about one minute.
"""

import logging
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

log = logging.getLogger("nexus-mt5-event-time")

# Lifecycle events are delivered in near real time. A timestamp more than five
# minutes in the future cannot be broker execution truth in UTC.
_FUTURE_TOLERANCE_SECONDS = 5 * 60
# Real broker timezone offsets are minute based; 15 minutes safely covers all
# current civil-time offsets while avoiding second-level transport jitter.
_OFFSET_QUANTUM_SECONDS = 15 * 60
_MAX_BROKER_OFFSET_SECONDS = 14 * 60 * 60
_CORRECTED_NEAR_NOW_SECONDS = 10 * 60


def _normalize_broker_candidate(candidate: datetime, *, source: str) -> datetime:
    """Return a plausible UTC lifecycle timestamp.

    MT5 ``DEAL_TIME`` is broker-server time. Some EA paths historically sent it
    as if it were Unix UTC. When that creates a future timestamp, infer a normal
    broker UTC offset in 15-minute increments and remove it. If the value still
    cannot be made plausible, fail closed to backend receive time instead of
    allowing a future close time to corrupt holding duration and reports.
    """
    if candidate.tzinfo is None:
        candidate = candidate.replace(tzinfo=timezone.utc)
    else:
        candidate = candidate.astimezone(timezone.utc)

    now = datetime.now(timezone.utc)
    future_seconds = (candidate - now).total_seconds()
    if future_seconds <= _FUTURE_TOLERANCE_SECONDS:
        return candidate

    if future_seconds <= _MAX_BROKER_OFFSET_SECONDS + _FUTURE_TOLERANCE_SECONDS:
        inferred_offset = int(round(future_seconds / _OFFSET_QUANTUM_SECONDS)) * _OFFSET_QUANTUM_SECONDS
        if _OFFSET_QUANTUM_SECONDS <= inferred_offset <= _MAX_BROKER_OFFSET_SECONDS:
            corrected = candidate - timedelta(seconds=inferred_offset)
            if abs((corrected - now).total_seconds()) <= _CORRECTED_NEAR_NOW_SECONDS:
                log.warning(
                    "[NEXUS][MT5_EVENT_TIME][BROKER_OFFSET_CORRECTED] source=%s offset_seconds=%s raw=%s corrected=%s",
                    source,
                    inferred_offset,
                    candidate.isoformat(),
                    corrected.isoformat(),
                )
                return corrected

    log.warning(
        "[NEXUS][MT5_EVENT_TIME][FUTURE_TIMESTAMP_REJECTED] source=%s raw=%s fallback=%s",
        source,
        candidate.isoformat(),
        now.isoformat(),
    )
    return now


def mt5_event_datetime(payload: dict[str, Any]) -> datetime:
    """Return a timezone-aware UTC timestamp for an MT5 lifecycle payload.

    Preferred source is ``event_time_ms`` because direct EA lifecycle events
    carry broker event time as milliseconds. ISO ``event_time`` is a secondary
    source. Values that look like broker deal tickets (for example 75,000,000)
    are deliberately not interpreted as epoch time.

    Future values caused by broker-server timezone leakage are normalized before
    use. If neither field is usable, current UTC is returned. Delivery must not
    fail merely because an optional timestamp is absent; broker execution
    identity and P/L remain authoritative.
    """
    raw_ms = payload.get("event_time_ms")
    try:
        value = int(float(raw_ms)) if raw_ms not in (None, "") else 0
    except (TypeError, ValueError, OverflowError):
        value = 0

    # Contemporary Unix milliseconds. Lower values are commonly MT5 deal
    # tickets and must never be treated as timestamps.
    if 1_000_000_000_000 <= value <= 9_999_999_999_999:
        try:
            candidate = datetime.fromtimestamp(value / 1000.0, tz=timezone.utc)
            return _normalize_broker_candidate(candidate, source="event_time_ms")
        except (OSError, OverflowError, ValueError):
            pass

    raw_iso = str(payload.get("event_time") or "").strip()
    if raw_iso:
        try:
            candidate = datetime.fromisoformat(raw_iso.replace("Z", "+00:00"))
            if candidate.tzinfo is None:
                candidate = candidate.replace(tzinfo=timezone.utc)
            return _normalize_broker_candidate(candidate, source="event_time")
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
