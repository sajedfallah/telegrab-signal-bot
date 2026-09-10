from __future__ import annotations

import asyncio
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

from app.services import report_runtime


class FakeDB:
    def __init__(self):
        # report_runtime renders scheduled reports via asyncio.to_thread().
        # Production db.conn() opens a connection inside the worker thread,
        # but this in-memory test double intentionally reuses one connection.
        # Allow that fixture connection to be read from the worker thread so
        # the test models production behavior instead of failing on SQLite's
        # default thread-affinity guard.
        self.con = sqlite3.connect(":memory:", check_same_thread=False)
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
        self.claimed: set[tuple[str, str, str]] = set()
        self.sent: set[tuple[str, str, str]] = set()

    @contextmanager
    def conn(self):
        yield self.con

    def claim_report_dispatch(self, report_type, period_key, recipient_key, start_iso, end_iso):
        key = (str(report_type), str(period_key), str(recipient_key))
        if key in self.claimed:
            return False
        self.claimed.add(key)
        return True

    def mark_report_sent(self, report_type, period_key, recipient_key, start_iso, end_iso):
        self.sent.add((str(report_type), str(period_key), str(recipient_key)))

    def release_report_dispatch(self, report_type, period_key, recipient_key):
        self.claimed.discard((str(report_type), str(period_key), str(recipient_key)))


class FakeMain:
    def __init__(self):
        self.db = FakeDB()
        self.settings = SimpleNamespace(
            free_channel_target=-100101,
            vip_channel_id=-100202,
            public_channel_id=-100303,
            channel_reports_enabled=True,
            channel_content_language="fa",
        )

    @staticmethod
    def tr(lang, fa, en):
        return fa if lang == "fa" else en

    @staticmethod
    def _period_utc(start_local, end_local):
        return start_local.astimezone(timezone.utc).isoformat(), end_local.astimezone(timezone.utc).isoformat()


class FakeBot:
    def __init__(self):
        self.calls: list[dict] = []

    async def send_message(self, target, text, **kwargs):
        self.calls.append({"target": target, "text": text, **kwargs})


def _seed_gold_close(main: FakeMain):
    con = main.db.con
    con.execute(
        """INSERT INTO signals
           (id,code,market_type,destination,status,created_at,closed_at,result_value,free_message_id,vip_message_id)
           VALUES(1,'NX-0001','GOLD','BOTH','CLOSED',?,?,?,1,2)""",
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


def test_public_daily_report_has_clear_independent_free_and_vip_sections():
    main = FakeMain()
    _seed_gold_close(main)
    start = datetime(2026, 9, 3, tzinfo=timezone.utc)
    end = datetime(2026, 9, 4, tzinfo=timezone.utc)

    text = report_runtime.render_public_daily_report(main, start, end, "fa")

    assert "گزارش روزانه کانال‌های سیگنال" in text
    assert "🆓 NEXUS FREE SIGNAL" in text
    assert "👑 NEXUS VIP SIGNAL" in text
    assert text.count("سیگنال‌های صادرشده: <b>1</b>") == 2
    assert text.count("معاملات بسته‌شده: <b>1</b>") == 2
    assert text.count("🔴 LOSS: <b>1</b>") == 2
    assert "آمار FREE و VIP به‌صورت مستقل" in text


def test_daily_send_keeps_channel_reports_and_sends_one_combined_public_post():
    main = FakeMain()
    _seed_gold_close(main)
    bot = FakeBot()
    start = datetime(2026, 9, 3, tzinfo=timezone.utc)
    end = datetime(2026, 9, 4, tzinfo=timezone.utc)

    asyncio.run(report_runtime.send_channel_report(main, bot, "daily", "2026-09-03", start, end))

    assert [call["target"] for call in bot.calls] == [-100101, -100202, -100303]
    public_calls = [call for call in bot.calls if call["target"] == -100303]
    assert len(public_calls) == 1
    assert "🆓 NEXUS FREE SIGNAL" in public_calls[0]["text"]
    assert "👑 NEXUS VIP SIGNAL" in public_calls[0]["text"]
    assert "NEXUS گزارش روزانه — VIP" not in public_calls[0]["text"]
    assert ("daily_public_channels_v3", "2026-09-03", "-100303") in main.db.sent


def test_daily_public_dispatch_is_idempotent():
    main = FakeMain()
    _seed_gold_close(main)
    bot = FakeBot()
    start = datetime(2026, 9, 3, tzinfo=timezone.utc)
    end = datetime(2026, 9, 4, tzinfo=timezone.utc)

    asyncio.run(report_runtime.send_channel_report(main, bot, "daily", "2026-09-03", start, end))
    asyncio.run(report_runtime.send_channel_report(main, bot, "daily", "2026-09-03", start, end))

    assert len([call for call in bot.calls if call["target"] == -100303]) == 1
    assert len(bot.calls) == 3


def test_report_routing_matches_free_vip_public_policy():
    main = FakeMain()

    assert report_runtime.channel_targets(main, "FREE") == (-100101,)
    assert report_runtime.channel_targets(main, "VIP") == (-100202, -100303)
