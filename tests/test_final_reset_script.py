import importlib.util
import sqlite3
from pathlib import Path


def _load_reset_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "reset_final_trading_test.py"
    spec = importlib.util.spec_from_file_location("nexus_final_reset", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_final_reset_script_loads_from_scripts_path():
    module = _load_reset_module()
    assert module.CONFIRM_TEXT == "RESET-NEXUS-FINAL-TEST"
    assert module.ROOT == Path(__file__).resolve().parents[1]
    assert "report_dispatches" in module.EXPLICIT_RUNTIME_TABLES


def test_final_reset_discovers_signal_owned_and_runtime_tables(tmp_path):
    module = _load_reset_module()
    db_path = tmp_path / "reset-test.db"
    con = sqlite3.connect(db_path)
    try:
        con.executescript(
            """
            PRAGMA foreign_keys=ON;
            CREATE TABLE users(
                telegram_id INTEGER PRIMARY KEY,
                last_menu_message_id INTEGER
            );
            CREATE TABLE payments(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                note TEXT
            );
            CREATE TABLE signals(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT
            );
            CREATE TABLE signal_targets(
                signal_id INTEGER NOT NULL,
                target_no INTEGER NOT NULL,
                FOREIGN KEY(signal_id) REFERENCES signals(id) ON DELETE CASCADE
            );
            CREATE TABLE autotrade_notifications(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                payload_json TEXT
            );
            CREATE TABLE mt5_live_state(
                account_number TEXT,
                state_type TEXT,
                ticket TEXT,
                signal_code TEXT,
                status TEXT
            );
            CREATE TABLE report_dispatches(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_type TEXT,
                period_key TEXT
            );
            """
        )
        related = module._signal_related_tables(con)
        assert "signals" in related
        assert "signal_targets" in related
        assert "autotrade_notifications" in related
        assert "mt5_live_state" in related
        assert "report_dispatches" in related
        assert "users" not in related
        assert "payments" not in related
    finally:
        con.close()


def test_final_reset_resets_signal_and_report_baseline_without_touching_commercial_rows(tmp_path):
    module = _load_reset_module()
    db_path = tmp_path / "reset-sequence.db"
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        con.executescript(
            """
            CREATE TABLE users(
                telegram_id INTEGER PRIMARY KEY,
                last_menu_message_id INTEGER
            );
            CREATE TABLE payments(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                note TEXT
            );
            CREATE TABLE signals(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT
            );
            CREATE TABLE signal_updates(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id INTEGER NOT NULL,
                detail TEXT,
                FOREIGN KEY(signal_id) REFERENCES signals(id) ON DELETE CASCADE
            );
            CREATE TABLE report_dispatches(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_type TEXT,
                period_key TEXT
            );
            INSERT INTO users(telegram_id,last_menu_message_id) VALUES(1,999);
            INSERT INTO payments(note) VALUES('preserve-me');
            INSERT INTO signals(code) VALUES('NX-0001');
            INSERT INTO signals(code) VALUES('NX-0002');
            INSERT INTO signal_updates(signal_id,detail) VALUES(2,'old');
            INSERT INTO report_dispatches(report_type,period_key) VALUES('daily_channel_v2_free','2026-09-04');
            INSERT INTO report_dispatches(report_type,period_key) VALUES('weekly_channel_v2_vip','2026-W36');
            """
        )
        related = module._signal_related_tables(con)
        module._reset_database(con, related)
        module._verify_reset(con, related)

        assert con.execute("SELECT COUNT(*) FROM signals").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM signal_updates").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM report_dispatches").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM payments").fetchone()[0] == 1
        assert con.execute("SELECT last_menu_message_id FROM users WHERE telegram_id=1").fetchone()[0] is None

        cur = con.execute("INSERT INTO signals(code) VALUES('NX-0001')")
        assert cur.lastrowid == 1
        report_cur = con.execute(
            "INSERT INTO report_dispatches(report_type,period_key) VALUES('daily_channel_v2_free','2026-09-04')"
        )
        assert report_cur.lastrowid == 1
    finally:
        con.close()
