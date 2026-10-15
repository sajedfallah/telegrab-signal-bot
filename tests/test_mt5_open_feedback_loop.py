"""Regression guards for the admin MT5 OPEN feedback loop (NX-0203 -> NX-0204)."""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "app/main.py").read_text(encoding="utf-8")
DB = (ROOT / "app/db.py").read_text(encoding="utf-8")
API = (ROOT / "app/autotrade/api.py").read_text(encoding="utf-8")


class Mt5OpenFeedbackLoopTests(unittest.TestCase):
    def test_open_event_resolves_original_signal_by_ticket(self):
        start = MAIN.index('    if event == "OPEN":')
        end = MAIN.index('    if event in {"CANCEL", "EXPIRE"}:', start)
        block = MAIN[start:end]
        self.assertLess(block.index("get_mt5_admin_signal_for_open("),
                        block.index("db.issue_mt5_admin_signal("))
        self.assertIn('str(payload.get("position_id") or "")', block)
        self.assertIn('existing["id"]', block)
        self.assertIn('existing["issuer_account"]', block)
        self.assertIn('signal_id.startswith("NX-")', block)
        self.assertIn('existing["created_by"]', block)
        self.assertIn('if existing and str(existing["order_type"] or "MARKET").upper() == "MARKET":', block)

    def test_admin_does_not_reconsume_broker_originated_manual_signals(self):
        self.assertIn("exclude_manual_origin_account=account", API)
        self.assertIn("COALESCE(trailing_name,'') <> 'Manual MT5'", DB)
        self.assertIn("def get_mt5_admin_signal_for_open(", DB)
        self.assertIn("e.position_id=?", DB)

    def test_regular_issued_signals_remain_available(self):
        self.assertIn("issuer_type='MT5_ADMIN'", DB)
        self.assertIn("exclude_manual_origin_account: str | None = None", DB)


if __name__ == "__main__":
    unittest.main()
