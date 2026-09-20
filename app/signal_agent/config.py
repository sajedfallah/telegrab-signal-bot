from __future__ import annotations
import os
from dataclasses import dataclass

TIMEFRAMES = ("M5","M15","H1","H4","D1")

@dataclass(frozen=True)
class SignalAgentSettings:
    enabled: bool = os.getenv("SIGNAL_AGENT_MARKET_DATA_ENABLED","0").strip().lower() in {"1","true","yes","on"}
    symbols: tuple[str,...] = tuple(x.strip().upper() for x in os.getenv("SIGNAL_AGENT_SYMBOLS","XAUUSD").split(",") if x.strip())
    stale_after_seconds: int = int(os.getenv("SIGNAL_AGENT_STALE_AFTER_SECONDS","30"))
    provider: str = os.getenv("SIGNAL_AGENT_MARKET_DATA_PROVIDER","MT5").strip().upper()

settings = SignalAgentSettings()
