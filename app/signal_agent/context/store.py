from __future__ import annotations
import sqlite3
class ContextStore:
    def __init__(self,path):self.path=path;self.migrate()
    def _c(self):c=sqlite3.connect(self.path);c.row_factory=sqlite3.Row;return c
    def migrate(self):
        with self._c() as c:c.executescript("""CREATE TABLE IF NOT EXISTS signal_agent_context_snapshots(context_key TEXT PRIMARY KEY,symbol TEXT NOT NULL,as_of TEXT NOT NULL,rule_version TEXT NOT NULL,payload_json TEXT NOT NULL); CREATE TABLE IF NOT EXISTS signal_agent_context_sources(context_key TEXT NOT NULL,event_key TEXT NOT NULL,PRIMARY KEY(context_key,event_key)); CREATE TABLE IF NOT EXISTS signal_agent_context_runtime(symbol TEXT PRIMARY KEY,status TEXT NOT NULL,context_count INTEGER NOT NULL DEFAULT 0,error_text TEXT);""")
    def save(self,s):
        with self._c() as c:
            c.execute("INSERT OR IGNORE INTO signal_agent_context_snapshots VALUES(?,?,?,?,?)",(s.context_key,s.symbol,s.as_of.isoformat(),s.rule_version,s.payload_json()))
            for k in s.source_event_keys:c.execute("INSERT OR IGNORE INTO signal_agent_context_sources VALUES(?,?)",(s.context_key,k))
    def keys(self):
        with self._c() as c:return [r[0] for r in c.execute("SELECT context_key FROM signal_agent_context_snapshots ORDER BY context_key")]
    def health(self,symbol,status,count=0,error=None):
        with self._c() as c:c.execute("INSERT INTO signal_agent_context_runtime VALUES(?,?,?,?) ON CONFLICT(symbol) DO UPDATE SET status=excluded.status,context_count=excluded.context_count,error_text=excluded.error_text",(symbol,status,count,error))
    def runtime(self,symbol):
        with self._c() as c:
            r=c.execute("SELECT * FROM signal_agent_context_runtime WHERE symbol=?",(symbol,)).fetchone();return dict(r) if r else None
