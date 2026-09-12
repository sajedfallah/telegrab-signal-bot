from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

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
    if key == "90":
        start = now - timedelta(days=90)
        return Period("90", start.isoformat(), now.isoformat(), "۹۰ روز اخیر", "Last 90 days")
    return Period("all", "2000-01-01T00:00:00+00:00", now.isoformat(), "کل دوره", "All time")


def _rows(p: Period):
    with db.conn() as con:
        return list(con.execute(
            """
            SELECT id,code,market_type,symbol,direction,entry_price,stop_loss,exit_price,result_value,result_unit,
                   rr_ratio,destination,trailing_code,trailing_name,created_at,opened_at,closed_at,
                   free_message_id,vip_message_id,free_last_message_id,vip_last_message_id
            FROM signals
            WHERE status='CLOSED' AND closed_at>=? AND closed_at<?
              AND COALESCE(cycle_id, ?) = ?
            ORDER BY closed_at DESC
            """,
            (p.start_iso, p.end_iso, db.current_cycle_id(), db.current_cycle_id()),
        ).fetchall())


def _realized_r(row: Any) -> float | None:
    try:
        entry = float(row["entry_price"] or 0)
        stop = float(row["stop_loss"] or 0)
        exit_price = float(row["exit_price"] or 0)
    except (TypeError, ValueError, KeyError, IndexError):
        return None
    initial_r = abs(entry - stop)
    if entry <= 0 or stop <= 0 or exit_price <= 0 or initial_r <= 0:
        return None
    direction = str(row["direction"] or "").upper()
    if direction not in {"BUY", "LONG", "SELL", "SHORT"}:
        return None
    displacement = exit_price - entry if direction in {"BUY", "LONG"} else entry - exit_price
    return round(displacement / initial_r, 4)


def _r_metrics(rows: Iterable) -> dict[str, Any]:
    ordered = sorted(list(rows), key=lambda row: str(row["closed_at"] or ""))
    values = [value for value in (_realized_r(row) for row in ordered) if value is not None]
    if not values:
        return {
            "r_sample_size": 0,
            "net_r": None,
            "average_realized_r": None,
            "profit_factor_r": None,
            "current_losing_streak": None,
            "maximum_losing_streak": None,
            "max_drawdown_r": None,
            "equity_curve_r": [],
        }

    gross_profit = sum(value for value in values if value > 0)
    gross_loss = abs(sum(value for value in values if value < 0))
    profit_factor = round(gross_profit / gross_loss, 4) if gross_loss > 0 else None

    current_losing = 0
    for value in reversed(values):
        if value < 0:
            current_losing += 1
        else:
            break

    maximum_losing = 0
    running_losing = 0
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    curve = []
    for value in values:
        if value < 0:
            running_losing += 1
            maximum_losing = max(maximum_losing, running_losing)
        else:
            running_losing = 0
        equity = round(equity + value, 4)
        peak = max(peak, equity)
        drawdown = round(equity - peak, 4)
        max_drawdown = min(max_drawdown, drawdown)
        curve.append(equity)

    return {
        "r_sample_size": len(values),
        "net_r": round(sum(values), 4),
        "average_realized_r": round(sum(values) / len(values), 4),
        "profit_factor_r": profit_factor,
        "current_losing_streak": current_losing,
        "maximum_losing_streak": maximum_losing,
        "max_drawdown_r": round(max_drawdown, 4),
        "equity_curve_r": curve,
    }


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
        **_r_metrics(rows),
    }


def overview(key: str = "30") -> dict:
    p = period(key)
    rows = _rows(p)
    summary = _summarize(rows)
    cycle = db.current_cycle_id()
    with db.conn() as con:
        active = int(con.execute(
            """SELECT COUNT(*) FROM signals
               WHERE UPPER(COALESCE(status,'')) NOT IN ('DRAFT','CLOSED','REJECTED','CANCELLED','EXPIRED','PUBLISH_FAILED')
                 AND COALESCE(cycle_id,?)=?""",
            (cycle, cycle),
        ).fetchone()[0])
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


