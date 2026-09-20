from __future__ import annotations
from . import detectors as d
from .sessions import session_events
class ICTEventEngine:
    def detect(self,candles,closed_only=True):
        cs=sorted(candles,key=lambda x:x.open_time)
        if not cs:return []
        sw=d.swings(cs); disp=d.displacement(cs); fvg=d.fvgs(cs); liq=d.liquidity(cs,sw)
        events=sw+liq+d.sweeps(cs,liq)+disp+fvg
        events+=d.structure_changes(cs,sw)
        obs=d.order_blocks(cs,disp); events+=obs+d.breakers(cs,obs)+d.premium_discount(cs)
        if cs[0].timeframe.upper()=="D1":events+=d.daily_quadrant(cs)
        events+=session_events(cs[0].symbol,cs[-1].open_time)
        return self._dedup(events)
    @staticmethod
    def _dedup(events):
        return list({e.event_key:e for e in events}.values())
