import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


class ArchitectureV7StaticTests(unittest.TestCase):
    def test_persistent_fsm_replaces_memory_storage(self):
        main = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        self.assertIn("SQLiteStorage", main)
        self.assertNotIn("MemoryStorage", main)
        self.assertTrue((ROOT / "app" / "storage" / "sqlite_storage.py").exists())

    def test_new_feature_routers_are_modular(self):
        self.assertTrue((ROOT / "app" / "routers" / "analytics.py").exists())
        self.assertTrue((ROOT / "app" / "routers" / "subscriptions.py").exists())
        self.assertTrue((ROOT / "app" / "services" / "analytics_service.py").exists())
        self.assertTrue((ROOT / "app" / "services" / "license_service.py").exists())
        self.assertTrue((ROOT / "app" / "states.py").exists())

    def test_signal_center_has_analytics_entry(self):
        ui = (ROOT / "app" / "ui.py").read_text(encoding="utf-8")
        self.assertIn("signal_analytics", ui)


if __name__ == "__main__":
    unittest.main()
