"""Opt-in broker timestamp validation; never changes the existing market feed.

Clock calibration is caller-supplied evidence, not inferred from market prices.
Only intraday bars with a captured, contiguous successor establish completion.
"""
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from contextlib import closing
import sqlite3

from .lifecycle_evidence_v33 import Candle, SECONDS


@dataclass(frozen=True)
class BrokerClock:
    source: str
    reference: str
    offset_seconds: int
    valid_from: int
    valid_until: int

    def __post_init__(self):
        if any(type(v) is not str or not v for v in (self.source,self.reference)):
            raise ValueError("source and clock-calibration reference required")
        if any(type(v) is not int for v in (self.offset_seconds,self.valid_from,self.valid_until)):
            raise ValueError("explicit integer UTC clock policy required")
        if not -14*3600<=self.offset_seconds<=14*3600 or self.valid_from>=self.valid_until:
            raise ValueError("invalid clock calibration window/offset")


@dataclass(frozen=True)
class BrokerSeries:
    symbol: str
    timeframe: str
    clock_reference: str
    decision_at: int
    candles: tuple[Candle,...]


def _capture(value):
    if type(value) is not str:
        raise ValueError("aware UTC capture timestamp required")
    parsed=datetime.fromisoformat(value.replace("Z","+00:00"))
    if parsed.utcoffset() is None:
        raise ValueError("capture timezone is missing")
    return parsed.timestamp()


def validate_broker_series(rows, *, symbol, timeframe, clock: BrokerClock,
                           decision_at: int, max_capture_age: int = 30):
    if timeframe not in {"M1","M5","M15","H1","H4"}:
        raise ValueError("intraday timeframe required; daily sessions need separate policy")
    if type(clock) is not BrokerClock or type(decision_at) is not int:
        raise ValueError("broker clock and decision timestamp required")
    if type(max_capture_age) is not int or max_capture_age<0:
        raise ValueError("invalid capture freshness policy")
    if not clock.valid_from<=decision_at<clock.valid_until:
        raise ValueError("decision outside calibration validity")
    parsed=[]
    for row in rows:
        raw=row["bar_time"]
        if type(raw) is not int:
            raise ValueError("broker timestamp must be integer seconds, not milliseconds")
        opened=raw-clock.offset_seconds
        captured=_capture(row["captured_at"])
        if not clock.valid_from<=opened<clock.valid_until or not opened<=captured<=decision_at:
            raise ValueError("future/source-clock inconsistent candle")
        c=Candle(symbol,timeframe,opened,opened+SECONDS[timeframe],
                 row["open"],row["high"],row["low"],row["close"],clock.source)
        if parsed and opened<parsed[-1][0].closed_at:
            raise ValueError("duplicate, overlapping or unordered bars")
        parsed.append((c,captured))
    if len(parsed)<2 or decision_at-parsed[-1][1]>max_capture_age:
        raise ValueError("insufficient or stale broker capture")
    closed=[]
    for (c,captured),(successor,next_capture) in zip(parsed,parsed[1:]):
        # A weekend/session gap does not prove when the preceding bar closed.
        if successor.opened_at!=c.closed_at:
            raise ValueError("missing successor at expected candle boundary")
        if captured<c.closed_at or next_capture<successor.opened_at or c.closed_at>decision_at:
            raise ValueError("capture predates completed candle")
        closed.append(c)
    if not closed:
        raise ValueError("no broker-confirmed completed bars")
    return BrokerSeries(symbol,timeframe,clock.reference,decision_at,tuple(closed))


def read_broker_series(db_path, *, account, symbol, timeframe, clock, decision_at, limit=220):
    """Read one authorized export with SQLite mode=ro; no schema initialization."""
    path=Path(db_path).resolve()
    if not path.is_file() or any(p.lower()=="nexus_deploy" for p in path.parts):
        raise ValueError("isolated existing broker export required")
    if not account or type(limit) is not int or not 2<=limit<=500:
        raise ValueError("account and bounded candle limit required")
    with closing(sqlite3.connect(path.as_uri()+"?mode=ro",uri=True)) as db:
        db.row_factory=sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        rows=tuple(db.execute("""SELECT bar_time,open,high,low,close,captured_at
            FROM mt5_market_candles WHERE account_number=? AND symbol=? AND timeframe=?
            ORDER BY bar_time DESC LIMIT ?""",(account,symbol,timeframe,limit)))
    return validate_broker_series(tuple(reversed(rows)),symbol=symbol,timeframe=timeframe,
                                  clock=clock,decision_at=decision_at)
