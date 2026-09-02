import unittest
from app.signals.calculator import risk_reward, result_metric

class CalculatorTests(unittest.TestCase):
    def test_rr_buy(self):
        self.assertEqual(risk_reward(100, 90, 120, "BUY"), 2.0)

    def test_forex_buy_sell_direction(self):
        buy = result_metric("FOREX", "EURUSD", "BUY", 1.1000, 1.1010)
        sell = result_metric("FOREX", "EURUSD", "SELL", 1.1010, 1.1000)
        self.assertEqual(buy[0], 10.0)
        self.assertEqual(sell[0], 10.0)

    def test_crypto_short(self):
        value, unit, _ = result_metric("CRYPTO", "BTCUSD", "SHORT", 100.0, 90.0)
        self.assertEqual(unit, "PERCENT")
        self.assertEqual(value, 10.0)

    def test_explicit_xau_pip_size(self):
        value, unit, _ = result_metric("FOREX", "XAUUSD", "BUY", 4000.0, 4400.0, pip_size=0.1)
        self.assertEqual(unit, "PIPS")
        self.assertEqual(value, 4000.0)

if __name__ == "__main__":
    unittest.main()
