from __future__ import annotations

"""Read-only runtime smoke test for NEXUS MT5 Live PnL.

Run from the repository root on the VPS after deploying the target branch:

    python scripts/diagnose_live_pnl.py --require-live

Optional filters:

    python scripts/diagnose_live_pnl.py --account 12345678 --require-live
    python scripts/diagnose_live_pnl.py --signal-code NEXUS-123 --require-live
    python scripts/diagnose_live_pnl.py --json

The diagnostic never places, changes, or closes trades. It opens the SQLite DB
in read-only mode, validates the MT5 live-state schema, resolves live
positions/orders to NEXUS signals, then calls the same `_live_signal_state`
serializer used by the customer Mini App while forcing DB reads through the
read-only connection.

Exit codes:
    0 = healthy (or no live rows when --require-live is not requested)
    1 = live rows exist but linkage/freshness/PnL invariants fail
    2 = runtime/schema incomplete, or --require-live requested with no live rows
"""

import argparse
import json
import math
import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import db, miniapp_signals


REQUIRED_LIVE_COLUMNS = {
    "account_number",
    "state_type",
    "ticket",
    "signal_code",
    "nexus_managed",
    "status",
    "symbol",
    "direction",
    "volume",
    "entry_price",
    "current_price",
    "stop_loss",
    "take_profit",
    "profit",
    "last_seen_at",
}


def _ro_uri(path: Path) -> str:
    # SQLite accepts file:// URIs on both Windows and POSIX. mode=ro guarantees
    # this diagnostic cannot mutate the production database.
    return f"{path.resolve().as_uri()}?mode=ro"


@contextmanager
def _readonly_conn():
    con = sqlite3.connect(_ro_uri(db.DB_PATH), uri=True, timeout=5.0)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only = ON")
    con.execute("PRAGMA busy_timeout = 5000")
    try:
        yield con
    finally:
        con.close()


def _table_exists(con: sqlite3.Connection, table: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (table,)
    ).fetchone() is not None


def _columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in con.execute(f"PRAGMA table_info({table})").fetchall()}


def _iso_age_seconds(value: Any) -> float | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds())
    except (TypeError, ValueError):
        return None


def _resolve_signal(con: sqlite3.Connection, live: dict[str, Any]) -> sqlite3.Row | None:
    account = str(live.get("account_number") or "").strip()
    code = str(live.get("signal_code") or "").strip()
    ticket = str(live.get("ticket") or "").strip()

    if code:
        row = con.execute(
            """
            SELECT * FROM signals
            WHERE issuer_account=? AND UPPER(COALESCE(code,''))=UPPER(?)
            ORDER BY id DESC LIMIT 1
            """,
            (account, code),
        ).fetchone()
        if row is not None:
            return row

    if ticket and _table_exists(con, "autotrade_trade_executions"):
        return con.execute(
            """
            SELECT s.*
            FROM autotrade_trade_executions e
            JOIN signals s ON s.id=e.signal_id
            WHERE e.ticket=? AND s.issuer_account=?
            ORDER BY e.id DESC LIMIT 1
            """,
            (ticket, account),
        ).fetchone()
    return None


def _live_rows(con: sqlite3.Connection, account: str | None, signal_code: str | None) -> list[dict[str, Any]]:
    where = ["nexus_managed=1", "UPPER(COALESCE(status,'')) IN ('OPEN','PENDING')"]
    args: list[Any] = []
    if account:
        where.append("account_number=?")
        args.append(str(account))
    if signal_code:
        where.append("UPPER(COALESCE(signal_code,''))=UPPER(?)")
        args.append(str(signal_code))
    rows = con.execute(
        f"SELECT * FROM mt5_live_state WHERE {' AND '.join(where)} ORDER BY last_seen_at DESC, ticket DESC",
        tuple(args),
    ).fetchall()
    return [dict(row) for row in rows]


def _heartbeat(con: sqlite3.Connection, account: str) -> dict[str, Any] | None:
    if not _table_exists(con, "mt5_heartbeats_v060"):
        return None
    row = con.execute(
        """
        SELECT account_number,role,ea_version,last_seen_at
        FROM mt5_heartbeats_v060
        WHERE account_number=?
        ORDER BY last_seen_at DESC LIMIT 1
        """,
        (account,),
    ).fetchone()
    return dict(row) if row is not None else None


