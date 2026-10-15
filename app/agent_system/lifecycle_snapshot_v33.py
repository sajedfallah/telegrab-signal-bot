"""Strict snapshot boundary for isolated lifecycle adapters; no runtime wiring.

Explicit source close timestamps are mandatory. The existing MT5 adapter does
not yet provide them, so it cannot silently enter this contract.
"""
from dataclasses import dataclass
from math import isfinite

from .contracts import MarketSnapshot
from .lifecycle_evidence_v33 import Candle


@dataclass(frozen=True)
class EvidenceFrame:
    snapshot_ref: str
    context_ref: str
    symbol: str
    timeframe: str
    decision_at: int
    bid: float
    ask: float
    candles: tuple[Candle, ...]


def evidence_frame(snapshot: MarketSnapshot, timeframe: str, *, context_ref: str,
                   max_age_ms: int = 30_000) -> EvidenceFrame:
    """Copy and validate closed evidence without deriving confirmation metadata."""
    if timeframe not in {"M1","M5"} or type(context_ref) is not str or not context_ref:
        raise ValueError("explicit execution timeframe and shared context reference required")
    if type(max_age_ms) is not int or max_age_ms < 0:
        raise ValueError("invalid freshness policy")
    if snapshot.missing_data or snapshot.data_freshness_ms > max_age_ms:
        raise ValueError("missing or stale snapshot")
    bid,ask=snapshot.bid,snapshot.ask
    if bid is None or ask is None or not all(isfinite(v) and v>0 for v in (bid,ask)) or ask<bid:
        raise ValueError("executable quotes required")
    at=int(snapshot.as_of.timestamp())
    completed=[]
    previous=None
    rows=snapshot.timeframes.get(timeframe,())
    for index,row in enumerate(rows):
        try:
            c=Candle(snapshot.symbol,timeframe,row["time"],row["closed_at"],
                     row["open"],row["high"],row["low"],row["close"],snapshot.source)
        except (KeyError,TypeError) as exc:
            raise ValueError("explicit candle close/provenance metadata required") from exc
        if c.opened_at>at or previous is not None and c.opened_at<previous.closed_at:
            raise ValueError("future, duplicate or overlapping source candles")
        if c.closed_at>at:
            if index!=len(rows)-1:
                raise ValueError("unclosed nontrailing candle")
            # A live bar is quote context only, never completed event evidence.
        else:
            completed.append(c)
        previous=c
    if not completed:
        raise ValueError("no verified closed candles")
    return EvidenceFrame(snapshot.snapshot_id,context_ref,snapshot.symbol,timeframe,
                         at,float(bid),float(ask),tuple(completed))
