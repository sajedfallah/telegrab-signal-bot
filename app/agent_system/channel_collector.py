"""Authorized read-only public Telegram channel collector for isolated NEXUS research.

Uses Telethon user session. Never joins channels, sends Telegram messages,
changes channel membership or publishes trade signals.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
import tempfile
from pathlib import Path

from .channel_auditor import CHANNELS, SCHEMA, ingest


def last_message_id(db_path: str, channel: str) -> int:
    with sqlite3.connect(db_path) as db:
        db.executescript(SCHEMA)
        row=db.execute("SELECT MAX(message_id) FROM messages WHERE channel=?", (channel,)).fetchone()
        return int(row[0] or 0)


async def collect_once(client, db_path: str, channels=CHANNELS, limit=100) -> dict:
    """Collect at most limit recent messages per channel; isolate errors."""
    summary={"channels_ok":0,"channels_failed":0,"messages_imported":0,"duplicates":0,"errors":{}}
    for username in channels:
        try:
            # Public username lookup only; never call JoinChannelRequest.
            entity=await client.get_entity(username)
            minimum=last_message_id(db_path,username)
            records=[]
            async for msg in client.iter_messages(entity,limit=limit,min_id=minimum,reverse=True):
                if msg.id and msg.date and msg.message:
                    records.append({"channel":username,"message_id":msg.id,
                                    "posted_at":msg.date.isoformat(),"text":msg.message})
            if records:
                # Reuse the exact auditor ingestion and uniqueness semantics.
                temp_path=None
                try:
                    with tempfile.NamedTemporaryFile(mode="w",encoding="utf-8",
                        suffix=".jsonl",delete=False) as fh:
                        temp_path=Path(fh.name)
                        for row in records: fh.write(json.dumps(row,ensure_ascii=False)+"\n")
                    stats=ingest(db_path,str(temp_path))
                    summary["messages_imported"]+=stats["ingested"]
                    summary["duplicates"]+=stats["duplicate"]
                finally:
                    if temp_path: temp_path.unlink(missing_ok=True)
            summary["channels_ok"]+=1
        except Exception as exc:
            summary["channels_failed"]+=1
            summary["errors"][username]=type(exc).__name__
        await asyncio.sleep(1.0)
    return summary


async def run(args):
    try:
        from telethon import TelegramClient
    except ImportError as exc:
        raise RuntimeError('Install Telethon: python -m pip install "telethon>=1.36,<2"') from exc

    api_id=os.getenv("NEXUS_COLLECTOR_API_ID","").strip()
    api_hash=os.getenv("NEXUS_COLLECTOR_API_HASH","").strip()
    if not api_id.isdecimal() or not api_hash:
        raise RuntimeError("Set NEXUS_COLLECTOR_API_ID and NEXUS_COLLECTOR_API_HASH in user environment")
    session=Path(args.session)
    session.parent.mkdir(parents=True,exist_ok=True)
    Path(args.db).parent.mkdir(parents=True,exist_ok=True)
    # Session is sensitive. Keep it out of Git / production paths.
    async with TelegramClient(str(session),int(api_id),api_hash) as client:
        if not await client.is_user_authorized():
            raise RuntimeError("Collector session not authorized. Run --login once interactively.")
        while True:
            result=await collect_once(client,args.db,limit=args.limit)
            print(json.dumps(result,ensure_ascii=False))
            if args.once: return
            await asyncio.sleep(args.interval)


async def login(args):
    from telethon import TelegramClient
    api_id=os.getenv("NEXUS_COLLECTOR_API_ID","").strip()
    api_hash=os.getenv("NEXUS_COLLECTOR_API_HASH","").strip()
    if not api_id.isdecimal() or not api_hash:
        raise RuntimeError("Collector API ID / Hash must be configured")
    session=Path(args.session)
    session.parent.mkdir(parents=True,exist_ok=True)
    client=TelegramClient(str(session),int(api_id),api_hash)
    try:
        await client.start()  # Interactive login: phone, Telegram OTP, optional 2FA.
        print("COLLECTOR LOGIN: PASS (local session stored; keep file private)")
    finally:
        await client.disconnect()


def main():
    p=argparse.ArgumentParser(description="NEXUS authorized read-only Telegram collection")
    p.add_argument("--db",default="data/channel_audit/channel_audit.db")
    p.add_argument("--session",default="data/channel_audit/nexus_collector")
    p.add_argument("--interval",type=int,default=180)
    p.add_argument("--limit",type=int,default=100)
    p.add_argument("--once",action="store_true")
    p.add_argument("--login",action="store_true")
    args=p.parse_args()
    if args.interval<60 or not 1<=args.limit<=500: p.error("interval >=60, limit 1..500 required")
    asyncio.run(login(args) if args.login else run(args))


if __name__=="__main__":
    main()
