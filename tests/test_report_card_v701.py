import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from io import BytesIO
from pathlib import Path

from PIL import Image

from app import db
from app.signals.card_generator import build_report_card


class ReportCardV701Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = db.DB_PATH
        db.DB_PATH = Path(self.tmp.name) / "test.db"
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self.old
        self.tmp.cleanup()

    def _closed(self, market, dest, result, unit):
        is_forex = market == "FOREX"
        row = db.create_signal(
            market_type=market,
            symbol="EURUSD" if is_forex else "BTCUSD",
            direction="BUY",
            entry_price=1.1 if is_forex else 100.0,
            stop_loss=1.09 if is_forex else 95.0,
            targets=[1.12 if is_forex else 110.0],
            risk_percent=1,
            rr_ratio=2,
            destination=dest,
            chart_file_id=None,
            created_by=1,
            lot_size=0.1 if is_forex else None,
            leverage=None if is_forex else 3,
            trailing_code="NEXUS_TRAIL_01",
            trailing_name="Safe Scalping",
        )
        db.close_signal(int(row["id"]), 1.11 if is_forex else 105.0, result, unit, None)

    def test_channel_market_stats_keep_units_separate(self):
        self._closed("FOREX", "FREE", 25.4, "PIPS")
        self._closed("FOREX", "BOTH", -10.0, "PIPS")
        self._closed("CRYPTO", "FREE", 4.5, "PERCENT")
        self._closed("CRYPTO", "VIP", 2.0, "PERCENT")
        self._closed("CRYPTO", "BOTH", -1.25, "PERCENT")
        start = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        end = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

        ff = db.channel_market_performance_stats(start, end, "FREE", "FOREX")
        fv = db.channel_market_performance_stats(start, end, "VIP", "FOREX")
        cf = db.channel_market_performance_stats(start, end, "FREE", "CRYPTO")
        cv = db.channel_market_performance_stats(start, end, "VIP", "CRYPTO")

        self.assertEqual(ff["total"], 2)
        self.assertAlmostEqual(ff["result_pips"], 15.4, places=1)
        self.assertEqual(fv["total"], 1)
        self.assertAlmostEqual(fv["result_pips"], -10.0, places=1)
        self.assertEqual(cf["total"], 2)
        self.assertAlmostEqual(cf["result_pct"], 3.25, places=2)
        self.assertEqual(cv["total"], 2)
        self.assertAlmostEqual(cv["result_pct"], 0.75, places=2)

    def test_report_card_is_single_png(self):
        summary = {"closed": 36, "wins": 28, "losses": 8, "win_rate": 77.8, "crypto_pct": 19.2, "forex_pips": 323.6}
        crypto_free = {"total": 18, "wins": 14, "losses": 4, "win_rate": 77.8, "result_pct": 12.0, "result_pips": 0.0}
        crypto_vip = {"total": 10, "wins": 8, "losses": 2, "win_rate": 80.0, "result_pct": 7.2, "result_pips": 0.0}
        forex_free = {"total": 12, "wins": 9, "losses": 3, "win_rate": 75.0, "result_pct": 0.0, "result_pips": 186.4}
        forex_vip = {"total": 8, "wins": 5, "losses": 3, "win_rate": 62.5, "result_pct": 0.0, "result_pips": 137.2}
        raw = build_report_card("daily", "۱۴۰۵/۰۵/۲۸", summary, crypto_free, crypto_vip, forex_free, forex_vip, "fa")
        image = Image.open(BytesIO(raw))
        self.assertEqual(image.format, "PNG")
        self.assertEqual(image.size, (1080, 1320))

    def test_channel_sender_is_text_only(self):
        src = (Path(__file__).parents[1] / "app" / "main.py").read_text(encoding="utf-8")
        start = src.index("async def _send_channel_report")
        end = src.index("async def _send_scheduled_report", start)
        fn = src[start:end]
        self.assertIn("bot.send_message", fn)
        self.assertIn("_channel_report_caption", fn)
        self.assertNotIn("bot.send_photo", fn)
        self.assertNotIn("build_report_card", fn)

    def test_config_accepts_utf8_bom_env(self):
        src = (Path(__file__).parents[1] / "app" / "config.py").read_text(encoding="utf-8")
        self.assertIn('load_dotenv(encoding="utf-8-sig")', src)


if __name__ == "__main__":
    unittest.main()
