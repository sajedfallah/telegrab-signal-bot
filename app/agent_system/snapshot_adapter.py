from __future__ import annotations

import hashlib
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .. import db
from ..autotrade.symbol_registry import normalize_symbol
from ..market_candles import init_market_candle_schema
from .contracts import MarketSnapshot


_TIMEFRAMES = ("D1", "H1", "M15", "M5", "M1")
_REQUIRED_TIMEFRAMES = ("H1", "M15", "M5")
_QUOTE_MAX_AGE_MS = 15_000
_CANDLE_CAPTURE_MAX_AGE_MS = 30_000
_SHADOW_DB_ENV = "NEXUS_AGENT_MARKET_DB_PATH"


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _age_ms(value: datetime | None, now: datetime) -> int | None:
    if value is None:
        return None
    return max(0, int((now - value).total_seconds() * 1000))


def _session(now: datetime) -> str:
    hour = now.hour
    if 7 <= hour < 12:
        return "LONDON"
    if 12 <= hour < 17:
        return "LONDON_NEW_YORK_OVERLAP"
    if 17 <= hour < 21:
        return "NEW_YORK"
    return "OFF_PEAK"


def _snapshot_id(account: str, symbol: str, as_of: datetime, quote_time_ms: int | None) -> str:
    raw = f"{account}|{symbol}|{as_of.isoformat()}|{quote_time_ms or 0}"
    return "snap-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


@contextmanager
def _market_conn() -> Iterator[sqlite3.Connection]:
    """Open the configured shadow market DB read-only, or use the app DB normally.

    NEXUS_AGENT_MARKET_DB_PATH is intentionally shadow-only. When present we
    never initialize schemas and SQLite itself enforces mode=ro.
    """
    configured = os.getenv(_SHADOW_DB_ENV, "").strip()
    if not configured:
        init_market_candle_schema()
        with db.conn() as con:
            yield con
        return

    path = Path(configured).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"shadow market database not found: {path}")
    con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=10.0)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only = ON")
    con.execute("PRAGMA busy_timeout = 10000")
    try:
        yield con
    finally:
        con.close()


def build_mt5_snapshot(account: str, symbol: str, *, candle_limit: int = 220, now_utc: datetime | None = None) -> MarketSnapshot:
    """Build an immutable snapshot from existing MT5 market tables."""
    now = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
    canonical = normalize_symbol(symbol)
    account = str(account).strip()
    if not account:
        raise ValueError("account is required")
    missing: list[str] = []
    bid = ask = None
    quote_time_ms: int | None = None
    freshness_candidates: list[int] = []
    with _market_conn() as con:
        quote = con.execute("SELECT bid,ask,quote_time_ms,captured_at FROM mt5_market_quotes WHERE account_number=? AND symbol=? LIMIT 1", (account, canonical)).fetchone()
        if quote:
            raw_bid, raw_ask = float(quote["bid"]), float(quote["ask"])
            quote_time_ms = int(quote["quote_time_ms"])
            capture_age = _age_ms(_parse_iso(str(quote["captured_at"] or "")), now)
            tick_age = max(0, int(now.timestamp() * 1000) - quote_time_ms)
            if raw_bid > 0 and raw_ask >= raw_bid and capture_age is not None and capture_age <= _QUOTE_MAX_AGE_MS and tick_age <= _QUOTE_MAX_AGE_MS:
                bid, ask = raw_bid, raw_ask
                freshness_candidates.extend((capture_age, tick_age))
            else:
                missing.append("quote")
        else:
            missing.append("quote")
        timeframes: dict[str, tuple[dict[str, Any], ...]] = {}
        for timeframe in _TIMEFRAMES:
            limit = 20 if timeframe == "D1" else max(20, min(500, int(candle_limit)))
            rows = con.execute("SELECT bar_time,open,high,low,close,tick_volume,captured_at FROM mt5_market_candles WHERE account_number=? AND symbol=? AND timeframe=? ORDER BY bar_time DESC LIMIT ?", (account, canonical, timeframe, limit)).fetchall()
            valid: list[dict[str, Any]] = []
            for row in reversed(rows):
                o, h, l, c = (float(row[x]) for x in ("open", "high", "low", "close"))
                if min(o, h, l, c) <= 0 or h < max(o, c, l) or l > min(o, c, h):
                    continue
                valid.append({"time": int(row["bar_time"]), "open": o, "high": h, "low": l, "close": c, "tick_volume": float(row["tick_volume"] or 0)})
            timeframes[timeframe] = tuple(valid)
            minimum = 10 if timeframe == "D1" else 20
            if len(valid) < minimum and (timeframe == "D1" or timeframe in _REQUIRED_TIMEFRAMES):
                missing.append(f"candles:{timeframe}")
            if rows:
                capture_age = _age_ms(_parse_iso(str(rows[0]["captured_at"] or "")), now)
                if timeframe in _REQUIRED_TIMEFRAMES:
                    if capture_age is None or capture_age > _CANDLE_CAPTURE_MAX_AGE_MS:
                        missing.append(f"stale_candles:{timeframe}")
                    else:
                        freshness_candidates.append(capture_age)
    return MarketSnapshot(snapshot_id=_snapshot_id(account, canonical, now, quote_time_ms), symbol=canonical, as_of=now, source="MT5_MARKET_FEED", timeframes=timeframes, bid=bid, ask=ask, last=None, session=_session(now), data_freshness_ms=max(freshness_candidates) if freshness_candidates else 10**9, missing_data=tuple(dict.fromkeys(missing)))