def _same_money(a: Any, b: Any) -> bool:
    try:
        return math.isclose(float(a), float(b), rel_tol=0.0, abs_tol=0.01)
    except (TypeError, ValueError):
        return False


def diagnose(*, account: str | None = None, signal_code: str | None = None, require_live: bool = False) -> tuple[int, dict[str, Any]]:
    path = Path(db.DB_PATH)
    report: dict[str, Any] = {
        "db_path": str(path),
        "stale_seconds": int(miniapp_signals.ACTIVE_TRUTH_STALE_SECONDS),
        "filters": {"account": account, "signal_code": signal_code},
        "signals": [],
        "issues": [],
    }

    if not path.exists():
        report["issues"].append("database file does not exist")
        report["result"] = "RUNTIME_INCOMPLETE"
        return 2, report

    try:
        with _readonly_conn() as con:
            for table in ("signals", "mt5_live_state"):
                if not _table_exists(con, table):
                    report["issues"].append(f"missing table: {table}")
            if report["issues"]:
                report["result"] = "SCHEMA_INCOMPLETE"
                return 2, report

            missing = sorted(REQUIRED_LIVE_COLUMNS - _columns(con, "mt5_live_state"))
            if missing:
                report["issues"].append("mt5_live_state missing columns: " + ", ".join(missing))
                report["result"] = "SCHEMA_INCOMPLETE"
                return 2, report

            signal_columns = _columns(con, "signals")
            needed_signal = {"id", "code", "status", "issuer_account", "entry_price", "stop_loss", "direction", "symbol"}
            missing_signal = sorted(needed_signal - signal_columns)
            if missing_signal:
                report["issues"].append("signals missing columns: " + ", ".join(missing_signal))
                report["result"] = "SCHEMA_INCOMPLETE"
                return 2, report

            rows = _live_rows(con, account, signal_code)
            report["live_rows"] = len(rows)
            accounts = sorted({str(row.get("account_number") or "") for row in rows if row.get("account_number")})
            report["accounts"] = accounts
            report["heartbeats"] = []
            for acc in accounts:
                hb = _heartbeat(con, acc)
                if hb:
                    hb["age_seconds"] = _iso_age_seconds(hb.get("last_seen_at"))
                    report["heartbeats"].append(hb)

            if not rows:
                report["result"] = "NO_LIVE_ROWS"
                if require_live:
                    report["issues"].append("no NEXUS-managed OPEN/PENDING MT5 snapshot matched the requested filters")
                    return 2, report
                return 0, report

            # Group by the resolved canonical signal. Multiple MT5 positions may
            # legitimately map to the same signal and must be aggregated once.
            grouped: dict[int, dict[str, Any]] = {}
            unmatched: list[dict[str, Any]] = []
            for live in rows:
                signal = _resolve_signal(con, live)
                if signal is None:
                    unmatched.append({
                        "account_number": live.get("account_number"),
                        "ticket": live.get("ticket"),
                        "signal_code": live.get("signal_code"),
                        "symbol": live.get("symbol"),
                    })
                    continue
                sid = int(signal["id"])
                grouped.setdefault(sid, {"signal": dict(signal), "rows": []})["rows"].append(live)

            if unmatched:
                report["unmatched_live_rows"] = unmatched
                report["issues"].append(f"{len(unmatched)} live MT5 row(s) could not be linked to a NEXUS signal")

            original_conn = miniapp_signals.db.conn
            miniapp_signals.db.conn = _readonly_conn
            try:
                for sid, group in grouped.items():
                    signal = group["signal"]
                    live_state = miniapp_signals._live_signal_state(signal)
                    source_rows = group["rows"]
                    positions = [
                        row for row in source_rows
                        if str(row.get("state_type") or "").upper() == "POSITION"
                        and str(row.get("status") or "").upper() == "OPEN"
                    ]
                    expected_profit = round(sum(float(row.get("profit") or 0.0) for row in positions), 2)
                    expected_volume = sum(float(row.get("volume") or 0.0) for row in positions)
                    item = {
                        "signal_id": sid,
                        "code": signal.get("code"),
                        "symbol": signal.get("symbol"),
                        "direction": signal.get("direction"),
                        "issuer_account": signal.get("issuer_account"),
                        "tickets": sorted({str(row.get("ticket") or "") for row in source_rows}),
                        "source_profit": expected_profit,
                        "source_volume": expected_volume,
                        "api_live": live_state,
                        "checks": {},
                    }

                    if live_state is None:
                        item["checks"]["serializer_present"] = False
                        report["issues"].append(f"signal {sid}: serializer returned no live state")
                    else:
                        item["checks"]["serializer_present"] = True
                        if positions:
                            pnl_ok = _same_money(live_state.get("floating_pnl"), expected_profit)
                            volume_ok = math.isclose(float(live_state.get("volume") or 0.0), expected_volume, rel_tol=0.0, abs_tol=1e-9)
                            item["checks"]["broker_pnl_exact"] = pnl_ok
                            item["checks"]["volume_exact"] = volume_ok
                            if not pnl_ok:
                                report["issues"].append(
                                    f"signal {sid}: API floating_pnl={live_state.get('floating_pnl')} != broker snapshot sum={expected_profit}"
                                )
                            if not volume_ok:
                                report["issues"].append(
                                    f"signal {sid}: API volume={live_state.get('volume')} != broker snapshot sum={expected_volume}"
                                )
                        else:
                            pending_zero = _same_money(live_state.get("floating_pnl"), 0.0)
                            item["checks"]["pending_pnl_zero"] = pending_zero
                            if not pending_zero:
                                report["issues"].append(f"signal {sid}: pending order exposed non-zero floating PnL")

                        fresh = str(live_state.get("status") or "").upper() in {"LIVE", "PENDING"}
                        item["checks"]["fresh"] = fresh
                        if not fresh:
                            report["issues"].append(
                                f"signal {sid}: live state is {live_state.get('status')} age={live_state.get('age_seconds')}s"
                            )

                    report["signals"].append(item)
            finally:
                miniapp_signals.db.conn = original_conn

    except sqlite3.Error as exc:
        report["issues"].append(f"sqlite error: {exc}")
        report["result"] = "RUNTIME_ERROR"
        return 2, report

    report["matched_signals"] = len(report["signals"])
    report["result"] = "PASS" if not report["issues"] else "FAIL"
    return (0 if not report["issues"] else 1), report


