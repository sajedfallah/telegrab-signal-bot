from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from app import db
from app.autotrade.symbol_registry import normalize_symbol
from app.market_candles import init_market_candle_schema


SNAPSHOT_VERSION = "ai-market-snapshot-v1"

DEFAULT_TIMEFRAMES = ("H4", "H1", "M15", "M5")

_TIMEFRAME_ALIASES = {
    "1D": "D1",
    "D1": "D1",
    "4H": "H4",
    "H4": "H4",
    "1H": "H1",
    "H1": "H1",
    "15M": "M15",
    "M15": "M15",
    "5M": "M5",
    "M5": "M5",
    "1M": "M1",
    "M1": "M1",
}


def _tf(value: str) -> str:
    key = str(value or "").strip().upper()

    if key not in _TIMEFRAME_ALIASES:
        raise ValueError(f"unsupported timeframe: {value}")

    return _TIMEFRAME_ALIASES[key]


def _age_seconds(value: str | None) -> float | None:
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        return max(
            0.0,
            (
                datetime.now(timezone.utc)
                - parsed.astimezone(timezone.utc)
            ).total_seconds(),
        )

    except (TypeError, ValueError):
        return None


def _candidate_accounts(
    con,
    *,
    symbol: str,
    timeframes: tuple[str, ...],
) -> list[str]:
    placeholders = ",".join("?" for _ in timeframes)

    rows = con.execute(
        f"""
        SELECT
            account_number,
            COUNT(DISTINCT timeframe) AS tf_count,
            MAX(captured_at) AS latest_capture
        FROM mt5_market_candles
        WHERE symbol=?
          AND timeframe IN ({placeholders})
        GROUP BY account_number
        HAVING COUNT(DISTINCT timeframe)=?
        ORDER BY latest_capture DESC
        """,
        (
            symbol,
            *timeframes,
            len(timeframes),
        ),
    ).fetchall()

    return [
        str(row["account_number"])
        for row in rows
    ]


def load_market_snapshot(
    *,
    symbol: str,
    timeframes: Iterable[str] = DEFAULT_TIMEFRAMES,
    candle_limit: int = 200,
) -> dict[str, Any]:
    """
    Load a read-only market snapshot from existing NEXUS MT5 feed.

    No signal publication, execution, order placement, position mutation,
    or strategy gating occurs here.
    """

    init_market_candle_schema()

    canonical = normalize_symbol(symbol)

    requested = tuple(
        dict.fromkeys(
            _tf(value)
            for value in timeframes
        )
    )

    if not requested:
        raise ValueError("at least one timeframe is required")

    candle_limit = max(20, min(500, int(candle_limit)))

    with db.conn() as con:
        accounts = _candidate_accounts(
            con,
            symbol=canonical,
            timeframes=requested,
        )

        if not accounts:
            raise RuntimeError(
                f"no MT5 account has all requested timeframes "
                f"for {canonical}: {','.join(requested)}"
            )

        selected_account: str | None = None
        quote_row = None

        for account in accounts:
            candidate_quote = con.execute(
                """
                SELECT
                    account_number,
                    symbol,
                    broker_symbol,
                    bid,
                    ask,
                    digits,
                    quote_time_ms,
                    captured_at
                FROM mt5_market_quotes
                WHERE account_number=?
                  AND symbol=?
                LIMIT 1
                """,
                (
                    account,
                    canonical,
                ),
            ).fetchone()

            if candidate_quote:
                selected_account = account
                quote_row = candidate_quote
                break

        if selected_account is None:
            selected_account = accounts[0]

        candle_map: dict[str, list[dict[str, Any]]] = {}
        feed_meta: dict[str, dict[str, Any]] = {}

        for timeframe in requested:
            rows = con.execute(
                """
                SELECT
                    bar_time,
                    open,
                    high,
                    low,
                    close,
                    tick_volume,
                    broker_symbol,
                    digits,
                    captured_at
                FROM mt5_market_candles
                WHERE account_number=?
                  AND symbol=?
                  AND timeframe=?
                ORDER BY bar_time DESC
                LIMIT ?
                """,
                (
                    selected_account,
                    canonical,
                    timeframe,
                    candle_limit,
                ),
            ).fetchall()

            if not rows:
                raise RuntimeError(
                    f"missing {canonical} {timeframe} candles "
                    f"for account {selected_account}"
                )

            latest_capture = str(rows[0]["captured_at"] or "") or None

            candle_map[timeframe] = [
                {
                    "time": int(row["bar_time"]),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "tick_volume": float(row["tick_volume"] or 0.0),
                }
                for row in reversed(rows)
            ]

            feed_meta[timeframe] = {
                "count": len(rows),
                "captured_at": latest_capture,
                "age_seconds": (
                    round(_age_seconds(latest_capture), 1)
                    if _age_seconds(latest_capture) is not None
                    else None
                ),
                "broker_symbol": str(
                    rows[0]["broker_symbol"] or canonical
                ),
                "digits": (
                    int(rows[0]["digits"])
                    if rows[0]["digits"] is not None
                    else None
                ),
            }

        if quote_row:
            quote = {
                "available": True,
                "bid": float(quote_row["bid"]),
                "ask": float(quote_row["ask"]),
                "digits": (
                    int(quote_row["digits"])
                    if quote_row["digits"] is not None
                    else None
                ),
                "broker_symbol": str(
                    quote_row["broker_symbol"] or canonical
                ),
                "quote_time_ms": int(quote_row["quote_time_ms"]),
                "captured_at": str(
                    quote_row["captured_at"] or ""
                ) or None,
            }

            age = _age_seconds(quote["captured_at"])

            quote["age_seconds"] = (
                round(age, 1)
                if age is not None
                else None
            )

        else:
            latest_m5 = (
                candle_map.get("M5")
                or candle_map.get("M15")
                or next(iter(candle_map.values()))
            )

            fallback_price = float(
                latest_m5[-1]["close"]
            )

            inferred_digits = next(
                (
                    meta["digits"]
                    for meta in feed_meta.values()
                    if meta["digits"] is not None
                ),
                2,
            )

            quote = {
                "available": False,
                "bid": fallback_price,
                "ask": fallback_price,
                "digits": inferred_digits,
                "broker_symbol": next(
                    iter(feed_meta.values())
                )["broker_symbol"],
                "quote_time_ms": None,
                "captured_at": None,
                "age_seconds": None,
            }

    freshness_values = [
        meta["age_seconds"]
        for meta in feed_meta.values()
        if meta["age_seconds"] is not None
    ]

    max_feed_age = (
        max(freshness_values)
        if freshness_values
        else None
    )

    return {
        "snapshot_version": SNAPSHOT_VERSION,
        "source": "NEXUS / MT5",
        "symbol": canonical,
        "account_number": selected_account,
        "timeframes": list(requested),
        "quote": quote,
        "candles": candle_map,
        "feed": feed_meta,
        "max_feed_age_seconds": max_feed_age,
        "read_only": True,
    }
