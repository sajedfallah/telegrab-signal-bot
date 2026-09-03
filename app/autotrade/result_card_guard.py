from __future__ import annotations

import html
import logging
import re
from typing import Any

log = logging.getLogger("nexus-result-card-guard")

_TAG_RE = re.compile(r"<[^>]+>")
_CANONICAL_MARKER = "💰 Broker P/L:"


def _row_get(row: Any, key: str, default: Any = "") -> Any:
    try:
        value = row[key]
    except Exception:
        try:
            value = getattr(row, key)
        except Exception:
            return default
    return default if value is None else value


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=False)


def _price(value: Any) -> str:
    if value in (None, "", "—"):
        return "—"
    try:
        number = float(value)
        text = format(number, ".10f").rstrip("0").rstrip(".")
        if text in {"", "-0"}:
            text = "0"
    except (TypeError, ValueError):
        text = str(value).strip()
    return f"<code>{_esc(text)}</code>"


def _plain(caption: str) -> str:
    return html.unescape(_TAG_RE.sub("", caption or "")).strip()


def _line_value(plain: str, *labels: str) -> str:
    for line in plain.splitlines():
        stripped = line.strip()
        for label in labels:
            prefix = label + ":"
            if stripped.casefold().startswith(prefix.casefold()):
                return stripped[len(prefix) :].strip()
    return ""


def _normalize_result(value: str) -> str:
    v = (value or "").strip().upper().replace("_", " ")
    mapping = {
        "برد": "WIN",
        "باخت": "LOSS",
        "سر به سر": "BREAK EVEN",
        "BREAKEVEN": "BREAK EVEN",
        "BE": "BREAK EVEN",
    }
    return mapping.get(v, v or "CLOSED")


def _build_card(
    row: Any,
    *,
    exit_price: str = "",
    broker_pnl: str = "",
    result: str = "",
    duration: str = "",
    reason: str = "",
) -> str:
    """Render the intentionally minimal final-result flash card.

    Product rule: final CLOSE replies must contain only the signal/result identity,
    exit price, broker P/L, holding duration, exit reason and final status.  Symbol,
    direction, entry, performance/pips and broker ticket belong to the original
    signal or internal execution history and must not clutter the result reply.
    """
    code = _esc(_row_get(row, "code", "—"))
    result = _normalize_result(result)
    badge = {
        "WIN": "🟢 WIN",
        "LOSS": "🔴 LOSS",
        "BREAK EVEN": "⚪ BREAK EVEN",
    }.get(result, "⚪ CLOSED")

    pnl = str(broker_pnl or "—").strip() or "—"
    duration_text = str(duration or "—").strip() or "—"
    reason_text = str(reason or "—").strip().upper() or "—"

    return "\n".join(
        [
            f"<b>{code}</b>  <b>{badge}</b>",
            "",
            f"🏁 Exit: {_price(exit_price)}",
            f"💰 Broker P/L: <b>{_esc(pnl)}</b>",
            f"⏱️ Duration: <b>{_esc(duration_text)}</b>",
            f"🚪 Exit Reason: <b>{_esc(reason_text)}</b>",
            "📌 Status: <b>CLOSED</b>",
        ]
    )


def format_result_card(row: Any, caption: str) -> str:
    """Convert every final CLOSE caption to the canonical minimal result card.

    Telegram delivery, reply threading, broker truth and lifecycle screenshot
    policy stay untouched. Unknown/non-result lifecycle captions pass through.
    """
    if not caption or (_CANONICAL_MARKER in caption and "📌 Status: <b>CLOSED</b>" in caption):
        return caption

    plain = _plain(caption)

    # Broker-driven MT5 CLOSE arrives as one compact pipe-delimited line.
    if plain.startswith("TRADE CLOSED |"):
        parts = [part.strip() for part in plain.split("|")]
        fields: dict[str, str] = {}
        for part in parts[1:]:
            if "=" in part:
                key, value = part.split("=", 1)
                fields[key.strip().lower()] = value.strip()
        return _build_card(
            row,
            exit_price=fields.get("exit", ""),
            broker_pnl=fields.get("pnl", ""),
            result=fields.get("result", ""),
            duration=fields.get("duration", ""),
            reason=fields.get("reason", ""),
        )

    # Admin/manual close does not have broker-confirmed P/L or duration in the
    # legacy caption. Keep the required fields visible with an explicit dash
    # instead of mis-labelling a pip/percent metric as Broker P/L.
    if "TRADE RESULT" in plain.upper() or "نتیجه معامله" in plain:
        return _build_card(
            row,
            exit_price=_line_value(plain, "Exit", "خروج"),
            broker_pnl="—",
            result=_line_value(plain, "Result", "نتیجه"),
            duration="—",
            reason=_line_value(plain, "Exit type", "نوع خروج") or "MANUAL CLOSE",
        )

    return caption


def install_result_card_formatter() -> bool:
    """Install the formatter at the common text-result publication boundary."""
    import app.main as main_module

    current = getattr(main_module, "_publish_result_with_fallback", None)
    if current is None:
        log.error("[NEXUS][RESULT_CARD][INSTALL_FAILED] publisher missing")
        return False
    if getattr(current, "_nexus_result_card_guard", False):
        return True

    async def wrapped(bot, target, row, last_message_id, original_message_id, caption, label):
        formatted = format_result_card(row, caption)
        return await current(
            bot,
            target,
            row,
            last_message_id,
            original_message_id,
            formatted,
            label,
        )

    wrapped._nexus_result_card_guard = True  # type: ignore[attr-defined]
    wrapped._nexus_result_card_original = current  # type: ignore[attr-defined]
    main_module._publish_result_with_fallback = wrapped
    log.info("[NEXUS][RESULT_CARD][INSTALLED]")
    return True
