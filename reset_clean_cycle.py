from __future__ import annotations

import argparse
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "nexus_bot.db"
FSM_PATH = ROOT / "nexus_fsm.db"

# Operational/history tables only. Users, licenses, subscriptions, plans,
# payment records, MT5 bindings and exchange bindings are intentionally kept.
RESET_TABLES = [
    "signal_targets",
    "signal_updates",
    "autotrade_command_receipts",
    "autotrade_signal_receipts",
    "autotrade_trade_executions",
    "autotrade_publish_claims",
    "autotrade_notifications",
    "autotrade_commands",
    "report_dispatches",
    "signals",
    "audit_logs",
]


def backup(path: Path, backup_dir: Path) -> Path | None:
    if not path.exists():
        return None
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    target = backup_dir / f"{path.stem}_{stamp}{path.suffix}"
    shutil.copy2(path, target)
    return target


def reset_db() -> None:
    if not DB_PATH.exists():
        print(f"DB not found: {DB_PATH}")
        return

    backup_dir = ROOT / "backups" / "pre_reset"

    # Checkpoint first so the backup includes the latest WAL contents.
    con = sqlite3.connect(DB_PATH, timeout=20)
    try:
        con.execute("PRAGMA busy_timeout=20000")
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        con.close()

    db_backup = backup(DB_PATH, backup_dir)
    if db_backup:
        print(f"Backup: {db_backup}")

    con = sqlite3.connect(DB_PATH, timeout=20)
    try:
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA busy_timeout=20000")
        con.execute("BEGIN IMMEDIATE")
        for table in RESET_TABLES:
            con.execute(f"DELETE FROM {table}")
        # Make the next signal row ID exactly 1, hence code NX-0001.
        con.execute("DELETE FROM sqlite_sequence WHERE name='signals'")
        # Reset operational AUTOINCREMENT IDs for deterministic fresh reports.
        for table in (
            "signal_updates",
            "autotrade_commands",
            "autotrade_trade_executions",
            "autotrade_notifications",
            "report_dispatches",
            "audit_logs",
        ):
            con.execute("DELETE FROM sqlite_sequence WHERE name=?", (table,))
        cycle = "CYCLE-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        con.execute("INSERT INTO app_settings(key,value,updated_at) VALUES('current_cycle_id',?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at", (cycle, datetime.now(timezone.utc).isoformat()))
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def reset_fsm() -> None:
    if not FSM_PATH.exists():
        print(f"FSM DB not found: {FSM_PATH}")
        return
    backup_dir = ROOT / "backups" / "pre_reset"
    fsm_backup = backup(FSM_PATH, backup_dir)
    if fsm_backup:
        print(f"FSM backup: {fsm_backup}")
    con = sqlite3.connect(FSM_PATH, timeout=20)
    try:
        con.execute("PRAGMA busy_timeout=20000")
        con.execute("DELETE FROM fsm_context")
        con.commit()
    finally:
        con.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reset NEXUS operational/trading memory for a new Signal #1 cycle."
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm destructive operational-history reset.",
    )
    args = parser.parse_args()
    if not args.yes:
        print("This resets signals, trade ledger, notifications, report dispatches and FSM state.")
        print("Users, licenses, plans, payments, MT5 bindings and exchange bindings are kept.")
        print("Run: python reset_clean_cycle.py --yes")
        return 2

    reset_db()
    reset_fsm()
    print("CLEAN CYCLE RESET COMPLETE")
    print("Next signal code: NX-0001")
    print("Reports/trade statistics start from zero.")
    print("MT5 Global Variables are reset separately by mt5/NEXUS_AutoTrade/NEXUS_Reset_Runtime.mq5")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
