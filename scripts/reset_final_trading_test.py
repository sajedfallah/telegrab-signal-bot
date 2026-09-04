from __future__ import annotations

"""Destructive-but-scoped reset for the final NEXUS trading baseline.

This utility resets the *trading/signal* runtime to a clean production-start
state without deleting users, licenses, payments, channel configuration, or MT5
account authorization. It is intended to be run only while the Telegram bot,
FastAPI process, and MT5 AutoTrade EA are stopped/detached.

What it resets:
- all signals and tables that reference signals;
- signal numbering (SQLite AUTOINCREMENT -> next id/code is NX-0001);
- MT5 notification/execution/session/live-state caches;
- signal-report delivery/dedup history so reports start from the new zero point;
- recorded Telegram signal/result message pointers;
- best-effort deletion of recorded FREE/VIP Telegram signal lifecycle messages;
- generated AutoTrade chart cache files;
- users.last_menu_message_id UI cache pointers.

It deliberately preserves commercial/account truth: users, licenses, payments,
subscription plans, AutoTrade account bindings, admin allow-list/configuration,
and .env secrets.
"""

import argparse
import json
import os
import shutil
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DB_PATH = ROOT / "nexus_bot.db"
ASSET_ROOT = ROOT / "app" / "assets" / "autotrade"
CONFIRM_TEXT = "RESET-NEXUS-FINAL-TEST"

# Runtime/cache tables that do not necessarily have a declared FK to signals.
EXPLICIT_RUNTIME_TABLES = {
    "autotrade_notifications",
    "autotrade_sessions",
    "autotrade_trade_executions",
    "autotrade_signal_receipts",
    "autotrade_command_receipts",
    "autotrade_commands",
    "autotrade_publish_claims",
    "mt5_signal_publication_assets",
    "mt5_live_state",
    "mt5_heartbeats_v060",
    "report_dispatches",
}


def _qident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _tables(con: sqlite3.Connection) -> set[str]:
    return {
        str(r[0])
        for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    }


def _columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {str(r[1]) for r in con.execute(f"PRAGMA table_info({_qident(table)})").fetchall()}


def _signal_related_tables(con: sqlite3.Connection) -> set[str]:
    all_tables = _tables(con)
    related = {"signals"} if "signals" in all_tables else set()

    # Follow declared FK dependencies transitively so new signal-owned tables
    # added by future migrations are automatically included in the reset.
    changed = True
    while changed:
        changed = False
        for table in all_tables - related:
            refs = {
                str(r[2])
                for r in con.execute(f"PRAGMA foreign_key_list({_qident(table)})").fetchall()
            }
            if refs & related:
                related.add(table)
                changed = True

    # Compatibility/migration/runtime tables may intentionally lack FKs.
    related.update(t for t in all_tables if t.startswith("signal_") or t in EXPLICIT_RUNTIME_TABLES)
    return related & all_tables


def _active_live_rows(con: sqlite3.Connection) -> list[sqlite3.Row]:
    if "mt5_live_state" not in _tables(con):
        return []
    cols = _columns(con, "mt5_live_state")
    if not {"status", "state_type", "ticket"}.issubset(cols):
        return []
    return list(
        con.execute(
            "SELECT account_number,state_type,ticket,signal_code,status "
            "FROM mt5_live_state WHERE UPPER(status) IN ('OPEN','PENDING')"
        ).fetchall()
    )