def _access(row: Any) -> str:
    return "VIP" if str(row["destination"] or "FREE").upper() == "VIP" else "FREE"


def _result_source(row: Any) -> str:
    if _realized_r(row) is not None:
        return "CALCULATED"
    if row["result_value"] is not None:
        return "MANUAL"
    return "UNKNOWN"


def _first_target(signal_id: int) -> float | None:
    targets = db.get_signal_targets(signal_id)
    if not targets:
        return None
    try:
        return float(targets[0]["price"])
    except (TypeError, ValueError, KeyError, IndexError):
        return None


def _trade_row(row: Any) -> dict[str, Any]:
    realized_r = _realized_r(row)
    unit = str(row["result_unit"] or "").upper() or None
    realized_pnl = None
    if unit in {"USD", "$", "ACCOUNT_CURRENCY", "MONEY"} and row["result_value"] is not None:
        try:
            realized_pnl = float(row["result_value"])
        except (TypeError, ValueError):
            realized_pnl = None
    return {
        "id": int(row["id"]),
        "code": str(row["code"] or ""),
        "symbol": str(row["symbol"] or "—"),
        "direction": str(row["direction"] or ""),
        "access": _access(row),
        "status": "CLOSED",
        "open_time": row["opened_at"] or row["created_at"],
        "close_time": row["closed_at"],
        "initial_entry": row["entry_price"],
        "initial_sl": row["stop_loss"],
        "initial_tp": _first_target(int(row["id"])),
        "final_exit": row["exit_price"],
        "result_value": row["result_value"],
        "result_unit": unit,
        "realized_pnl": realized_pnl,
        "realized_r": realized_r,
        "result_source": _result_source(row),
    }


def trade_history(key: str = "30", *, limit: int = 20, offset: int = 0) -> dict[str, Any]:
    rows = _rows(period(key))
    total = len(rows)
    start = max(0, int(offset))
    stop = start + max(1, min(int(limit), 100))
    return {"total": total, "items": [_trade_row(row) for row in rows[start:stop]]}


def trade_detail(signal_id: int) -> dict[str, Any] | None:
    row = db.get_signal(int(signal_id))
    if not row or str(row["status"] or "").upper() != "CLOSED":
        return None
    result = _trade_row(row)
    result["targets"] = [
        {"target_no": int(item["target_no"]), "price": float(item["price"])}
        for item in db.get_signal_targets(int(signal_id))
    ]
    result["telegram"] = {
        "free_message_id": row["free_message_id"],
        "vip_message_id": row["vip_message_id"],
        "free_last_message_id": row["free_last_message_id"],
        "vip_last_message_id": row["vip_last_message_id"],
    }
    result["lifecycle"] = [
        {
            "action": str(item["action"] or ""),
            "detail_fa": str(item["detail_fa"] or ""),
            "detail_en": str(item["detail_en"] or ""),
            "value": item["value"],
            "free_message_id": item["free_message_id"],
            "vip_message_id": item["vip_message_id"],
            "created_at": item["created_at"],
        }
        for item in db.signal_updates(int(signal_id))
    ]
    return result


def methodology() -> dict[str, Any]:
    return {
        "scope": "published_nexus_signals",
        "account_return": False,
        "losses_are_retained": True,
        "be_is_retained": True,
        "win_loss_rule": "result_value > 0 = WIN; result_value < 0 = LOSS; otherwise BE",
        "realized_r_rule": "directional (final_exit - initial_entry) / abs(initial_entry - initial_sl)",
        "profit_factor_rule": "sum positive realized R / absolute sum negative realized R",
        "drawdown_rule": "peak-to-trough decline of cumulative realized R",
        "verification_note": "Signal performance is separate from per-account AutoTrade broker performance.",
        "insufficient_data_rule": "R-based metrics are null when Entry, Initial SL, or Final Exit is missing or invalid.",
    }
