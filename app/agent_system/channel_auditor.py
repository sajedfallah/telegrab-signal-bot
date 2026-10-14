"""NEXUS Channel Auditor V1: offline, read-only channel signal ingestion.

No Telegram user login, scraping, consensus publication or trading.
Imported messages must have a verifiable source ID and timestamp.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

CHANNELS = (
"ssfgold","XAUUSD","learn2tradenews","PrestigeGoldTraders",
"xauusd_trading_scalping_signals","GoldSignalsOfficial","XAUUSDSignalsCore",
"goldwallstreet","XAUUSDTradeInsight","Xauusd_Gold_Scalping_Signal",
"xauusd_signals_scalping","Photon_Trading2023","goldscalpingtrader",
"wolvestrades","Goldsignals","goldtradermo","goldscalperninja",
"elitetradingsignals6","ForexFactory","free_signals",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
 channel TEXT NOT NULL, message_id INTEGER NOT NULL, posted_at TEXT NOT NULL,
 text TEXT NOT NULL, imported_at TEXT NOT NULL,
 PRIMARY KEY(channel,message_id)
);
CREATE TABLE IF NOT EXISTS signals (
 channel TEXT NOT NULL, message_id INTEGER NOT NULL, posted_at TEXT NOT NULL,
 side TEXT, entry_low REAL, entry_high REAL, sl REAL, tp1 REAL,
 classification TEXT NOT NULL, reject_reason TEXT,
 PRIMARY KEY(channel,message_id),
 FOREIGN KEY(channel,message_id) REFERENCES messages(channel,message_id)
);
"""


def parse_signal(text: str) -> dict:
    normalized=text.upper().replace(",", "")
    symbol=bool(re.search(r"\b(XAU\s*/?\s*USD|GOLD)\b",normalized))
    sides=re.findall(r"\b(BUY|SELL|LONG|SHORT)\b",normalized)
    if not symbol or not sides:
        return {"classification":"NOT_SIGNAL","reject_reason":"missing_symbol_or_direction"}
    if len(set("BUY" if s in {"BUY","LONG"} else "SELL" for s in sides)) != 1:
        return {"classification":"REJECT","reject_reason":"conflicting_directions"}
    side="BUY" if sides[0] in {"BUY","LONG"} else "SELL"
    def val(pattern):
        m=re.search(pattern,normalized)
        return float(m.group(1)) if m else None
    sl=val(r"\b(?:SL|STOP\s*LOSS)\s*[:=@ -]+\s*(\d+(?:\.\d+)?)")
    tp=val(r"\b(?:TP1?|TAKE\s*PROFIT\s*1?)\s*[:=@ -]+\s*(\d+(?:\.\d+)?)")
    m=re.search(r"\b(?:ENTRY|BUY|SELL|LONG|SHORT)\s*(?:ZONE)?\s*[:=@ -]+\s*(\d+(?:\.\d+)?)(?:\s*[-–]\s*(\d+(?:\.\d+)?))?",normalized)
    if not m:
        return dict(classification="INCOMPLETE", side=side, reject_reason="entry_not_detected")
    low=float(m.group(1)); high=float(m.group(2)) if m.group(2) else low
    low,high=min(low,high),max(low,high)
    if sl is None or tp is None:
        return dict(classification="INCOMPLETE",side=side,entry_low=low,entry_high=high,sl=sl,tp1=tp,reject_reason="missing_sl_or_tp")
    if (side=="BUY" and (sl>=low or tp<=high)) or (side=="SELL" and (sl<=high or tp>=low)):
        return dict(classification="REJECT",side=side,entry_low=low,entry_high=high,sl=sl,tp1=tp,reject_reason="invalid_trade_geometry")
    return dict(classification="CANDIDATE",side=side,entry_low=low,entry_high=high,sl=sl,tp1=tp,reject_reason=None)


def ingest(db_path: str, source_path: str) -> dict:
    src=Path(source_path)
    if not src.is_file():
        raise FileNotFoundError(src)
    result={"ingested":0,"duplicate":0,"invalid":0}
    with sqlite3.connect(db_path) as con:
        con.executescript(SCHEMA)
        with src.open(encoding="utf-8") as inp:
            for line in inp:
                if not line.strip(): continue
                obj=json.loads(line)
                channel=str(obj.get("channel","")).lstrip("@")
                mid=obj.get("message_id")
                posted=obj.get("posted_at")
                body=obj.get("text")
                if channel not in CHANNELS or type(mid) is not int or mid<=0 or not isinstance(body,str) or not body.strip() or not isinstance(posted,str):
                    result["invalid"]+=1
                    continue
                try:
                    t=datetime.fromisoformat(posted.replace("Z","+00:00"))
                    if t.tzinfo is None: raise ValueError("timezone required")
                except ValueError:
                    result["invalid"]+=1; continue
                now=datetime.now(timezone.utc).isoformat()
                inserted=con.execute("INSERT OR IGNORE INTO messages VALUES (?,?,?,?,?)",(channel,mid,t.astimezone(timezone.utc).isoformat(),body,now)).rowcount
                if not inserted:
                    result["duplicate"]+=1; continue
                parsed=parse_signal(body)
                con.execute("INSERT INTO signals(channel,message_id,posted_at,side,entry_low,entry_high,sl,tp1,classification,reject_reason) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (channel,mid,t.astimezone(timezone.utc).isoformat(),parsed.get("side"),parsed.get("entry_low"),parsed.get("entry_high"),parsed.get("sl"),parsed.get("tp1"),parsed["classification"],parsed.get("reject_reason")))
                result["ingested"]+=1
    return result


def summary(db_path: str) -> list[dict]:
    with sqlite3.connect(db_path) as con:
        rows=con.execute("""SELECT channel,COUNT(*) total,
            SUM(classification='CANDIDATE') candidates,
            SUM(classification='REJECT') rejected,
            SUM(classification='INCOMPLETE') incomplete
            FROM signals GROUP BY channel ORDER BY channel""").fetchall()
    return [dict(channel=r[0],messages=r[1],candidates=r[2],rejected=r[3],incomplete=r[4],
                 verified_win_rate=None,profit_factor=None) for r in rows]


def main():
    p=argparse.ArgumentParser(description="Offline NEXUS XAUUSD channel auditor")
    p.add_argument("--db",default="data/channel_audit/channel_audit.db")
    p.add_argument("--import-jsonl")
    p.add_argument("--summary",action="store_true")
    args=p.parse_args()
    Path(args.db).parent.mkdir(parents=True,exist_ok=True)
    if args.import_jsonl: print(json.dumps(ingest(args.db,args.import_jsonl),ensure_ascii=False))
    if args.summary:
        with sqlite3.connect(args.db) as con: con.executescript(SCHEMA)
        print(json.dumps(summary(args.db),ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
