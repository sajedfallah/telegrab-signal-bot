from __future__ import annotations
class ReplayRunner:
    def __init__(self,engine): self.engine=engine
    def run(self,candles):
        # Prefix replay simulates live closed-candle arrival. Event keys make output idempotent.
        found={}
        for i in range(1,len(candles)+1):
            for e in self.engine.detect(candles[:i]): found[e.event_key]=e
        return list(found.values())
