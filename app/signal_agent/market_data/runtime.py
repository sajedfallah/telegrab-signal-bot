from __future__ import annotations
import logging
from ..config import TIMEFRAMES, SignalAgentSettings
from .provider import MarketDataProvider
from .store import MarketDataStore

log=logging.getLogger("nexus.signal_agent.market_data")
class MarketDataRuntime:
    def __init__(self,provider:MarketDataProvider,store:MarketDataStore,settings:SignalAgentSettings): self.provider=provider; self.store=store; self.settings=settings
    def poll_once(self):
        result={}
        for symbol in self.settings.symbols:
            try:
                q=self.provider.quote(symbol)
                if q.stale_age_seconds>self.settings.stale_after_seconds: raise RuntimeError(f"stale quote age={q.stale_age_seconds:.1f}s")
                self.store.save_quote(q); counts={}
                for tf in TIMEFRAMES:
                    rows=self.provider.candles(symbol,tf); self.store.save_candles(rows); counts[tf]=len(rows)
                self.store.health(f"market:{symbol}","OK",metadata={"spread":q.spread,"candles":counts}); result[symbol]={"status":"OK","spread":q.spread,"candles":counts}; log.info("signal_agent_market_poll %s",result[symbol])
            except Exception as exc:
                self.store.health(f"market:{symbol}","ERROR",error=str(exc)); result[symbol]={"status":"ERROR","error":str(exc)}; log.exception("signal_agent_market_poll_failed symbol=%s",symbol)
        return result
