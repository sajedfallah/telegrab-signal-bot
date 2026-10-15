"""Guard the public MT5 close reply against leaking admin account P/L."""

from pathlib import Path
import unittest


MAIN = (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text(encoding="utf-8")


class Mt5ClosePipsOnlyTests(unittest.TestCase):
    def test_mt5_close_reply_uses_price_movement_not_admin_money(self):
        start = MAIN.index('    if event == "CLOSE":')
        end = MAIN.index('    raise ValueError(f"unsupported MT5 event: {event}")', start)
        block = MAIN[start:end]
        reply_start = block.index('        reply = (')
        reply_end = block.index('\n\n', reply_start)
        reply = block[reply_start:reply_end]
        self.assertNotIn("pnl=", reply)
        self.assertNotIn("{profit", reply)
        self.assertIn("performance={pips_text}", reply)
        self.assertIn("result={result_type}", reply)
        self.assertIn('result_type = "WIN" if result_pips > 0', block)
        self.assertNotIn('result_type = "WIN" if profit > 0', block)

    def test_broker_profit_remains_available_for_private_audit(self):
        start = MAIN.index('    if event == "CLOSE":')
        end = MAIN.index('    raise ValueError(f"unsupported MT5 event: {event}")', start)
        block = MAIN[start:end]
        self.assertIn('"profit": profit', block)
        self.assertIn('"mt5_trade_close"', block)


if __name__ == "__main__":
    unittest.main()
