from __future__ import annotations
import logging, threading
from ..config import TIMEFRAMES, SignalAgentSettings
from .provider import MarketDataProvider
from .store import MarketDataStore

log=logging.getLogger("nexus.signal_agent.market_data")
class MarketDataRuntime:
    def __init__(self,provider:MarketDataProvider,store:MarketDataStore,settings:SignalAgentSettings):
        self.provider=provider; self.store=store; self.settings=settings
        self._stop=threading.Event(); self._thread=None
        self.state={s:self.store.load_state(s) for s in settings.symbols}
    def poll_once(self):
        result={}
        for symbol in self.settings.symbols:
            try:
                q=self.provider.quote(symbol)
                if q.stale_age_seconds>self.settings.stale_after_seconds: raise RuntimeError(f"stale quote age={q.stale_age_seconds:.1f}s")
                self.store.save_quote(q); counts={}
                for tf in TIMEFRAMES:
                    rows=self.provider.candles(symbol,tf)
                    if not rows: raise RuntimeError(f"missing candles: {symbol} {tf}")
                    self.store.save_candles(rows); counts[tf]=len(rows)
                self.state[symbol]=self.store.load_state(symbol)
                self.store.health(f"market:{symbol}","OK",metadata={"spread":q.spread,"candles":counts})
                result[symbol]={"status":"OK","spread":q.spread,"candles":counts}; log.info("signal_agent_market_poll %s",result[symbol])
            except Exception as exc:
                self.store.health(f"market:{symbol}","ERROR",error=str(exc)); result[symbol]={"status":"ERROR","error":str(exc)}; log.exception("signal_agent_market_poll_failed symbol=%s",symbol)
        return result
    def run_forever(self):
        log.info("signal_agent_market_runtime_started symbols=%s",self.settings.symbols)
        try:
            while not self._stop.is_set():
                self.poll_once()
                self._stop.wait(max(.1,self.settings.poll_interval_seconds))
        finally: log.info("signal_agent_market_runtime_stopped")
    def start(self):
        if not self.settings.enabled: return False
        if self._thread and self._thread.is_alive(): return True
        self._stop.clear(); self._thread=threading.Thread(target=self.run_forever,name="signal-agent-market-data",daemon=True); self._thread.start(); return True
    def stop(self,timeout:float=5.0):
        self._stop.set()
        if self._thread: self._thread.join(timeout)
