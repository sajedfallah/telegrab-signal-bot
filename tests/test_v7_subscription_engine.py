import tempfile
import unittest
from pathlib import Path
from datetime import datetime

from app import db
from app.services import analytics_service


class SubscriptionEngineV7Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = db.DB_PATH
        db.DB_PATH = Path(self.tmp.name) / "test.db"
        db.init_db()
        db.create_plan("VIP30", 30, "VIP 30", "VIP 30", "3.000.000 تومان", vip_access=True, autotrade_access=False, renewal_discount_percent=10)
        db.create_plan("PRO30", 30, "PRO 30", "PRO 30", "5.000.000 تومان", vip_access=True, autotrade_access=True, renewal_discount_percent=15)
        db.upsert_user(100, "u", "User")

    def tearDown(self):
        db.DB_PATH = self.old
        self.tmp.cleanup()

    def test_plan_entitlements_and_renewal_settings(self):
        p = db.get_plan("VIP30")
        self.assertTrue(bool(p["vip_access"]))
        self.assertFalse(bool(p["autotrade_access"]))
        self.assertEqual(float(p["renewal_discount_percent"]), 10)
        db.update_plan_entitlement("VIP30", "auto", True)
        db.update_plan_renewal_discount("VIP30", 20)
        p = db.get_plan("VIP30")
        self.assertTrue(bool(p["autotrade_access"]))
        self.assertEqual(float(p["renewal_discount_percent"]), 20)

    def test_upgrade_preserves_remaining_time_and_adds_access(self):
        first = db.create_or_extend_license(100, None, 30, plan_code="VIP30", source="admin", vip_access=True, autotrade_access=False)
        first_exp = datetime.fromisoformat(first["expires_at"])
        upgraded = db.create_or_extend_license(100, None, 30, plan_code="PRO30", source="admin", vip_access=True, autotrade_access=True)
        second_exp = datetime.fromisoformat(upgraded["expires_at"])
        self.assertGreaterEqual((second_exp - first_exp).total_seconds(), 29 * 86400)
        self.assertTrue(db.has_entitlement(100, "vip"))
        self.assertTrue(db.has_entitlement(100, "autotrade"))
        self.assertEqual(first["id"] + 1, upgraded["id"])

    def test_paid_license_snapshots_plan_code_and_access(self):
        pid = db.create_payment(100, "VIP30", 30, "3.000.000 تومان", "irr", "f", "photo", final_amount_irr=3000000)
        db.review_payment(pid, "approved", 1)
        lic = db.create_or_extend_license(100, pid, 30, plan_code="VIP30", source="payment", vip_access=True, autotrade_access=False)
        self.assertEqual(lic["plan_code"], "VIP30")
        self.assertEqual(lic["source"], "payment")
        self.assertTrue(bool(lic["vip_access"]))
        self.assertFalse(bool(lic["autotrade_access"]))


class AnalyticsV7Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = db.DB_PATH
        db.DB_PATH = Path(self.tmp.name) / "test.db"
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self.old
        self.tmp.cleanup()

    def _signal(self, symbol, dest, trailing, result, entry=100, exit_price=110):
        row = db.create_signal(
            market_type="FOREX", symbol=symbol, direction="BUY", entry_price=entry,
            stop_loss=90, targets=[120], risk_percent=1, rr_ratio=2,
            destination=dest, chart_file_id=None, created_by=1,
            lot_size=0.1, trailing_code=trailing, trailing_name=trailing,
        )
        db.close_signal(int(row["id"]), exit_price, result, "PIPS", None)

    def test_analytics_groups_symbols_trailing_and_channels(self):
        self._signal("XAUUSD", "FREE", "NEXUS_TRAIL_01", 10)
        self._signal("XAUUSD", "BOTH", "NEXUS_TRAIL_01", -5, exit_price=95)
        self._signal("EURUSD", "VIP", "NEXUS_TRAIL_04", 20)
        overview = analytics_service.overview("all")
        self.assertEqual(overview["total"], 3)
        self.assertEqual(overview["wins"], 2)
        syms = {r["symbol"]: r for r in analytics_service.symbols("all")}
        self.assertEqual(syms["XAUUSD"]["total"], 2)
        trails = {r["code"]: r for r in analytics_service.trailing("all")}
        self.assertEqual(trails["NEXUS_TRAIL_01"]["total"], 2)
        channels = analytics_service.channels("all")
        self.assertEqual(channels["FREE"]["total"], 2)
        self.assertEqual(channels["VIP"]["total"], 2)


if __name__ == "__main__":
    unittest.main()
