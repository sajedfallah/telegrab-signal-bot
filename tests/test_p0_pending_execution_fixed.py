
from pathlib import Path
import tempfile
import unittest
from app import db
from app.autotrade.api import TradeEventRequest
from app.autotrade.symbol_registry import normalize_symbol, infer_category, resolve_symbol


ROOT=Path(__file__).resolve().parents[1]

class P0PendingExecutionFixedTests(unittest.TestCase):
    def test_mt5_pending_execution_path_is_not_limit_market_only(self):
        ea=(ROOT/"mt5/NEXUS_AutoTrade/NEXUS_AutoTrade.mq5").read_text(encoding="utf-8")
        tm=(ROOT/"mt5/NEXUS_AutoTrade/Include/TradeManager.mqh").read_text(encoding="utf-8")
        for token in ("BUY_LIMIT","SELL_LIMIT","BUY_STOP","SELL_STOP","BUY_STOP_LIMIT","SELL_STOP_LIMIT"):
            self.assertIn(token, tm)
        self.assertIn("TRADE_ACTION_PENDING", tm)
        self.assertIn("OrderSend(req,res)", tm)
        self.assertIn("IsPendingSignalType", ea)

    def test_signal_event_contract_preserves_stop_limit(self):
        req=TradeEventRequest(
            event="PENDING", ticket="1", signal_id="NX-1", symbol="BTCUSD",
            direction="LONG", volume=0.1, entry_price=100, stop_loss=90,
            take_profit=120, order_type="BUY_STOP_LIMIT", stop_limit_price=101,
        )
        self.assertEqual(req.order_type, "BUY_STOP_LIMIT")
        self.assertEqual(req.stop_limit_price, 101)

    def test_db_rejects_stop_limit_without_limit_price(self):
        tmp=tempfile.TemporaryDirectory()
        old=db.DB_PATH; db.DB_PATH=Path(tmp.name)/"t.db"
        try:
            db.init_db()
            with self.assertRaises(ValueError):
                db.create_signal(
                    market_type="CRYPTO",symbol="BTCUSD",direction="BUY",
                    entry_price=100,stop_loss=90,targets=[120],risk_percent=1,
                    rr_ratio=2,destination="VIP",chart_file_id=None,created_by=1,
                    order_type="BUY_STOP_LIMIT",
                )
        finally:
            db.DB_PATH=old; tmp.cleanup()

    def test_signal_card_is_canonical_ltr_and_contains_volume(self):
        src=(ROOT/"app/main.py").read_text(encoding="utf-8")
        start=src.index("def _signal_caption")
        end=src.index("\n\ndef ",start+10)
        fn=src[start:end]
        self.assertIn("NEXUS SIGNAL",fn)
        self.assertIn("Volume",fn)
        self.assertNotIn("Leverage:",fn)

    def test_no_legacy_leverage_field_in_signal_fsm(self):
        src=(ROOT/"app/main.py").read_text(encoding="utf-8")
        self.assertNotIn("signal_leverage",src)

    def test_symbol_registry_normalizes_and_maps_without_market_execution_branching(self):
        self.assertEqual(normalize_symbol(" xau/usd "), "XAUUSD")
        self.assertEqual(infer_category("BTCUSD"), "CRYPTO")
        self.assertEqual(resolve_symbol("XAUUSD", "EPLANET"), "XAUUSD")
        self.assertEqual(resolve_symbol("EURUSD", "NEW_BROKER"), "EURUSD")

if __name__=="__main__":
    unittest.main()
