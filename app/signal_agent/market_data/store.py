from __future__ import annotations
import json, sqlite3
from datetime import datetime, timezone
from pathlib import Path
from .models import Candle, Quote

class MarketDataStore:
    def __init__(self,path:str): self.path=path; self.migrate()
    def _con(self): c=sqlite3.connect(self.path); c.row_factory=sqlite3.Row; return c
    def migrate(self):
        with self._con() as c:
            c.executescript("""CREATE TABLE IF NOT EXISTS signal_agent_quotes(symbol TEXT PRIMARY KEY,bid REAL NOT NULL,ask REAL NOT NULL,spread REAL NOT NULL,observed_at TEXT NOT NULL); CREATE TABLE IF NOT EXISTS signal_agent_candles(symbol TEXT NOT NULL,timeframe TEXT NOT NULL,open_time TEXT NOT NULL,open REAL NOT NULL,high REAL NOT NULL,low REAL NOT NULL,close REAL NOT NULL,volume REAL NOT NULL DEFAULT 0,PRIMARY KEY(symbol,timeframe,open_time)); CREATE TABLE IF NOT EXISTS signal_agent_runtime(component TEXT PRIMARY KEY,status TEXT NOT NULL,last_ok_at TEXT,last_error_at TEXT,error_text TEXT,metadata_json TEXT NOT NULL DEFAULT '{}');""")
    def save_quote(self,q:Quote):
        with self._con() as c:c.execute("INSERT INTO signal_agent_quotes VALUES(?,?,?,?,?) ON CONFLICT(symbol) DO UPDATE SET bid=excluded.bid,ask=excluded.ask,spread=excluded.spread,observed_at=excluded.observed_at",(q.symbol,q.bid,q.ask,q.spread,q.ts.isoformat()))
    def save_candles(self,rows:list[Candle]):
        with self._con() as c:c.executemany("INSERT OR REPLACE INTO signal_agent_candles VALUES(?,?,?,?,?,?,?,?)",[(x.symbol,x.timeframe,x.open_time.isoformat(),x.open,x.high,x.low,x.close,x.volume) for x in rows])
    def health(self,component,status,error=None,metadata=None):
        now=datetime.now(timezone.utc).isoformat(); ok=now if status=="OK" else None; bad=now if status!="OK" else None
        with self._con() as c:c.execute("INSERT INTO signal_agent_runtime VALUES(?,?,?,?,?,?) ON CONFLICT(component) DO UPDATE SET status=excluded.status,last_ok_at=COALESCE(excluded.last_ok_at,last_ok_at),last_error_at=COALESCE(excluded.last_error_at,last_error_at),error_text=excluded.error_text,metadata_json=excluded.metadata_json",(component,status,ok,bad,error,json.dumps(metadata or {},sort_keys=True)))
