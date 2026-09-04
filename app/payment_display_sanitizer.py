from __future__ import annotations

"""Small startup guard for human-readable payment account fields.

A Windows/PowerShell edit can leave Persian UTF-8 text in .env as classic
mojibake (for example strings starting with ``Ø``/``Ù``). The invoice renderer
is correct; the corrupted environment value is not. Repair only when the
conversion is clearly safer, before app.config materializes the frozen
Settings object.
"""

import os

_MOJIBAKE_MARKERS = ("Ø", "Ù", "Û", "Ã", "Â")


def _persian_arabic_score(value: str) -> int:
    return sum(1 for ch in value if "\u0600" <= ch <= "\u06ff")


def _mojibake_score(value: str) -> int:
    return sum(value.count(marker) for marker in _MOJIBAKE_MARKERS)


def repair_utf8_mojibake(value: str) -> str:
    raw = str(value or "").strip()
    if not raw or _mojibake_score(raw) == 0:
        return raw

    candidates: list[str] = []
    for codec in ("latin1", "cp1252"):
        try:
            candidates.append(raw.encode(codec).decode("utf-8"))
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue

    best = raw
    for candidate in candidates:
        if (
            _persian_arabic_score(candidate) > _persian_arabic_score(best)
            and _mojibake_score(candidate) < _mojibake_score(best)
        ):
            best = candidate
    return best


def repair_payment_owner_env() -> str:
    current = os.getenv("PAYMENT_OWNER", "")
    repaired = repair_utf8_mojibake(current)
    if repaired and repaired != current:
        os.environ["PAYMENT_OWNER"] = repaired
    return repaired
