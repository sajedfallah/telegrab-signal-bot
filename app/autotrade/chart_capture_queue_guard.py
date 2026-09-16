from __future__ import annotations

from typing import Any, Callable

from .. import db


def _signal_status(signal_id: int) -> str:
    row = db.get_signal(int(signal_id))
    if not row:
        return ""
    try:
        return str(row["status"] or "").strip().upper()
    except Exception:
        return ""


def install_chart_capture_queue_guard(app) -> None:
    """Keep post-publication chart repair candidates aligned with claim eligibility.

    V24 repair discovery can see old FAILED/EXPIRED jobs whose parent signal has
    already reached CLOSED/REJECTED/etc. The ChartAgent claim gate intentionally
    accepts only DRAFT initial captures and ACTIVE broker-confirmed repairs. Do
    not requeue terminal parent signals only to make the agent consume them and
    receive HTTP 409 on every poll.

    This guard is intentionally additive: historical rows are left untouched and
    only future repair-candidate selection is narrowed to ACTIVE signals.
    """
    if getattr(app.state, "nexus_chart_capture_queue_guard_v33", False):
        return

    from . import chart_delivery_guard as delivery

    original: Callable[[str], list[Any]] = delivery._terminal_repair_candidates

    def active_repair_candidates(account: str) -> list[Any]:
        rows = original(str(account))
        return [row for row in rows if _signal_status(int(row["signal_id"])) == "ACTIVE"]

    delivery._terminal_repair_candidates = active_repair_candidates
    app.state.nexus_chart_capture_queue_guard_v33 = True
