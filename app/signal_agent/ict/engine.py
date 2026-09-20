from __future__ import annotations
from datetime import datetime,timezone
from . import detectors as d
from .sessions import session_events
class ICTEventEngine:
    def detect(self,candles,closed_only=True,as_of=None):
        cs=sorted(candles,key=lambda x:x.open_time)
        if not cs:return []
        if closed_only:
            as_of=as_of or datetime.now(timezone.utc)
            sec={"M5":300,"M15":900,"H1":3600,"H4":14400,"D1":86400}
            cs=[c for c in cs if c.open_time.timestamp()+sec[c.timeframe.upper()]<=as_of.timestamp()]
            if not cs:return []
        sw=d.swings(cs);disp=d.displacement(cs);liq=d.liquidity(cs,sw)
        events=sw+liq+d.sweeps(cs,liq)+disp+d.fvgs(cs)+d.structure_changes(cs,sw)
        obs=d.order_blocks(cs,disp);events+=obs+d.breakers(cs,obs)+d.premium_discount(cs)
        if cs[0].timeframe.upper()=="D1":events+=d.daily_quadrant(cs)
        events+=session_events(cs[0].symbol,cs[-1].open_time)
        return sorted({e.event_key:e for e in events}.values(),key=lambda e:e.event_key)
