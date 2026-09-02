import asyncio
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

from app import db
from app.autotrade.service import AutoTradeError, authorize_mt5
from app.config import settings
from app.services import pricing_service


class V71PricingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = db.DB_PATH
        db.DB_PATH = Path(self.tmp.name) / "test.db"
        db.init_db()
        db.ensure_default_plans(settings.plans)
        db.upsert_user(1, "u", "User")

    def tearDown(self):
        db.DB_PATH = self.old
        self.tmp.cleanup()

    def test_exact_catalog(self):
        expected = {
            "VIP1M": ("25", "0"), "VIP3M": ("69", "0"), "VIP6M": ("129", "0"), "VIP12M": ("239", "0"),
            "AUTO1M": ("30", "0"), "AUTO3M": ("83", "0"), "AUTO6M": ("155", "0"), "AUTO12M": ("289", "0"),
        }
        for code, (price, setup) in expected.items():
            p = db.plan_dict(db.get_plan(code))
            self.assertEqual(p["price_usdt"], price)
            self.assertEqual(p["setup_fee_usdt"], setup)

    def test_rial_rounds_up_and_expires(self):
        db.set_setting("usdt_rial_manual_rate", "1234567")
        invoice = asyncio.run(pricing_service.create_invoice_quote(1, "AUTO6M", "rial"))
        self.assertEqual(invoice["final_amount_rial"], 191357885)
        exp = datetime.fromisoformat(invoice["expires_at"])
        self.assertGreater(exp, datetime.now(timezone.utc))
        self.assertLessEqual(exp, datetime.now(timezone.utc) + timedelta(minutes=16))


    def test_usdt_invoice_does_not_require_rial_rate(self):
        original = pricing_service.get_usdt_rial_rate

        async def fail_if_called():
            raise AssertionError("USDT invoice must not fetch USDT/RIAL rate")

        pricing_service.get_usdt_rial_rate = fail_if_called
        try:
            invoice = asyncio.run(pricing_service.create_invoice_quote(1, "AUTO6M", "usdt"))
        finally:
            pricing_service.get_usdt_rial_rate = original

        self.assertEqual(invoice["payment_method"], "usdt")
        self.assertEqual(invoice["usdt_rial_rate"], None)
        self.assertEqual(invoice["final_amount_rial"], None)
        self.assertEqual(invoice["total_usdt"], 155)

    def test_upgrade_credit_uses_remaining_value(self):
        first = db.create_or_extend_license(1, None, 30, plan_code="VIP1M", source="admin", vip_access=True, autotrade_access=False)
        q = pricing_service.quote_purchase(1, "AUTO6M")
        self.assertEqual(q["mode"], "upgrade")
        self.assertGreater(q["upgrade_credit_usdt"], 0)
        self.assertLess(q["total_usdt"], 155)


class V71AutoTradeSecurityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = db.DB_PATH
        db.DB_PATH = Path(self.tmp.name) / "test.db"
        db.init_db()
        db.ensure_default_plans(settings.plans)
        db.upsert_user(2, "u", "User")

    def tearDown(self):
        db.DB_PATH = self.old
        self.tmp.cleanup()

    def test_cancelled_license_is_hard_revoked(self):
        lic = db.create_or_extend_license(2, None, 30, source="admin", vip_access=True, autotrade_access=True)
        db.bind_mt5_account(2, "123", "Broker", "Server", "0.5.0")
        db.cancel_active_license(2)
        with self.assertRaises(AutoTradeError):
            authorize_mt5(str(lic["license_key"]), "123", bind=False)

    def test_signal_receipt_never_mutates_global_signal_state(self):
        lic = db.create_or_extend_license(2, None, 30, source="admin", vip_access=True, autotrade_access=True)
        db.bind_mt5_account(2, "123", "Broker", "Server", "0.5.0")
        signal = db.create_signal(market_type="FOREX", symbol="EURUSD", direction="BUY", entry_price=1.1, stop_loss=1.09,
                                  targets=[1.12], risk_percent=1, rr_ratio=2, destination="VIP", chart_file_id=None, created_by=2)
        db.set_signal_publish_messages(int(signal["id"]), None, 100)
        db.mark_signal_receipt(int(signal["id"]), 2, status="activated", ticket="1")
        fresh = db.get_signal(int(signal["id"]))
        self.assertEqual(str(fresh["status"]), "DRAFT")

    def test_unpublished_signal_is_not_available_to_autotrade(self):
        lic = db.create_or_extend_license(2, None, 30, source="admin", vip_access=True, autotrade_access=True)
        db.bind_mt5_account(2, "123", "Broker", "Server", "0.5.0")
        signal = db.create_signal(market_type="FOREX", symbol="EURUSD", direction="BUY", entry_price=1.1, stop_loss=1.09,
                                  targets=[1.12], risk_percent=1, rr_ratio=2, destination="VIP", chart_file_id=None, created_by=2)
        rows = db.autotrade_active_signals(0, 50)
        self.assertFalse(any(int(r["id"]) == int(signal["id"]) for r in rows))

    def test_case_insensitive_txid_is_unique(self):
        db.create_payment(2, "VIP1M", 30, "25 USDT", "usdt", "f", "photo", txid="0x" + "a" * 64)
        self.assertTrue(db.txid_exists("0X" + "A" * 64))
        with self.assertRaises(ValueError):
            db.create_payment(2, "VIP1M", 30, "25 USDT", "usdt", "f", "photo", txid="0X" + "A" * 64)
