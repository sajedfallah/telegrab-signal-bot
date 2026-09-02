import tempfile
import unittest
from pathlib import Path

from app import db
from app.autotrade import service


class AutoTradeBackendTests(unittest.TestCase):
    def setUp(self):
        self.old_path = db.DB_PATH
        self.tmp = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(self.tmp.name) / "test.db"
        db.init_db()
        db.upsert_user(1001, "tester", "Tester")
        self.license = db.create_or_extend_license(1001, None, 30, source="admin", autotrade_access=True, vip_access=True)

    def tearDown(self):
        db.DB_PATH = self.old_path
        self.tmp.cleanup()

    def test_license_key_created_and_mt5_binding_is_single_account(self):
        key = self.license["license_key"]
        self.assertTrue(str(key).startswith("NXS-"))
        result = service.authorize_mt5(key, "123456", bind=True, broker="Demo", server="Demo-1", ea_version="0.1")
        self.assertEqual(result["license_status"], "ACTIVE")
        with self.assertRaises(service.AutoTradeError):
            service.authorize_mt5(key, "999999", bind=True, broker="Demo", server="Demo-1")

    def test_signal_payload_uses_existing_signal_engine(self):
        row = db.create_signal(
            market_type="FOREX", symbol="XAUUSD", direction="BUY", entry_price=3345.5,
            stop_loss=3338.0, targets=[3350.0, 3355.0], risk_percent=1.0, rr_ratio=2.2,
            destination="VIP", chart_file_id=None, created_by=1001, lot_size=0.10,
            trailing_code="NEXUS_TRAIL_04", trailing_name="Market Structure",
        )
        payload = service.signal_to_payload(row)
        self.assertEqual(payload["signal_id"], row["code"])
        self.assertEqual(payload["tp3"], None)
        self.assertEqual(payload["trailing_config"]["code"], "NEXUS_TRAIL_04")

    def test_signal_update_creates_machine_command(self):
        row = db.create_signal(
            market_type="FOREX", symbol="EURUSD", direction="SELL", entry_price=1.10,
            stop_loss=1.11, targets=[1.09], risk_percent=1.0, rr_ratio=1.0,
            destination="VIP", chart_file_id=None, created_by=1001, lot_size=0.10,
            trailing_code="NEXUS_TRAIL_01", trailing_name="Safe Scalping",
        )
        db.add_signal_update(int(row["id"]), "BREAK_EVEN", "x", "x", None, 1001)
        cmds = db.autotrade_commands()
        self.assertEqual(len(cmds), 1)
        self.assertEqual(cmds[0]["command"], "MOVE_SL_TO_ENTRY")


if __name__ == "__main__":
    unittest.main()


def test_mt5_signal_feed_is_not_restricted_to_forex():
    sql = (Path(__file__).resolve().parents[1] / "app" / "db.py").read_text(encoding="utf-8")
    start = sql.index("def autotrade_active_signals")
    block = sql[start:sql.index("def autotrade_commands", start)]
    assert "market_type='FOREX'" not in block