def _collect_telegram_message_ids(con: sqlite3.Connection) -> tuple[set[int], set[int]]:
    free_ids: set[int] = set()
    vip_ids: set[int] = set()
    for table in _tables(con):
        cols = _columns(con, table)
        if "free_message_id" in cols:
            for row in con.execute(
                f"SELECT free_message_id FROM {_qident(table)} WHERE free_message_id IS NOT NULL"
            ):
                try:
                    free_ids.add(int(row[0]))
                except (TypeError, ValueError):
                    pass
        if "free_last_message_id" in cols:
            for row in con.execute(
                f"SELECT free_last_message_id FROM {_qident(table)} WHERE free_last_message_id IS NOT NULL"
            ):
                try:
                    free_ids.add(int(row[0]))
                except (TypeError, ValueError):
                    pass
        if "vip_message_id" in cols:
            for row in con.execute(
                f"SELECT vip_message_id FROM {_qident(table)} WHERE vip_message_id IS NOT NULL"
            ):
                try:
                    vip_ids.add(int(row[0]))
                except (TypeError, ValueError):
                    pass
        if "vip_last_message_id" in cols:
            for row in con.execute(
                f"SELECT vip_last_message_id FROM {_qident(table)} WHERE vip_last_message_id IS NOT NULL"
            ):
                try:
                    vip_ids.add(int(row[0]))
                except (TypeError, ValueError):
                    pass
    return free_ids, vip_ids


def _telegram_targets() -> tuple[str, str, str]:
    # Importing settings loads .env through the same path used by production.
    from app.config import settings

    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN is missing; cannot clean recorded Telegram messages")
    return token, str(settings.free_channel_target), str(settings.vip_channel_id)


