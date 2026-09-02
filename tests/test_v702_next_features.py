import tempfile
import unittest
from pathlib import Path
from datetime import datetime

from app import db
from app.autotrade import service
from app.autotrade.trailing_profiles import profile_guide


class NextVersionFeaturesTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.old=db.DB_PATH
        db.DB_PATH=Path(self.tmp.name)/"test.db"
        db.init_db()
        db.upsert_user(77,"u","User")

    def tearDown(self):
        db.DB_PATH=self.old
        self.tmp.cleanup()

    def test_signal_publish_token_is_idempotent(self):
        kwargs=dict(
            market_type="FOREX",symbol="XAUUSD",direction="BUY",entry_price=100,
            stop_loss=90,targets=[110],risk_percent=1,rr_ratio=1,destination="VIP",
            chart_file_id=None,created_by=1,lot_size=None,trailing_code="NEXUS_TRAIL_01",
            trailing_name="Safe Scalping",volume_mode="RISK",publish_token="draft-abc",
        )
        a=db.create_signal(**kwargs)
        b=db.create_signal(**kwargs)
        self.assertEqual(a["id"],b["id"])
        self.assertEqual(len(db.list_active_signals(20)),1)

    def test_volume_mode_is_exposed_to_ea_payload(self):
        row=db.create_signal(
            market_type="FOREX",symbol="XAUUSD",direction="BUY",entry_price=100,
            stop_loss=90,targets=[110],risk_percent=0,rr_ratio=1,destination="VIP",
            chart_file_id=None,created_by=1,lot_size=0.02,trailing_code="NEXUS_TRAIL_01",
            trailing_name="Safe Scalping",volume_mode="FIXED",
        )
        payload=service.signal_to_payload(row)
        self.assertEqual(payload["volume_mode"],"FIXED")
        self.assertEqual(payload["lot_size"],0.02)

    def test_vip_and_autotrade_expire_independently(self):
        vip=db.create_or_extend_license(77,None,30,source="admin",vip_access=True,autotrade_access=False)
        vip_exp=datetime.fromisoformat(vip["vip_expires_at"])
        upgraded=db.create_or_extend_license(77,None,10,source="admin",vip_access=False,autotrade_access=True)
        self.assertEqual(datetime.fromisoformat(upgraded["vip_expires_at"]),vip_exp)
        auto_exp=datetime.fromisoformat(upgraded["autotrade_expires_at"])
        self.assertLess(auto_exp,vip_exp)
        self.assertTrue(db.has_entitlement(77,"vip"))
        self.assertTrue(db.has_entitlement(77,"autotrade"))

    def test_trailing_guide_contains_model_behavior(self):
        text=profile_guide("NEXUS_TRAIL_07","fa")
        self.assertIn("NEXUS Smart Hybrid",text)
        self.assertIn("سر‌به‌سر",text)


if __name__ == "__main__":
    unittest.main()
