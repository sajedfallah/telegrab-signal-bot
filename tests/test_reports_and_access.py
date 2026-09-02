import os
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone, timedelta

from app import db


class ReportAccessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = db.DB_PATH
        db.DB_PATH = Path(self.tmp.name) / 'test.db'
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self.old
        self.tmp.cleanup()

    def _signal(self, dest, direction, entry, exit_price, result):
        row = db.create_signal(
            market_type='FOREX', symbol='EURUSD', direction=direction,
            entry_price=entry, stop_loss=entry - 0.01 if direction == 'BUY' else entry + 0.01,
            targets=[entry + 0.02 if direction == 'BUY' else entry - 0.02],
            risk_percent=1, rr_ratio=2, destination=dest, chart_file_id=None, created_by=1,
            lot_size=0.1, trailing_code='NEXUS_TRAIL_01', trailing_name='Safe Scalping'
        )
        db.close_signal(int(row['id']), exit_price, result, 'PIPS', None)
        return row

    def test_channel_stats_keep_free_and_vip_separate(self):
        self._signal('FREE', 'BUY', 100, 110, 10)
        self._signal('VIP', 'SELL', 100, 90, 10)
        self._signal('BOTH', 'BUY', 100, 95, -5)
        start = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        end = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        free = db.channel_performance_stats(start, end, 'FREE')
        vip = db.channel_performance_stats(start, end, 'VIP')
        self.assertEqual(free['total'], 2)
        self.assertEqual(vip['total'], 2)
        self.assertEqual((free['wins'], free['losses']), (1, 1))
        self.assertEqual((vip['wins'], vip['losses']), (1, 1))
        self.assertAlmostEqual(free['net_pct'], 5.0, places=2)
        self.assertAlmostEqual(vip['net_pct'], 5.0, places=2)

    def test_paid_license_history_excludes_admin_free_license(self):
        uid = 123
        db.upsert_user(uid, 'u', 'User')
        pid = db.create_payment(uid, '30', 30, '3.000.000 تومان', 'irr', 'file', 'photo', final_amount_irr=3000000)
        self.assertTrue(db.review_payment(pid, 'approved', 1))
        db.create_or_extend_license(uid, pid, 30)
        db.admin_extend_license(uid, 7)
        history = db.user_paid_license_history(uid)
        self.assertEqual(len(history), 1)
        self.assertEqual(int(history[0]['payment_id']), pid)


class StaticUxTests(unittest.TestCase):
    def test_channel_report_contains_both_sections(self):
        src = (Path(__file__).parents[1] / 'app' / 'main.py').read_text(encoding='utf-8')
        self.assertIn('کانال عمومی', src)
        self.assertIn('کانال VIP', src)
        self.assertIn('Public Channel', src)
        self.assertIn('VIP Channel', src)

    def test_startup_catchup_is_disabled_by_default(self):
        cfg = (Path(__file__).parents[1] / 'app' / 'config.py').read_text(encoding='utf-8')
        self.assertIn('REPORT_CATCHUP_ENABLED', cfg)
        self.assertIn('"false"', cfg)

    def test_client_menu_order(self):
        ui = (Path(__file__).parents[1] / 'app' / 'ui.py').read_text(encoding='utf-8')
        main_menu_src = ui[ui.index('def main_menu'):ui.index('def guide_hub_menu')]
        for label in ['سیگنال', 'حساب من', 'خرید اشتراک', 'راهنما', 'پشتیبانی', 'تغییر زبان']:
            self.assertIn(label, main_menu_src)
        self.assertNotIn('معاملات خودکار', main_menu_src)
        self.assertNotIn('دعوت و امتیاز', main_menu_src)
        self.assertNotIn('⭐ Referral & Points', main_menu_src)
        account_src = ui[ui.index('def account_menu'):ui.index('def referral_menu')]
        self.assertIn('پرداخت‌های من', account_src)
        self.assertIn('دعوت دوستان', account_src)


if __name__ == '__main__':
    unittest.main()