def _telegram_delete(token: str, chat_id: str, message_id: int) -> tuple[bool, str]:
    url = f"https://api.telegram.org/bot{token}/deleteMessage"
    body = urllib.parse.urlencode({"chat_id": chat_id, "message_id": int(message_id)}).encode("utf-8")
    request = urllib.request.Request(url, data=body, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8", errors="replace"))
        if bool(data.get("ok")):
            return True, ""
        return False, str(data.get("description") or "Telegram deleteMessage failed")
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8", errors="replace")).get("description")
        except Exception:
            detail = None
        return False, str(detail or f"HTTP {exc.code}")
    except Exception as exc:
        return False, str(exc)


def _delete_recorded_telegram_messages(
    free_ids: Iterable[int], vip_ids: Iterable[int]
) -> tuple[int, int, list[str]]:
    token, free_target, vip_target = _telegram_targets()
    deleted = failed = 0
    errors: list[str] = []

    # Delete newest first. Telegram threading/history looks cleaner and duplicate
    # ids gathered from last-message pointers are naturally deduplicated by sets.
    for label, target, ids in (
        ("FREE", free_target, sorted(set(free_ids), reverse=True)),
        ("VIP", vip_target, sorted(set(vip_ids), reverse=True)),
    ):
        for mid in ids:
            ok, error = _telegram_delete(token, target, mid)
            if ok:
                deleted += 1
            else:
                failed += 1
                errors.append(f"{label} message_id={mid}: {error}")
    return deleted, failed, errors


def _clear_assets() -> int:
    if not ASSET_ROOT.exists():
        return 0
    removed = 0
    for path in sorted(ASSET_ROOT.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if path.is_file() and path.name != ".gitkeep":
            try:
                path.unlink()
                removed += 1
            except FileNotFoundError:
                pass
        elif path.is_dir():
            try:
                path.rmdir()
            except OSError:
                pass
    return removed


def _backup_database() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_root = Path(os.environ.get("TEMP") or os.environ.get("TMP") or ROOT) / "NEXUS_FINAL_TEST_BACKUPS"
    backup_root.mkdir(parents=True, exist_ok=True)
    target = backup_root / f"nexus_bot_before_final_reset_{stamp}.db"
    shutil.copy2(DB_PATH, target)
    return target


def _reset_database(con: sqlite3.Connection, related_tables: set[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in sorted(related_tables):
        counts[table] = int(con.execute(f"SELECT COUNT(*) FROM {_qident(table)}").fetchone()[0])

    con.execute("PRAGMA foreign_keys=OFF")
    try:
        con.execute("BEGIN IMMEDIATE")
        for table in sorted(related_tables):
            con.execute(f"DELETE FROM {_qident(table)}")

        # UI message pointers are runtime cache, not customer/commercial truth.
        if "users" in _tables(con) and "last_menu_message_id" in _columns(con, "users"):
            con.execute("UPDATE users SET last_menu_message_id=NULL")

        if "sqlite_sequence" in {
            str(r[0]) for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }:
            placeholders = ",".join("?" for _ in related_tables)
            if placeholders:
                con.execute(
                    f"DELETE FROM sqlite_sequence WHERE name IN ({placeholders})",
                    tuple(sorted(related_tables)),
                )
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.execute("PRAGMA foreign_keys=ON")

    return counts


def _verify_reset(con: sqlite3.Connection, related_tables: set[str]) -> None:
    nonzero = {
        table: int(con.execute(f"SELECT COUNT(*) FROM {_qident(table)}").fetchone()[0])
        for table in sorted(related_tables)
        if int(con.execute(f"SELECT COUNT(*) FROM {_qident(table)}").fetchone()[0]) != 0
    }
    if nonzero:
        raise RuntimeError(f"reset verification failed; non-empty tables: {nonzero}")

    if "signals" in related_tables:
        seq = con.execute("SELECT seq FROM sqlite_sequence WHERE name='signals'").fetchone()
        if seq is not None:
            raise RuntimeError(f"signal sequence was not reset: {seq[0]}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset NEXUS trading state for final production baseline")
    parser.add_argument("--confirm", required=True, help=f"must equal {CONFIRM_TEXT}")
    parser.add_argument(
        "--skip-telegram-delete",
        action="store_true",
        help="reset DB/cache but do not call Telegram deleteMessage",
    )
    parser.add_argument(
        "--allow-live-snapshot",
        action="store_true",
        help="override stale/open mt5_live_state safety check (use only after broker is verified flat)",
    )
    args = parser.parse_args()

    if args.confirm != CONFIRM_TEXT:
        print(f"ABORT: confirmation must be exactly {CONFIRM_TEXT}", file=sys.stderr)
        return 2
    if not DB_PATH.exists():
        print(f"ABORT: database not found: {DB_PATH}", file=sys.stderr)
        return 2

    con = sqlite3.connect(DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    try:
        live = _active_live_rows(con)
        if live and not args.allow_live_snapshot:
            print("ABORT: MT5 live-state still contains OPEN/PENDING broker rows:", file=sys.stderr)
            for row in live:
                print(
                    f"  {row['state_type']} ticket={row['ticket']} signal={row['signal_code']} status={row['status']}",
                    file=sys.stderr,
                )
            print("Verify MT5 is flat, let LIVE SYNC update, then run reset again.", file=sys.stderr)
            return 3

        related = _signal_related_tables(con)
        free_ids, vip_ids = _collect_telegram_message_ids(con)
        backup = _backup_database()

        print(f"Backup: {backup}")
        print(f"Trading tables selected: {', '.join(sorted(related))}")
        print(f"Recorded Telegram messages: FREE={len(free_ids)} VIP={len(vip_ids)}")

        if not args.skip_telegram_delete:
            deleted, failed, errors = _delete_recorded_telegram_messages(free_ids, vip_ids)
            print(f"Telegram cleanup: deleted={deleted} failed={failed}")
            for error in errors[:20]:
                print(f"  WARN: {error}")
            if len(errors) > 20:
                print(f"  WARN: {len(errors) - 20} additional Telegram delete errors omitted")
        else:
            print("Telegram cleanup: SKIPPED by argument")

        prior_counts = _reset_database(con, related)
        _verify_reset(con, related)
        removed_assets = _clear_assets()

        print("Database reset: OK")
        print(f"Rows removed: {sum(prior_counts.values())}")
        print(f"AutoTrade asset files removed: {removed_assets}")
        print("Signal sequence: RESET (next inserted signal id/code will be 1 / NX-0001)")
        print("Signal report baseline: RESET (old report dispatch/dedup history removed)")
        print("Commercial state preserved: users/licenses/payments/account bindings/config")
        print("IMPORTANT: restart/re-attach the MT5 EA before trading so its in-memory after_id counters return to 0.")
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
