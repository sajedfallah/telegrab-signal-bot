import json
import sqlite3
from datetime import datetime, timezone

from app.agent_system.channel_auditor import CHANNELS, ingest, parse_signal, summary


def test_twenty_unique_channel_candidates():
    assert len(CHANNELS) == 20
    assert len(set(CHANNELS)) == 20


def test_parser_accepts_structurally_valid_xauusd_signal():
    parsed=parse_signal("XAUUSD BUY 4142.0 SL 4139.0 TP1 4148.0")
    assert parsed["classification"] == "CANDIDATE"
    assert parsed["side"] == "BUY"


def test_parser_rejects_invalid_buy_stop():
    parsed=parse_signal("GOLD BUY 4142 SL 4150 TP1 4160")
    assert parsed["classification"] == "REJECT"
    assert parsed["reject_reason"] == "invalid_trade_geometry"


def test_parser_rejects_missing_or_conflicting_inputs():
    assert parse_signal("XAUUSD BUY SELL 4142 SL 4139 TP1 4148")["classification"] == "REJECT"
    assert parse_signal("XAUUSD SELL 4142")["classification"] == "INCOMPLETE"


def test_import_is_idempotent_and_persists_raw_messages(tmp_path):
    src=tmp_path/"input.jsonl"
    obj=dict(channel="ssfgold",message_id=17,posted_at="2026-10-14T10:00:00Z",
             text="XAUUSD SELL 4142 SL 4146 TP1 4134")
    src.write_text(json.dumps(obj)+"\n"+json.dumps(obj)+"\n",encoding="utf-8")
    db=str(tmp_path/"audit.db")
    result=ingest(db,str(src))
    assert result == {"ingested":1,"duplicate":1,"invalid":0}
    assert summary(db)[0]["candidates"] == 1
    assert summary(db)[0]["verified_win_rate"] is None
    with sqlite3.connect(db) as con:
        assert con.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 1
