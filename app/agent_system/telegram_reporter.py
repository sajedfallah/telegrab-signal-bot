from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Mapping


class TelegramReportError(RuntimeError):
    """Sanitized outbound reporting error that never includes the bot token."""


@dataclass(frozen=True)
class TelegramShadowReporter:
    """Minimal outbound-only reporter for the isolated Agent Test Bot.

    It does not poll Telegram, register handlers, publish to NEXUS channels,
    mutate AutoTrade, or place MT5 orders.
    """

    bot_token: str
    chat_id: str
    timeout_seconds: int = 10

    def __post_init__(self) -> None:
        if not self.bot_token.strip():
            raise ValueError("bot_token is required")
        if not self.chat_id.strip():
            raise ValueError("chat_id is required")

    def send_text(self, text: str) -> None:
        payload = urllib.parse.urlencode(
            {
                "chat_id": self.chat_id,
                "text": text,
                "disable_web_page_preview": "true",
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
            data=payload,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise TelegramReportError(f"Telegram sendMessage HTTP {exc.code}") from None
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", None)
            label = type(reason).__name__ if reason is not None else "network_error"
            raise TelegramReportError(f"Telegram sendMessage network failure: {label}") from None
        except (TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
            raise TelegramReportError(f"Telegram sendMessage failure: {type(exc).__name__}") from None
        if not body.get("ok"):
            description = str(body.get("description") or "unknown error")
            raise TelegramReportError(f"Telegram sendMessage rejected: {description}")


def format_shadow_record(record: Mapping[str, object]) -> str:
    symbol = str(record.get("symbol") or "UNKNOWN")
    if record.get("error"):
        return (
            f"⚠️ NEXUS AGENT TEST | {symbol}\n\n"
            f"State: NO_TRADE\n"
            f"Feed/Runner Error: {record['error']}\n\n"
            "MODE: SHADOW — NO REAL ORDER"
        )

    scan = str(record.get("scan") or "-")
    supervisor = str(record.get("supervisor") or "-")
    final = str(record.get("final") or "-")
    direction = str(record.get("direction") or "NEUTRAL")
    risk_allowed = record.get("risk_allowed")
    risk_text = "NOT_EVALUATED" if risk_allowed is None else ("PASSED" if risk_allowed else "BLOCKED")
    blocks = record.get("risk_blocks") or []
    block_text = ", ".join(str(x) for x in blocks) if blocks else "-"
    return (
        f"🧠 NEXUS AGENT TEST | {symbol}\n\n"
        f"Scanner: {scan}\n"
        f"Supervisor: {supervisor}\n"
        f"Final: {final}\n"
        f"Direction: {direction}\n"
        f"Risk Gate: {risk_text}\n"
        f"Risk Blocks: {block_text}\n\n"
        "MODE: SHADOW — NO REAL ORDER"
    )
