from pathlib import Path
import tempfile
import unittest
from fastapi.testclient import TestClient

from app import db
from app.autotrade import api
from app.autotrade import service
from app.config import settings


class V058FinalHardeningNextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = db.DB_PATH
        db.DB_PATH = Path(self.tmp.name) / "test.db"
        db.init_db()
        self.client = TestClient(api.app)
        db.upsert_user(10, "u", "User")

    def tearDown(self):
        db.DB_PATH = self.old
        self.tmp.cleanup()

    def test_vip_only_signal_is_visible_to_autotrade(self):
        row = db.create_signal(
            market_type="CRYPTO", symbol="BTCUSD", direction="LONG",
            entry_price=100.0, stop_loss=90.0, targets=[120.0], risk_percent=1.0,
            rr_ratio=2.0, destination="VIP", chart_file_id=None, created_by=10,
        )
        db.set_signal_status(int(row["id"]), "ACTIVE")
        db.set_signal_publish_messages(int(row["id"]), None, 12345)
        # v0.6.0: Telegram-originated signals are legacy and are no longer
        # eligible for AutoTrade distribution. Only MT5_ADMIN signals qualify.
        rows = db.autotrade_active_signals(0, 50)
        self.assertEqual([int(r["id"]) for r in rows], [])

    def test_license_extension_rolls_back_supersede_on_insert_failure(self):
        lic = db.create_or_extend_license(10, None, 30, plan_code="AUTO1M")
        old_id = int(lic["id"])
        with db.conn() as con:
            con.execute("CREATE TRIGGER fail_license_insert BEFORE INSERT ON licenses BEGIN SELECT RAISE(ABORT, 'forced'); END")
        with self.assertRaises(Exception):
            db.create_or_extend_license(10, None, 30, plan_code="AUTO1M")
        with db.conn() as con:
            row = con.execute("SELECT status FROM licenses WHERE id=?", (old_id,)).fetchone()
        self.assertEqual(row["status"], "active")

    def test_invalid_license_activation_is_403(self):
        response = self.client.get("/api/v1/autotrade/activate", headers={"X-License-Key": "BAD", "X-MT5-Account": "123456"})
        self.assertEqual(response.status_code, 403, response.text)

    def test_invalid_license_check_is_403(self):
        response = self.client.get("/api/v1/autotrade/license/check", headers={"X-License-Key": "BAD", "X-MT5-Account": "123456"})
        self.assertEqual(response.status_code, 403, response.text)

    def test_catalog_prices_are_numeric_and_consistent(self):
        db.ensure_default_plans(settings.plans)
        for code, expected in {"VIP12M":"239", "AEX1M":"5", "AEX3M":"14", "AEX6M":"27", "AEX12M":"49"}.items():
            row = db.get_plan(code)
            self.assertEqual(str(row["price_usdt"]), expected)
            self.assertEqual(str(row["canonical_price_usdt"]), expected)

    def test_api_release_version_is_project_version(self):
        self.assertEqual(api.API_VERSION, "0.6.5")

    def test_stop_limit_is_accepted_by_signal_model(self):
        row = db.create_signal(
            market_type="CRYPTO", symbol="BTCUSD", direction="LONG",
            entry_price=100.0, stop_loss=90.0, targets=[120.0], risk_percent=1.0,
            rr_ratio=2.0, destination="VIP", chart_file_id=None, created_by=10,
            order_type="BUY_STOP_LIMIT", stop_limit_price=101.0,
        )
        self.assertEqual(row["order_type"], "BUY_STOP_LIMIT")
        self.assertEqual(float(row["stop_limit_price"]), 101.0)

if __name__ == "__main__":
    unittest.main()

def test_manual_mt5_events_use_unified_caption_engine():
    text = (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text(encoding="utf-8")
    block = text[text.index('async def _process_mt5_trade_event'):]
    assert '_signal_caption(row, get_lang(uid), status="PENDING")' in block
    assert '_signal_caption(row, get_lang(uid), status="ACTIVE")' in block
    assert 'f"🟠 <b>{escape(label)} SIGNAL</b>\\\\n"' not in block
    assert 'f"🟢 <b>{escape(ot_label)} SIGNAL</b>\\\\n"' not in block


def test_mt5_supports_all_pending_order_types_and_signal_timeframe():
    root = Path(__file__).resolve().parents[1]
    ea = (root / "mt5" / "NEXUS_AutoTrade" / "NEXUS_AutoTrade.mq5").read_text(encoding="utf-8")
    tm = (root / "mt5" / "NEXUS_AutoTrade" / "Include" / "TradeManager.mqh").read_text(encoding="utf-8")
    parser = (root / "mt5" / "NEXUS_AutoTrade" / "Include" / "SignalParser.mqh").read_text(encoding="utf-8")
    for token in ["BUY_LIMIT", "SELL_LIMIT", "BUY_STOP", "SELL_STOP", "BUY_STOP_LIMIT", "SELL_STOP_LIMIT"]:
        assert token in ea or token in tm
    assert 's.timeframe=NexusJsonString(obj,"timeframe","M5")' in parser
    assert 'NexusTimeframeFromString(s.timeframe)' in tm
    assert 'timeframe_code' in (root / "mt5" / "NEXUS_AutoTrade" / "Include" / "TradeManager.mqh").read_text(encoding="utf-8")


def test_mt5_license_config_is_terminal_local_not_common():
    ea = (Path(__file__).resolve().parents[1] / "mt5" / "NEXUS_AutoTrade" / "NEXUS_AutoTrade.mq5").read_text(encoding="utf-8")
    config_block = ea[ea.index('bool SaveUserConfig'):ea.index('void UISetLabel')]
    assert 'FILE_COMMON' not in config_block
