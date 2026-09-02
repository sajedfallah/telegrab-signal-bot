"""Canonical symbol registry and broker mapping primitives.

The Telegram market selector is reporting-only. Trading uses a canonical symbol;
the execution adapter resolves that symbol to the user's MT5 broker symbol.
Adding a broker mapping does not require changing signal/business logic.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


CANONICAL_SYMBOLS: dict[str, tuple[str, ...]] = {
    "FOREX": ("EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD"),
    "GOLD": ("XAUUSD", "XAGUSD"),
    "INDEX": ("DOWJONES", "NASDAQ", "SPX500"),
    "CRYPTO": ("BTCUSD", "ETHUSD", "SOLUSD", "BNBUSD", "XRPUSD", "DOGEUSD", "AVAXUSD", "LTCUSD"),
}


def normalize_symbol(value: str) -> str:
    """Normalize admin/user symbol input to a canonical broker-neutral token."""
    raw = re.sub(r"\s+", "", str(value or "").strip().upper())
    raw = raw.replace("/", "").replace("-", "")
    if not re.fullmatch(r"[A-Z0-9._]{3,32}", raw):
        raise ValueError("invalid symbol format")
    return raw


def infer_category(symbol: str) -> str:
    s = normalize_symbol(symbol)
    if s.startswith("XAU"):
        return "GOLD"
    if any(s.startswith(x) for x in CANONICAL_SYMBOLS["CRYPTO"]):
        return "CRYPTO"
    if s in CANONICAL_SYMBOLS["INDEX"]:
        return "INDEX"
    if len(s) >= 6 and s[:6].isalpha():
        return "FOREX"
    return "OTHER"


@dataclass(frozen=True)
class BrokerSymbolMap:
    broker: str
    aliases: dict[str, str] = field(default_factory=dict)

    def resolve(self, canonical: str) -> str | None:
        key = normalize_symbol(canonical)
        return self.aliases.get(key, key)


DEFAULT_BROKER = "EPLANET"
DEFAULT_MAPPINGS = {
    DEFAULT_BROKER: BrokerSymbolMap(DEFAULT_BROKER, {
        "XAUUSD": "XAUUSD",
        "XAGUSD": "XAGUSD",
        "BTCUSD": "BTCUSD",
        "ETHUSD": "ETHUSD",
        "SOLUSD": "SOLUSD",
    })
}


def resolve_symbol(canonical: str, broker: str = DEFAULT_BROKER) -> str:
    """Resolve through the broker registry; unknown brokers safely fall back to canonical."""
    broker_key = str(broker or DEFAULT_BROKER).strip().upper()
    mapping = DEFAULT_MAPPINGS.get(broker_key)
    return mapping.resolve(canonical) if mapping else normalize_symbol(canonical)
