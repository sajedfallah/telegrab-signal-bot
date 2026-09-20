from __future__ import annotations
from datetime import datetime, timezone
from .models import Candle, Quote
from .provider import MarketDataProvider

class MT5MarketDataProvider(MarketDataProvider):
    """Optional MetaTrader5-python adapter. Import is lazy so bot/API runtime is unaffected."""
    TF = {"M5":"TIMEFRAME_M5","M15":"TIMEFRAME_M15","H1":"TIMEFRAME_H1","H4":"TIMEFRAME_H4","D1":"TIMEFRAME_D1"}
    def __init__(self, mt5_module=None):
        if mt5_module is None:
            try: import MetaTrader5 as mt5_module
            except ImportError as exc: raise RuntimeError("MetaTrader5 package is required for MT5 provider") from exc
        self.mt5=mt5_module
    def quote(self,symbol:str)->Quote:
        t=self.mt5.symbol_info_tick(symbol)
        if t is None: raise RuntimeError(f"missing MT5 quote: {symbol}")
        return Quote(symbol.upper(),float(t.bid),float(t.ask),datetime.fromtimestamp(int(t.time),timezone.utc))
    def candles(self,symbol:str,timeframe:str,limit:int=500)->list[Candle]:
        key=timeframe.upper()
        if key not in self.TF: raise ValueError(f"unsupported timeframe: {timeframe}")
        rows=self.mt5.copy_rates_from_pos(symbol,getattr(self.mt5,self.TF[key]),0,limit)
        if rows is None or len(rows)==0: raise RuntimeError(f"missing MT5 candles: {symbol} {key}")
        return [Candle(symbol.upper(),key,datetime.fromtimestamp(int(r["time"]),timezone.utc),float(r["open"]),float(r["high"]),float(r["low"]),float(r["close"]),float(r["tick_volume"])) for r in rows]
