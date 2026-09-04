from __future__ import annotations

"""Runtime signal-code formatter for the approved NEXUS production baseline.

The database primary key remains an integer AUTOINCREMENT. Only the public
signal code is normalized from the legacy four-digit form (NX-0001) to the
requested two-digit minimum-width form (NX-01).

Examples:
    1   -> NX-01
    9   -> NX-09
    10  -> NX-10
    99  -> NX-99
    100 -> NX-100
"""

from functools import wraps

from . import db


_INSTALLED = False


def format_signal_code(signal_id: int) -> str:
    return f"NX-{int(signal_id):02d}"


def install_two_digit_signal_codes() -> None:
    """Patch db.create_signal so every newly created signal uses NX-01 style."""
    global _INSTALLED
    if _INSTALLED:
        return

    original = db.create_signal

    @wraps(original)
    def _create_signal_two_digit(*args, **kwargs):
        row = original(*args, **kwargs)
        if row is None:
            return row

        try:
            signal_id = int(row["id"])
        except (KeyError, TypeError, ValueError):
            return row

        desired = format_signal_code(signal_id)
        current = str(row["code"] or "")
        if current != desired:
            with db.conn() as con:
                con.execute(
                    "UPDATE signals SET code=? WHERE id=?",
                    (desired, signal_id),
                )
            row = db.get_signal(signal_id)

        return row

    db.create_signal = _create_signal_two_digit
    _INSTALLED = True