def _print_human(report: dict[str, Any]) -> None:
    print("NEXUS Live PnL Runtime Diagnostic")
    print(f"DB: {report.get('db_path')}")
    print(f"Freshness threshold: {report.get('stale_seconds')}s")
    print(f"Result: {report.get('result')}")
    print(f"Live rows: {report.get('live_rows', 0)} | Matched signals: {report.get('matched_signals', 0)}")

    for heartbeat in report.get("heartbeats", []):
        age = heartbeat.get("age_seconds")
        age_text = "?" if age is None else f"{age:.1f}s"
        print(
            f"HEARTBEAT account={heartbeat.get('account_number')} role={heartbeat.get('role')} "
            f"ea={heartbeat.get('ea_version') or '-'} age={age_text}"
        )

    for item in report.get("signals", []):
        live = item.get("api_live") or {}
        print(
            f"SIGNAL #{item.get('signal_id')} {item.get('code')} {item.get('symbol')} {item.get('direction')} "
            f"tickets={','.join(item.get('tickets') or [])} status={live.get('status')} "
            f"current={live.get('current_price')} pnl={live.get('floating_pnl')} "
            f"R={live.get('current_r')} volume={live.get('volume')} sync={live.get('last_sync')}"
        )
        for name, ok in item.get("checks", {}).items():
            print(f"  {'PASS' if ok else 'FAIL'} {name}")

    for item in report.get("unmatched_live_rows", []):
        print(
            f"UNMATCHED account={item.get('account_number')} ticket={item.get('ticket')} "
            f"signal_code={item.get('signal_code')} symbol={item.get('symbol')}"
        )

    for issue in report.get("issues", []):
        print(f"ISSUE: {issue}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only NEXUS MT5 Live PnL smoke test")
    parser.add_argument("--account", help="Limit diagnostics to one MT5 account number")
    parser.add_argument("--signal-code", help="Limit diagnostics to one NEXUS signal code")
    parser.add_argument("--require-live", action="store_true", help="Fail when there is no matching OPEN/PENDING live MT5 row")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    args = parser.parse_args()

    code, report = diagnose(account=args.account, signal_code=args.signal_code, require_live=args.require_live)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        _print_human(report)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
