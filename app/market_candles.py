from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field, field_validator, model_validator

from . import db
from .autotrade.service import AutoTradeError, authorize_admin_mt5
from .autotrade.symbol_registry import normalize_symbol

router = APIRouter(tags=["NEXUS Market Candles"])

_ALLOWED_TIMEFRAMES = {
    "1M": "M1", "M1": "M1",
    "5M": "M5", "M5": "M5",
    "15M": "M15", "M15": "M15",
    "30M": "M30", "M30": "M30",
    "1H": "H1", "H1": "H1",
    "4H": "H4", "H4": "H4",
    "1D": "D1", "D1": "D1",
}
_PUBLIC_TIMEFRAMES = {"M1": "1m", "M5": "5m", "M15": "15m", "M30": "30m", "H1": "1h", "H4": "4h", "D1": "1D"}
_MAX_SERIES = 50
_MAX_CANDLES_PER_SERIES = 500
_RETAIN_PER_SERIES = 1500
_STALE_SECONDS = 30


def _tf(value: str) -> str:
    raw = str(value or "").strip().upper()
    if raw not in _ALLOWED_TIMEFRAMES:
        raise ValueError("unsupported timeframe")
    return _ALLOWED_TIMEFRAMES[raw]


def init_market_candle_schema() -> None:
    with db.conn() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS mt5_market_candles (
                account_number TEXT NOT NULL,
                symbol TEXT NOT NULL,
                broker_symbol TEXT,
                timeframe TEXT NOT NULL,
                bar_time INTEGER NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                tick_volume REAL NOT NULL DEFAULT 0,
                digits INTEGER,
                captured_at TEXT NOT NULL,
                PRIMARY KEY(account_number, symbol, timeframe, bar_time)
            );
            CREATE INDEX IF NOT EXISTS idx_mt5_market_candles_lookup
                ON mt5_market_candles(symbol, timeframe, bar_time DESC);
            CREATE INDEX IF NOT EXISTS idx_mt5_market_candles_capture
                ON mt5_market_candles(account_number, captured_at DESC);

            CREATE TABLE IF NOT EXISTS mt5_market_quotes (
                account_number TEXT NOT NULL,
                symbol TEXT NOT NULL,
                broker_symbol TEXT NOT NULL,
                bid REAL NOT NULL,
                ask REAL NOT NULL,
                digits INTEGER,
                quote_time_ms INTEGER NOT NULL,
                captured_at TEXT NOT NULL,
                PRIMARY KEY(account_number, symbol)
            );
            CREATE INDEX IF NOT EXISTS idx_mt5_market_quotes_capture
                ON mt5_market_quotes(account_number, captured_at DESC);
            """
        )


class CandlePoint(BaseModel):
    time: int = Field(gt=0)
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    tick_volume: float = Field(default=0.0, ge=0)

    @field_validator("open", "high", "low", "close", "tick_volume")
    @classmethod
    def finite(cls, value: float) -> float:
        value = float(value)
        if not math.isfinite(value):
            raise ValueError("candle values must be finite")
        return value

    @model_validator(mode="after")
    def valid_ohlc(self):
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("high is below OHLC range")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("low is above OHLC range")
        return self


class CandleSeries(BaseModel):
    symbol: str = Field(min_length=3, max_length=32)
    broker_symbol: str | None = Field(default=None, max_length=64)
    timeframe: str = Field(min_length=2, max_length=8)
    digits: int | None = Field(default=None, ge=0, le=10)
    candles: list[CandlePoint] = Field(min_length=1, max_length=_MAX_CANDLES_PER_SERIES)

    @field_validator("timeframe")
    @classmethod
    def valid_timeframe(cls, value: str) -> str:
        return _tf(value)


class MarketQuote(BaseModel):
    symbol: str = Field(min_length=3, max_length=32)
    broker_symbol: str = Field(min_length=1, max_length=64)
    bid: float = Field(gt=0)
    ask: float = Field(gt=0)
    digits: int | None = Field(default=None, ge=0, le=10)
    time_msc: int = Field(gt=0)

    @field_validator("bid", "ask")
    @classmethod
    def finite_quote(cls, value: float) -> float:
        value = float(value)
        if not math.isfinite(value):
            raise ValueError("quote values must be finite")
        return value

    @model_validator(mode="after")
    def valid_spread(self):
        if self.ask < self.bid:
            raise ValueError("ask must be greater than or equal to bid")
        return self


class MarketFeedRequest(BaseModel):
    account_number: str = Field(min_length=3, max_length=32)
    broker: str | None = Field(default=None, max_length=128)
    server: str | None = Field(default=None, max_length=128)
    ea_version: str | None = Field(default=None, max_length=32)
    quotes: list[MarketQuote] = Field(default_factory=list, max_length=_MAX_SERIES)
    series: list[CandleSeries] = Field(min_length=1, max_length=_MAX_SERIES)


def _admin_auth(account: str, admin_mode: str | None, admin_token: str | None) -> dict[str, Any]:
    if str(admin_mode or "").strip().lower() not in {"1", "true", "yes", "on"}:
        raise HTTPException(status_code=403, detail="admin mode is required for broker candle feed")
    try:
        return authorize_admin_mt5(account, admin_token)
    except AutoTradeError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/api/v1/autotrade/admin/market-candles")
def ingest_market_candles(
    req: MarketFeedRequest,
    x_mt5_account: str | None = Header(None, alias="X-MT5-Account"),
    x_admin_mode: str | None = Header(None, alias="X-Admin-Mode"),
    x_admin_token: str | None = Header(None, alias="X-NEXUS-Admin-Token"),
) -> dict[str, Any]:
    account = str(x_mt5_account or req.account_number or "").strip()
    if account != str(req.account_number).strip():
        raise HTTPException(status_code=409, detail="MT5 account header/body mismatch")
    _admin_auth(account, x_admin_mode, x_admin_token)
    init_market_candle_schema()

    captured_at = db.now_iso()
    accepted = 0
    accepted_quotes = 0
    touched: list[tuple[str, str]] = []
    with db.conn() as con:
        for quote in req.quotes:
            symbol = normalize_symbol(quote.symbol)
            broker_symbol = str(quote.broker_symbol).strip()
            con.execute(
                """INSERT INTO mt5_market_quotes
                   (account_number,symbol,broker_symbol,bid,ask,digits,quote_time_ms,captured_at)
                   VALUES(?,?,?,?,?,?,?,?)
                   ON CONFLICT(account_number,symbol) DO UPDATE SET
                     broker_symbol=excluded.broker_symbol,
                     bid=excluded.bid,ask=excluded.ask,digits=excluded.digits,
                     quote_time_ms=excluded.quote_time_ms,captured_at=excluded.captured_at""",
                (
                    account, symbol, broker_symbol, float(quote.bid), float(quote.ask),
                    quote.digits, int(quote.time_msc), captured_at,
                ),
            )
            accepted_quotes += 1

        for series in req.series:
            symbol = normalize_symbol(series.symbol)
            timeframe = _tf(series.timeframe)
            broker_symbol = str(series.broker_symbol or series.symbol).strip()
            touched.append((symbol, timeframe))
            for candle in series.candles:
                con.execute(
                    """INSERT INTO mt5_market_candles
                       (account_number,symbol,broker_symbol,timeframe,bar_time,open,high,low,close,tick_volume,digits,captured_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(account_number,symbol,timeframe,bar_time) DO UPDATE SET
                         broker_symbol=excluded.broker_symbol,
                         open=excluded.open,high=excluded.high,low=excluded.low,close=excluded.close,
                         tick_volume=excluded.tick_volume,digits=excluded.digits,captured_at=excluded.captured_at""",
                    (
                        account, symbol, broker_symbol, timeframe, int(candle.time),
                        float(candle.open), float(candle.high), float(candle.low), float(candle.close),
                        float(candle.tick_volume), series.digits, captured_at,
                    ),
                )
                accepted += 1

        for symbol, timeframe in set(touched):
            con.execute(
                """DELETE FROM mt5_market_candles
                   WHERE account_number=? AND symbol=? AND timeframe=? AND bar_time NOT IN (
                     SELECT bar_time FROM mt5_market_candles
                     WHERE account_number=? AND symbol=? AND timeframe=?
                     ORDER BY bar_time DESC LIMIT ?
                   )""",
                (account, symbol, timeframe, account, symbol, timeframe, _RETAIN_PER_SERIES),
            )

    return {
        "ok": True,
        "account_number": account,
        "series": len(req.series),
        "candles": accepted,
        "quotes": accepted_quotes,
        "captured_at": captured_at,
    }


def _age_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds())
    except ValueError:
        return None


@router.get("/miniapp/api/market-candles")
def market_candles(
    symbol: str = Query(min_length=3, max_length=32),
    timeframe: str = Query(default="5m", min_length=2, max_length=8),
    limit: int = Query(default=500, ge=1, le=500),
) -> dict[str, Any]:
    init_market_candle_schema()
    canonical = normalize_symbol(symbol)
    try:
        tf = _tf(timeframe)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    with db.conn() as con:
        source = con.execute(
            """SELECT account_number,broker_symbol,digits,MAX(captured_at) AS captured_at
               FROM mt5_market_candles
               WHERE symbol=? AND timeframe=?
               GROUP BY account_number,broker_symbol,digits
               ORDER BY captured_at DESC LIMIT 1""",
            (canonical, tf),
        ).fetchone()
        if not source:
            raise HTTPException(status_code=503, detail=f"MT5 candle feed unavailable for {canonical} {tf}")
        rows = con.execute(
            """SELECT bar_time,open,high,low,close,tick_volume,captured_at
               FROM mt5_market_candles
               WHERE account_number=? AND symbol=? AND timeframe=?
               ORDER BY bar_time DESC LIMIT ?""",
            (str(source["account_number"]), canonical, tf, int(limit)),
        ).fetchall()

    candles = [
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
    latest_capture = str(source["captured_at"] or "") or None
    age = _age_seconds(latest_capture)
    return {
        "ok": True,
        "symbol": canonical,
        "broker_symbol": str(source["broker_symbol"] or canonical),
        "timeframe": _PUBLIC_TIMEFRAMES[tf],
        "mt5_timeframe": tf,
        "source": "NEXUS / MT5",
        "account_number": str(source["account_number"]),
        "digits": int(source["digits"]) if source["digits"] is not None else None,
        "captured_at": latest_capture,
        "age_seconds": round(age, 1) if age is not None else None,
        "stale": age is None or age > _STALE_SECONDS,
        "candles": candles,
    }
