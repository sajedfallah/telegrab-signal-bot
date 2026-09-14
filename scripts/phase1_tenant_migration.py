from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.tenancy import init_tenant_schema


DEFAULT_DB = ROOT / "nexus_bot.db"

# Phase 1 is additive. Tables without a simple integer `id` are intentionally
# deferred until their domain migration so we do not change legacy PK semantics.
TENANT_OWNED_TABLES = (
    "payments",
    "licenses",
    "signals",
    "signal_updates",
    "subscriptions",
    "invoices",
    "autotrade_mt5_accounts",
    "autotrade_account_change_requests",
    "autotrade_mt5_account_history",
    "autotrade_exchange_accounts",
    "autotrade_trade_executions",
    "autotrade_notifications",
)


def columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {str(r[1]) for r in con.execute(f"PRAGMA table_info({table})").fetchall()}


def table_exists(con: sqlite3.Connection, table: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def snapshot_counts(con: sqlite3.Connection) -> dict[str, int]:
    result: dict[str, int] = {}
    for table in TENANT_OWNED_TABLES:
        if table_exists(con, table):
            result[table] = int(con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    return result


def migrate(db_path: Path, *, dry_run: bool = False) -> dict[str, object]:
    if not db_path.exists():
        raise FileNotFoundError(db_path)
    con = sqlite3.connect(db_path, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    try:
        con.execute("BEGIN IMMEDIATE")
        before = snapshot_counts(con)
        nexus_tenant_id = init_tenant_schema(con)
        changed: list[str] = []
        for table in TENANT_OWNED_TABLES:
            if not table_exists(con, table):
                continue
            cols = columns(con, table)
            if "tenant_id" not in cols:
                con.execute(f"ALTER TABLE {table} ADD COLUMN tenant_id INTEGER")
                changed.append(table)
            con.execute(
                f"UPDATE {table} SET tenant_id=? WHERE tenant_id IS NULL",
                (nexus_tenant_id,),
            )
            con.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{table}_tenant ON {table}(tenant_id)"
            )
        after = snapshot_counts(con)
        if before != after:
            raise RuntimeError("row-count reconciliation failed; migration rolled back")
        nulls = {}
        for table in TENANT_OWNED_TABLES:
            if table_exists(con, table) and "tenant_id" in columns(con, table):
                nulls[table] = int(
                    con.execute(f"SELECT COUNT(*) FROM {table} WHERE tenant_id IS NULL").fetchone()[0]
                )
        if any(nulls.values()):
            raise RuntimeError(f"tenant backfill incomplete: {nulls}")
        report = {
            "database": str(db_path),
            "nexus_tenant_id": nexus_tenant_id,
            "tables_altered": changed,
            "row_counts_before": before,
            "row_counts_after": after,
            "null_tenant_counts": nulls,
            "dry_run": dry_run,
        }
        if dry_run:
            con.rollback()
        else:
            con.commit()
        return report
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="NEXUS Phase 1 additive tenant migration")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(migrate(args.db, dry_run=args.dry_run), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
