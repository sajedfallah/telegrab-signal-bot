from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import hashlib, json

RULE_VERSION="B1"
class EventStatus(str,Enum):
    ACTIVE="ACTIVE"; MITIGATED="MITIGATED"; INVALIDATED="INVALIDATED"; EXPIRED="EXPIRED"

@dataclass(frozen=True)
class ICTEvent:
    symbol:str; timeframe:str; event_type:str; direction:str; source_time:datetime
    detected_at:datetime; price_low:float|None=None; price_high:float|None=None
    reference_price:float|None=None; status:EventStatus=EventStatus.ACTIVE
    parent_key:str|None=None; metadata:dict=field(default_factory=dict); rule_version:str=RULE_VERSION
    @property
    def event_key(self)->str:
        raw="|".join((self.symbol.upper(),self.timeframe.upper(),self.event_type,self.direction,self.source_time.isoformat(),self.rule_version))
        return hashlib.sha256(raw.encode()).hexdigest()
    def metadata_json(self): return json.dumps(self.metadata,sort_keys=True,separators=(",",":"))
