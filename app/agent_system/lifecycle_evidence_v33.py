"""Immutable research evidence. No detector, publisher or execution authority."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from math import isfinite

SECONDS = {"M1": 60, "M5": 300, "M15": 900, "H1": 3600, "H4": 14400, "D1": 86400}


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value) -> str:
    return sha256(canonical(value).encode()).hexdigest()


@dataclass(frozen=True)
class Candle:
    symbol: str
    timeframe: str
    opened_at: int
    closed_at: int
    open: float
    high: float
    low: float
    close: float
    source: str

    def __post_init__(self):
        if self.timeframe not in SECONDS or any(type(v) is not str or not v for v in (self.symbol,self.source)):
            raise ValueError("candle provenance required")
        if type(self.opened_at) is not int or type(self.closed_at) is not int:
            raise ValueError("integer UTC timestamps required")
        if self.closed_at - self.opened_at != SECONDS[self.timeframe]:
            raise ValueError("explicit candle interval required")
        if not all(type(v) in (float,int) and isfinite(v) and v > 0 for v in (self.open, self.high, self.low, self.close)):
            raise ValueError("invalid candle price")
        if not self.low <= min(self.open, self.close) <= max(self.open, self.close) <= self.high:
            raise ValueError("invalid candle geometry")
        for key in ("open","high","low","close"):
            object.__setattr__(self,key,float(getattr(self,key)))

    @property
    def identity(self):
        return digest(asdict(self))


@dataclass(frozen=True)
class Sweep:
    candle: Candle
    liquidity: Candle


@dataclass(frozen=True)
class MSS:
    candle: Candle
    swing: Candle
    swing_confirmation: Candle
    sweep_event: str


@dataclass(frozen=True)
class Displacement:
    candle: Candle
    baseline: tuple[Candle, ...]
    mss_event: str


@dataclass(frozen=True)
class FVG:
    left: Candle
    middle: Candle
    right: Candle
    displacement_event: str


@dataclass(frozen=True)
class Retest:
    candle: Candle
    fvg_event: str


@dataclass(frozen=True)
class Observation:
    """Location evidence for POI selection/approach/touch; never an entry grant."""
    candle: Candle
    reason: str


@dataclass(frozen=True)
class Decision:
    reason: str


EVIDENCE_TYPES = {x.__name__: x for x in (Sweep, MSS, Displacement, FVG, Retest, Observation, Decision)}


def encode_evidence(evidence):
    if type(evidence).__name__ not in EVIDENCE_TYPES or type(evidence) not in EVIDENCE_TYPES.values():
        raise ValueError("unsupported evidence contract")
    data=asdict(evidence)
    for key in ("candle", "liquidity", "swing", "swing_confirmation", "left", "middle", "right"):
        if key in data and type(getattr(evidence,key)) is not Candle:
            raise ValueError("immutable source candle required")
    if "baseline" in data and (type(evidence.baseline) is not tuple or any(type(c) is not Candle for c in evidence.baseline)):
        raise ValueError("immutable displacement baseline required")
    for key in ("sweep_event", "mss_event", "displacement_event", "fvg_event", "reason"):
        if key in data and (type(data[key]) is not str or not data[key]):
            raise ValueError("evidence reference/reason required")
    return {"kind": type(evidence).__name__, "data": asdict(evidence)}


def decode_evidence(value):
    data = dict(value["data"])
    for key in ("candle", "liquidity", "swing", "swing_confirmation", "left", "middle", "right"):
        if key in data:
            data[key] = Candle(**data[key])
    if "baseline" in data:
        data["baseline"] = tuple(Candle(**c) for c in data["baseline"])
    return EVIDENCE_TYPES[value["kind"]](**data)
