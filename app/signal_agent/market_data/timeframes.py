from __future__ import annotations
from datetime import datetime, timedelta, timezone
from .models import Candle

_SECONDS={"M5":300,"M15":900,"H1":3600,"H4":14400,"D1":86400}
def bucket_start(ts:datetime,timeframe:str)->datetime:
    sec=_SECONDS[timeframe.upper()]; u=ts.astimezone(timezone.utc); epoch=int(u.timestamp()); return datetime.fromtimestamp(epoch-epoch%sec,timezone.utc)
def aggregate(symbol:str,timeframe:str,source:list[Candle])->list[Candle]:
    groups={}
    for c in sorted(source,key=lambda x:x.open_time):
        k=bucket_start(c.open_time,timeframe); groups.setdefault(k,[]).append(c)
    return [Candle(symbol.upper(),timeframe.upper(),k,x[0].open,max(v.high for v in x),min(v.low for v in x),x[-1].close,sum(v.volume for v in x)) for k,x in sorted(groups.items())]
