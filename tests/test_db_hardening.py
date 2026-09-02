import tempfile
import unittest
from pathlib import Path
from app import db

class DbHardeningTests(unittest.TestCase):
    def setUp(self):
        self.old_path = db.DB_PATH
        self.tmp = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(self.tmp.name) / "test.db"
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self.old_path
        self.tmp.cleanup()

    def test_wal_and_busy_timeout(self):
        with db.conn() as con:
            self.assertEqual(str(con.execute("PRAGMA journal_mode").fetchone()[0]).lower(), "wal")
            self.assertGreaterEqual(int(con.execute("PRAGMA busy_timeout").fetchone()[0]), 10000)

    def test_user_level_counts_empty(self):
        self.assertEqual(db.user_level_counts(), {"bronze":0,"silver":0,"gold":0,"diamond":0})

if __name__ == "__main__":
    unittest.main()
