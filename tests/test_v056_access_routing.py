
import unittest
from pathlib import Path
import tempfile

from app import db
from app.autotrade.service import authorize_standard_mt5


ROOT = Path(__file__).parents[1]


class V056AccessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = db.DB_PATH
        db.DB_PATH = Path(self.tmp.name) / "test.db"
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self.old
        self.tmp.cleanup()

    def test_standard_mode_is_available_without_license(self):
        auth = authorize_standard_mt5("80127028", broker="ePlanet", server="ePlanet-MT5")
        self.assertEqual(auth["mode"], "STANDARD")
        self.assertEqual(auth["license_status"], "STANDARD")
        self.assertTrue(auth["allow_signal_receive"])
        self.assertTrue(auth["allow_new_trade"])
        self.assertTrue(auth["allow_manage_trade"])
        self.assertFalse(auth["allow_advanced_settings"])
        self.assertFalse(auth["allow_manual_signal"])

    def test_manual_destination_claim_is_atomic(self):
        row = db.create_signal(
            market_type="FOREX", symbol="XAUUSD", direction="LONG",
            entry_price=4500, stop_loss=4490, targets=[4520],
            risk_percent=0, rr_ratio=2, destination="VIP",
            chart_file_id=None, created_by=1, lot_size=0.01,
            volume_mode="FIXED", publish_token="MT5MANUAL-9001"
        )
        self.assertTrue(db.claim_signal_channel(int(row["id"]), "VIP"))
        self.assertFalse(db.claim_signal_channel(int(row["id"]), "VIP"))
        db.release_signal_channel_claim(int(row["id"]), "VIP")
        self.assertTrue(db.claim_signal_channel(int(row["id"]), "VIP"))

    def test_manual_publish_token_is_idempotent(self):
        kwargs = dict(
            market_type="FOREX", symbol="XAUUSD", direction="LONG",
            entry_price=4500, stop_loss=4490, targets=[4520],
            risk_percent=0, rr_ratio=2, destination="VIP",
            chart_file_id=None, created_by=1, lot_size=0.01,
            volume_mode="FIXED", publish_token="MT5MANUAL-9002"
        )
        a = db.create_signal(**kwargs)
        b = db.create_signal(**kwargs)
        self.assertEqual(int(a["id"]), int(b["id"]))


class V056StaticTests(unittest.TestCase):
    def test_ea_has_access_state_machine_and_standard_startup(self):
        src = (ROOT / "mt5" / "NEXUS_AutoTrade" / "NEXUS_AutoTrade.mq5").read_text(encoding="utf-8")
        for token in [
            "NEXUS_STANDARD", "NEXUS_LICENSED", "NEXUS_ADMIN",
"LICENSED USER", "ADMIN MODE",
            'g_access_mode=NEXUS_STANDARD',
            'g_manual_destination="NONE"',
        ]:
            self.assertIn(token, src)

    def test_manual_publish_is_admin_only(self):
        src = (ROOT / "mt5" / "NEXUS_AutoTrade" / "NEXUS_AutoTrade.mq5").read_text(encoding="utf-8")
        self.assertIn('g_access_mode==NEXUS_ADMIN', src)
        self.assertIn('if(magic!=InpMagicNumber && g_access_mode==NEXUS_ADMIN)', src)

    def test_backend_has_standard_capability_contract(self):
        src = (ROOT / "app" / "autotrade" / "api.py").read_text(encoding="utf-8")
        self.assertIn("authorize_standard_mt5", src)
        self.assertIn('"allow_manual_signal"', src)
        self.assertIn('"mode"', src)


if __name__ == "__main__":
    unittest.main()
