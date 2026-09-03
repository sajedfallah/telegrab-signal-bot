from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

from app.services import report_runtime


class FakeDB:
    def __init__(self):
        self.con = sqlite3.connect(":memory:")
        self.con.row_factory = sqlite3.Row
        self.con.executescript(
            """
            CREATE TABLE signals (
                id INTEGER PRIMARY KEY,
                code TEXT,
                market_type TEXT,
                destination TEXT,
                status TEXT,
                created_at TEXT,
                closed_at TEXT,
                result_value REAL,
                free_message_id INTEGER,
                vip_message_id INTEGER
            );
            CREATE TABLE autotrade_trade_executions (
                id INTEGER PRIMARY KEY,
                signal_id INTEGER,
                event_type TEXT,
                profit REAL,
                created_at TEXT
            );
            """
        )

    @contextmanager
    def conn(self):
        yield self.con


class FakeMain:
    def __init__(self):
        self.db = FakeDB()
        self.settings = SimpleNamespace(
            free_channel_target=-100101,
            vip_channel_id=-100202,
            public_channel_id=-100303,
        )

    @staticmethod
    def tr(lang, fa, en):
        return fa if lang == "fa" else en

    @staticmethod
    def _period_utc(start_local, end_local):
        return start_local.astimezone(timezone.utc).isoformat(), end_local.astimezone(timezone.utc).isoformat()


def _seed_gold_close(main: FakeMain):
    con = main.db.con
    con.execute(
        """INSERT INTO signals
           (id,code,market_type,destination,status,created_at,closed_at,result_value,free_message_id,vip_message_id)
           VALUES(1,'NX-0001','GOLD','BOTH','CLOSED',?,?,?,?,1,2)""",
        (
            "2026-09-03T05:42:00+00:00",
            "2026-09-03T06:28:16+00:00",
            -113.4,
        ),
    )
    con.execute(
        """INSERT INTO autotrade_trade_executions
           (id,signal_id,event_type,profit,created_at)
           VALUES(1,1,'CLOSE',-10.64,'2026-09-03T06:28:16+00:00')"""
    )
    con.commit()


def test_gold_trade_is_not_dropped_from_unified_free_or_vip_report():
    main = FakeMain()
    _seed_gold_close(main)
    start = "2026-09-03T00:00:00+00:00"
    end = "2026-09-04T00:00:00+00:00"

    free = report_runtime.unified_report_stats(main, start, end, "FREE")
    vip = report_runtime.unified_report_stats(main, start, end, "VIP")

    for stats in (free, vip):
        assert stats["issued"] == 1
        assert stats["closed"] == 1
        assert stats["wins"] == 0
        assert stats["losses"] == 1
        assert stats["be"] == 0
        assert stats["win_rate"] == 0.0
        assert stats["broker_pnl"] == -10.64
        assert stats["broker_pnl_available"] == 1


def test_channel_report_has_one_market_agnostic_summary_card():
    main = FakeMain()
    _seed_gold_close(main)
    start = datetime(2026, 9, 3, tzinfo=timezone.utc)
    end = datetime(2026, 9, 4, tzinfo=timezone.utc)

    text = report_runtime.render_channel_report(main, "daily", start, end, "fa", "VIP")

    assert "سیگنال‌های صادرشده: <b>1</b>" in text
    assert "معاملات بسته‌شده: <b>1</b>" in text
    assert "🔴 LOSS: <b>1</b>" in text
    assert "💰 Broker P/L: <b>-10.64</b>" in text
    assert "کریپتو" not in text
    assert "فارکس" not in text
    assert "Crypto" not in text
    assert "Forex" not in text


def test_report_routing_matches_free_vip_public_policy():
    main = FakeMain()

    assert report_runtime.channel_targets(main, "FREE") == (-100101,)
    assert report_runtime.channel_targets(main, "VIP") == (-100202, -100303)
