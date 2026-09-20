from __future__ import annotations
from dataclasses import dataclass,field,asdict
from datetime import datetime
import hashlib,json
CONTEXT_RULE_VERSION="C1"
@dataclass(frozen=True)
class ContextSnapshot:
    symbol:str;as_of:datetime;price:float
    timeframe_bias:dict;htf_bias:str;structure_alignment:str
    dealing_range:dict;price_location:str
    daily_quadrant:dict|None;quadrant_relation:str
    liquidity:dict;recent_sweeps:list;active_pois:list
    session:dict;context_state:str;context_reasons:list
    source_event_keys:list;rule_version:str=CONTEXT_RULE_VERSION
    @property
    def context_key(self):
        sources=",".join(sorted(self.source_event_keys))
        raw=f"{self.symbol.upper()}|{self.as_of.isoformat()}|{self.rule_version}|{hashlib.sha256(sources.encode()).hexdigest()}"
        return hashlib.sha256(raw.encode()).hexdigest()
    def payload_json(self):
        d=asdict(self);d["as_of"]=self.as_of.isoformat()
        return json.dumps(d,sort_keys=True,separators=(",",":"))
