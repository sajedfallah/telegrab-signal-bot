from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

from .. import db


@dataclass(frozen=True)
class Period:
    key: str
    start_iso: str
    end_iso: str
    label_fa: str
    label_en: str


def period(key: str) -> Period:
    now = datetime.now(timezone.utc)
    key = key.lower()
    if key == "7":
        start = now - timedelta(days=7)
        return Period("7", start.isoformat(), now.isoformat(), "۷ روز اخیر", "Last 7 days")
    if key == "30":
        start = now - timedelta(days=30)
        return Period("30", start.isoformat(), now.isoformat(), "۳۰ روز اخیر", "Last 30 days")
    return Period("all", "2000-01-01T00:00:00+00:00", now.isoformat(), "کل دوره", "All time")


def _rows(p: Period):
    with db.conn() as con:
        return list(con.execute(
            """
            SELECT id,code,market_type,symbol,direction,entry_price,exit_price,result_value,result_unit,
                   rr_ratio,destination,trailing_code,trailing_name,created_at,closed_at
            FROM signals
            WHERE status='CLOSED' AND closed_at>=? AND closed_at<?
              AND COALESCE(cycle_id, ?) = ?
            ORDER BY closed_at DESC
            """,
            (p.start_iso, p.end_iso, db.current_cycle_id(), db.current_cycle_id()),
        ).fetchall())


def _summarize(rows: Iterable) -> dict:
    rows = list(rows)
    wins = sum(1 for r in rows if float(r["result_value"] or 0) > 0)
    losses = sum(1 for r in rows if float(r["result_value"] or 0) < 0)
    be = len(rows) - wins - losses
    forex_pips = sum(float(r["result_value"] or 0) for r in rows if str(r["result_unit"] or "").upper() == "PIPS")
    crypto_pct = sum(float(r["result_value"] or 0) for r in rows if str(r["result_unit"] or "").upper() == "PERCENT")
    raw_pct = 0.0
    rr_values = []
    for r in rows:
        entry = float(r["entry_price"] or 0)
        exit_price = float(r["exit_price"] or 0)
        if entry and exit_price:
            direction = str(r["direction"] or "").upper()
            delta = exit_price - entry if direction in {"BUY", "LONG"} else entry - exit_price
            raw_pct += (delta / entry) * 100
        if r["rr_ratio"] is not None:
            try:
                rr_values.append(float(r["rr_ratio"]))
            except (TypeError, ValueError):
                pass
    total = len(rows)
    return {
        "total": total,
        "wins": wins,
        "losses": losses,
        "be": be,
        "win_rate": round((wins / total * 100) if total else 0, 1),
        "forex_pips": round(forex_pips, 1),
        "crypto_pct": round(crypto_pct, 2),
        "net_pct": round(raw_pct, 2),
        "avg_rr": round(sum(rr_values) / len(rr_values), 2) if rr_values else 0,
    }


def overview(key: str = "30") -> dict:
    p = period(key)
    rows = _rows(p)
    summary = _summarize(rows)
    with db.conn() as con:
        active = int(con.execute("SELECT COUNT(*) FROM signals WHERE status<>'CLOSED' AND COALESCE(cycle_id,?)=?", (db.current_cycle_id(), db.current_cycle_id())).fetchone()[0])
    return {"period": p, "active": active, **summary}


def symbols(key: str = "30", limit: int = 12) -> list[dict]:
    p = period(key)
    groups = defaultdict(list)
    for row in _rows(p):
        groups[str(row["symbol"] or "—").upper()].append(row)
    result = []
    for symbol, rows in groups.items():
        result.append({"symbol": symbol, **_summarize(rows)})
    result.sort(key=lambda item: (-item["total"], -item["win_rate"], item["symbol"]))
    return result[:limit]


def trailing(key: str = "30", limit: int = 10) -> list[dict]:
    p = period(key)
    groups = defaultdict(list)
    labels = {}
    for row in _rows(p):
        code = str(row["trailing_code"] or "NO_TRAILING")
        groups[code].append(row)
        labels[code] = str(row["trailing_name"] or "—")
    result = []
    for code, rows in groups.items():
        result.append({"code": code, "name": labels[code], **_summarize(rows)})
    result.sort(key=lambda item: (-item["total"], -item["win_rate"], item["code"]))
    return result[:limit]


def channels(key: str = "30") -> dict[str, dict]:
    p = period(key)
    rows = _rows(p)
    return {
        "FREE": _summarize([r for r in rows if str(r["destination"]).upper() in {"FREE", "BOTH"}]),
        "VIP": _summarize([r for r in rows if str(r["destination"]).upper() in {"VIP", "BOTH"}]),
    }
