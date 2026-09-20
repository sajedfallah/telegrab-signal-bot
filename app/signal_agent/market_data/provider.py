from __future__ import annotations
from abc import ABC, abstractmethod
from .models import Candle, Quote

class MarketDataProvider(ABC):
    @abstractmethod
    def quote(self, symbol: str) -> Quote: ...
    @abstractmethod
    def candles(self, symbol: str, timeframe: str, limit: int=500) -> list[Candle]: ...
