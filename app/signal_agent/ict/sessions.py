from __future__ import annotations
from datetime import datetime
from zoneinfo import ZoneInfo
from .models import ICTEvent
SESSIONS={"ASIA":("Asia/Tokyo",8,17),"LONDON":("Europe/London",8,17),"NEW_YORK":("America/New_York",8,17)}
def session_events(symbol:str,ts:datetime):
    out=[]
    for name,(zone,start,end) in SESSIONS.items():
        local=ts.astimezone(ZoneInfo(zone))
        if start<=local.hour<end:
            out.append(ICTEvent(symbol,"SESSION","SESSION_CONTEXT",name,ts,ts,metadata={"timezone":zone,"local_date":local.date().isoformat()}))
    return out
