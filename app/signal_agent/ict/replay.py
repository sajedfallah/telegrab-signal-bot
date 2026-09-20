from __future__ import annotations
from datetime import timedelta
class ReplayRunner:
    def __init__(self,engine):self.engine=engine
    def run(self,candles):
        if not candles:return []
        sec={"M5":300,"M15":900,"H1":3600,"H4":14400,"D1":86400}
        tf=candles[-1].timeframe.upper()
        # A final replay is intentionally equivalent to live processing at the close of the last supplied candle.
        as_of=candles[-1].open_time+timedelta(seconds=sec[tf])
        return self.engine.detect(candles,closed_only=True,as_of=as_of)
