from __future__ import annotations
import sqlite3
from .models import ICTEvent
class ICTEventStore:
    def __init__(self,path): self.path=path; self.migrate()
    def _c(self): c=sqlite3.connect(self.path); c.row_factory=sqlite3.Row; return c
    def migrate(self):
        with self._c() as c:c.executescript("""CREATE TABLE IF NOT EXISTS signal_agent_ict_events(event_key TEXT PRIMARY KEY,symbol TEXT NOT NULL,timeframe TEXT NOT NULL,event_type TEXT NOT NULL,direction TEXT NOT NULL,status TEXT NOT NULL,source_time TEXT NOT NULL,detected_at TEXT NOT NULL,price_low REAL,price_high REAL,reference_price REAL,parent_key TEXT,metadata_json TEXT NOT NULL,rule_version TEXT NOT NULL); CREATE TABLE IF NOT EXISTS signal_agent_ict_event_links(child_key TEXT NOT NULL,parent_key TEXT NOT NULL,relation TEXT NOT NULL,PRIMARY KEY(child_key,parent_key,relation)); CREATE TABLE IF NOT EXISTS signal_agent_ict_runtime(component TEXT PRIMARY KEY,status TEXT NOT NULL,event_count INTEGER NOT NULL DEFAULT 0,error_text TEXT);""")
    def save(self,events:list[ICTEvent]):
        with self._c() as c:
            for e in events:
                c.execute("INSERT OR IGNORE INTO signal_agent_ict_events VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(e.event_key,e.symbol,e.timeframe,e.event_type,e.direction,e.status.value,e.source_time.isoformat(),e.detected_at.isoformat(),e.price_low,e.price_high,e.reference_price,e.parent_key,e.metadata_json(),e.rule_version))
                if e.parent_key:c.execute("INSERT OR IGNORE INTO signal_agent_ict_event_links VALUES(?,?,?)",(e.event_key,e.parent_key,"DERIVED_FROM"))
    def keys(self):
        with self._c() as c:return [r[0] for r in c.execute("SELECT event_key FROM signal_agent_ict_events ORDER BY event_key")]
