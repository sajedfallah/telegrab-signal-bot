from __future__ import annotations

import html
import logging
import re
from typing import Any

log = logging.getLogger("nexus-result-card-guard")

_HEADER = "<b>━━━━━━━━ NEXUS RESULT ━━━━━━━━</b>"
_TAG_RE = re.compile(r"<[^>]+>")


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
    performance: str = "",
    duration: str = "",
    reason: str = "",
    ticket: str = "",
) -> str:
    code = _esc(_row_get(row, "code", "—"))
    symbol = _esc(str(_row_get(row, "symbol", "—")).upper())
    direction = _esc(str(_row_get(row, "direction", "—")).upper())
    result = _normalize_result(result)
    badge = {
        "WIN": "🟢 WIN",
        "LOSS": "🔴 LOSS",
        "BREAK EVEN": "⚪ BREAK EVEN",
    }.get(result, "⚪ CLOSED")

    lines = [
        _HEADER,
        f"<b>{code}</b>  <b>{badge}</b>",
        "",
        f"📌 Symbol: <b>{symbol}</b>",
        f"↕️ Direction: <b>{direction}</b>",
        f"📍 Entry: {_price(_row_get(row, 'entry_price', ''))}",
        f"🏁 Exit: {_price(exit_price)}",
    ]

    detail_lines: list[str] = []
    if broker_pnl:
        detail_lines.append(f"💰 Broker P/L: <b>{_esc(broker_pnl)}</b>")
    if performance:
        detail_lines.append(f"📊 Performance: <b>{_esc(performance)}</b>")
    if duration and duration != "—":
        detail_lines.append(f"⏱ Duration: <b>{_esc(duration)}</b>")
    if reason:
        detail_lines.append(f"🚪 Exit Reason: <b>{_esc(reason.upper())}</b>")
    if ticket:
        detail_lines.append(f"🎫 Ticket: <code>{_esc(ticket)}</code>")

    if detail_lines:
        lines.append("")
        lines.extend(detail_lines)
    lines.append("📌 Status: <b>CLOSED</b>")
    return "\n".join(lines)


def format_result_card(row: Any, caption: str) -> str:
    """Convert every final CLOSE caption to the canonical NEXUS result card.

    The function intentionally changes text formatting only.  Telegram delivery,
    reply threading, broker truth and lifecycle screenshot policy stay untouched.
    Unknown/non-result lifecycle captions pass through unchanged.
    """
    if not caption or _HEADER in caption:
        return caption

    plain = _plain(caption)

    # Broker-driven MT5 close currently arrives as one compact pipe-delimited line.
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
            performance=fields.get("performance", ""),
            duration=fields.get("duration", ""),
            reason=fields.get("reason", ""),
            ticket=fields.get("ticket", ""),
        )

    # Admin/manual close already uses a multiline card, but historically had a
    # different Persian/English layout.  Normalize both variants to one LTR card.
    if "TRADE RESULT" in plain.upper() or "نتیجه معامله" in plain:
        return _build_card(
            row,
            exit_price=_line_value(plain, "Exit", "خروج"),
            result=_line_value(plain, "Result", "نتیجه"),
            performance=_line_value(plain, "P/L", "سود/زیان"),
            reason=_line_value(plain, "Exit type", "نوع خروج"),
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
