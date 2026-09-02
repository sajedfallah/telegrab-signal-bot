import base64
import math
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app import db
from app.autotrade import api
from app.autotrade import service


class P0HardeningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = db.DB_PATH
        db.DB_PATH = Path(self.tmp.name) / "test.db"
        db.init_db()
        self.client = TestClient(api.app)

    def tearDown(self):
        db.DB_PATH = self.old
        self.tmp.cleanup()

    def test_standard_signal_polling_uses_standard_authorization(self):
        response = self.client.get(
            "/api/v1/autotrade/signals",
            headers={"X-MT5-Account": "123456"},
        )
        self.assertEqual(response.status_code, 403, response.text)

    def test_standard_command_polling_uses_standard_authorization(self):
        response = self.client.get(
            "/api/v1/autotrade/commands",
            headers={"X-MT5-Account": "123456"},
        )
        self.assertEqual(response.status_code, 403, response.text)

    def test_create_signal_rejects_invalid_long_geometry(self):
        with self.assertRaises(ValueError):
            db.create_signal(
                market_type="FOREX", symbol="XAUUSD", direction="BUY",
                entry_price=100, stop_loss=101, targets=[110], risk_percent=1,
                rr_ratio=1, destination="VIP", chart_file_id=None, created_by=1,
            )

    def test_create_signal_rejects_unordered_targets(self):
        with self.assertRaises(ValueError):
            db.create_signal(
                market_type="FOREX", symbol="XAUUSD", direction="SELL",
                entry_price=100, stop_loss=110, targets=[90, 95], risk_percent=1,
                rr_ratio=1, destination="VIP", chart_file_id=None, created_by=1,
            )

    def test_trade_event_rejects_non_finite_numbers(self):
        payload = {
            "license_key": "",
            "account_number": "123456",
            "event": "OPEN",
            "ticket": "123",
            "symbol": "XAUUSD",
            "direction": "LONG",
            "volume": 0.1,
            "entry_price": math.nan,
            "stop_loss": 90,
            "take_profit": 110,
        }
        with self.assertRaises(ValueError):
            api.TradeEventRequest(**payload)

    def test_trade_event_rejects_bad_geometry(self):
        payload = {
            "account_number": "123456",
            "event": "OPEN",
            "ticket": "123",
            "symbol": "XAUUSD",
            "direction": "LONG",
            "volume": 0.1,
            "entry_price": 100,
            "stop_loss": 101,
            "take_profit": 110,
        }
        response = self.client.post("/api/v1/autotrade/trade-event", json=payload)
        self.assertEqual(response.status_code, 403)

    def test_trade_event_rejects_fake_image(self):
        fake = base64.b64encode(b"\x89PNG\r\n\x1a\nnot-an-image").decode()
        payload = {
            "account_number": "123456",
            "event": "CLOSE",
            "ticket": "123",
            "symbol": "XAUUSD",
            "direction": "LONG",
            "chart_base64": fake,
        }
        response = self.client.post("/api/v1/autotrade/trade-event", json=payload)
        self.assertEqual(response.status_code, 403)

    def test_standard_service_helpers_are_consistent(self):
        with self.assertRaises(service.AutoTradeError):
            service.active_signals("", "123456")
        with self.assertRaises(service.AutoTradeError):
            service.pending_commands("", "123456")

    def test_trade_event_legacy_id_is_deterministic(self):
        payload = {
            "event": "CLOSE", "ticket": "123", "signal_id": "NX-1",
            "symbol": "XAUUSD", "direction": "LONG", "volume": 0.1,
            "entry_price": 100.0, "stop_loss": 90.0, "take_profit": 110.0,
            "exit_price": 109.0, "profit": 9.0, "event_time_ms": 12345,
        }
        db.upsert_user(0, "standard", "Standard")
        db.enqueue_autotrade_trade_event(0, "CLOSE", payload, "123")
        db.enqueue_autotrade_trade_event(0, "CLOSE", payload, "123")
        with db.conn() as con:
            rows = con.execute("SELECT event_id FROM autotrade_trade_executions").fetchall()
        self.assertEqual(len(rows), 1)


class SourceHardeningTests(unittest.TestCase):
    ROOT = Path(__file__).parents[1]

    def test_mq5_contains_no_embedded_admin_secret(self):
        src = (self.ROOT / "mt5" / "NEXUS_AutoTrade" / "NEXUS_AutoTrade.mq5").read_text(encoding="utf-8")
        self.assertNotIn("#define NEXUS_ADMIN_TOKEN", src)
        self.assertNotIn("#define NEXUS_ADMIN_MT5_ACCOUNT", src)
        self.assertIn("EffectiveAdminToken", src)

    def test_network_reporting_is_not_called_from_on_tick(self):
        src = (self.ROOT / "mt5" / "NEXUS_AutoTrade" / "NEXUS_AutoTrade.mq5").read_text(encoding="utf-8")
        on_tick = src.split("void OnTick()", 1)[1].split("void OnTradeTransaction", 1)[0]
        self.assertNotIn("DetectPositionModifications();", on_tick)


if __name__ == "__main__":
    unittest.main()
