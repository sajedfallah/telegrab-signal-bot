from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.provider_credentials import init_provider_secret_schema
from app.provider_lifecycle import init_lifecycle_delivery_schema
from app.provider_reconciliation import init_reconciliation_schema
from app.signal_domain import backfill_legacy_publications, init_signal_domain_schema
from app.telegram_tenant_domain import init_telegram_tenant_schema
from app.tenancy import init_tenant_schema


DEFAULT_DB = ROOT / "nexus_bot.db"
PROVIDER_TABLES = (
    "signal_publications",
    "signal_events",
    "provider_secrets",
    "telegram_connections",
    "telegram_destinations",
    "provider_lifecycle_deliveries",
    "provider_delivery_reconciliations",
    "provider_audit_log",
)


def _table_exists(con: sqlite3.Connection, table: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _counts(con: sqlite3.Connection) -> dict[str, int]:
    return {
        table: int(con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        for table in PROVIDER_TABLES
        if _table_exists(con, table)
    }


def migrate(db_path: Path, *, dry_run: bool = False) -> dict[str, object]:
    if not db_path.exists():
        raise FileNotFoundError(db_path)

    con = sqlite3.connect(db_path, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    try:
        con.execute("BEGIN IMMEDIATE")
        before = _counts(con)
        nexus_tenant_id = int(init_tenant_schema(con))

        init_signal_domain_schema(con)
        backfilled_publications = int(backfill_legacy_publications(con))
        init_provider_secret_schema(con)
        init_telegram_tenant_schema(con)
        init_lifecycle_delivery_schema(con)
        init_reconciliation_schema(con)

        missing = [table for table in PROVIDER_TABLES if not _table_exists(con, table)]
        if missing:
            raise RuntimeError(f"provider schema incomplete: {missing}")

        after = _counts(con)
        report: dict[str, object] = {
            "database": str(db_path),
            "nexus_tenant_id": nexus_tenant_id,
            "provider_tables": list(PROVIDER_TABLES),
            "row_counts_before": before,
            "row_counts_after": after,
            "legacy_publications_backfilled": backfilled_publications,
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
    parser = argparse.ArgumentParser(description="NEXUS Provider domain additive migration")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(migrate(args.db, dry_run=args.dry_run), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
