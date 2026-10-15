"""Opt-in event-sourced lifecycle. Deliberately disconnected from all watchers.

All times are UTC epoch seconds supplied by the caller's decision clock. A
publication reservation is durable deduplication, not permission to send.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from enum import Enum
from math import isfinite
from pathlib import Path
from contextlib import contextmanager
import sqlite3

from .lifecycle_evidence_v33 import (
    Candle, Decision, Displacement, FVG, MSS, Observation, Retest, Sweep,
    canonical, decode_evidence, digest, encode_evidence,
)
import json


class State(str, Enum):
    DISCOVERED = "DISCOVERED"
    POI_SELECTED = "POI_SELECTED"
    APPROACHING_POI = "APPROACHING_POI"
    POI_TOUCHED = "POI_TOUCHED"
    LIQUIDITY_SWEPT = "LIQUIDITY_SWEPT"
    MSS_CONFIRMED = "MSS_CONFIRMED"
    DISPLACEMENT_CONFIRMED = "DISPLACEMENT_CONFIRMED"
    FVG_CREATED = "FVG_CREATED"
    RETEST_CONFIRMED = "RETEST_CONFIRMED"
    ENTRY_READY = "ENTRY_READY"
    SIGNAL_PUBLISHED = "SIGNAL_PUBLISHED"
    INVALIDATED = "INVALIDATED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


STAGES = tuple(State)[:11]
TERMINAL = {State.INVALIDATED, State.EXPIRED, State.CANCELLED, State.SIGNAL_PUBLISHED}
GATES = frozenset({"data_quality", "lifecycle", "poi", "mtf", "chronology", "geometry", "risk", "duplicate", "freshness"})


@dataclass(frozen=True)
class Setup:
    symbol: str
    strategy: str
    direction: str
    timeframe: str
    context_ref: str
    poi_id: str
    poi_origin: Candle
    poi_eligible_at: int
    poi_low: float
    poi_high: float
    poi_qualified: bool
    invalidation_price: float
    created_at: int
    expires_at: int
    allow_same_candle_displacement: bool = False
    displacement_body_ratio: float = 1.3

    def __post_init__(self):
        if self.timeframe not in {"M1", "M5"} or self.direction not in {"LONG", "SHORT"}:
            raise ValueError("unsupported strategy direction/timeframe")
        expected = "ICT_FAST_SCALP_M1" if self.timeframe == "M1" else "ICT_STANDARD_M5"
        if self.strategy != expected or any(type(v) is not str or not v for v in (self.symbol,self.context_ref,self.poi_id)):
            raise ValueError("complete immutable setup identity required")
        if self.poi_origin.symbol != self.symbol:
            raise ValueError("POI symbol mismatch")
        if any(type(t) is not int for t in (self.created_at, self.expires_at, self.poi_eligible_at)):
            raise ValueError("integer timestamps required")
        if not self.poi_origin.closed_at <= self.poi_eligible_at <= self.created_at < self.expires_at:
            raise ValueError("invalid setup availability/expiry")
        if not all(type(v) in (int,float) and isfinite(v) and v > 0 for v in (self.poi_low, self.poi_high, self.invalidation_price)):
            raise ValueError("finite positive levels required")
        if self.poi_low >= self.poi_high or not isfinite(self.displacement_body_ratio) or self.displacement_body_ratio < 1:
            raise ValueError("invalid POI/volatility policy")
        if type(self.poi_qualified) is not bool or type(self.allow_same_candle_displacement) is not bool:
            raise ValueError("explicit boolean policies required")
        for key in ("poi_low","poi_high","invalidation_price","displacement_body_ratio"):
            object.__setattr__(self,key,float(getattr(self,key)))

    @property
    def setup_id(self):
        return digest(asdict(self))


def _decode_setup(value):
    data = json.loads(value)
    data["poi_origin"] = Candle(**data["poi_origin"])
    return Setup(**data)


def _candles(evidence):
    for field in fields(evidence):
        item = getattr(evidence, field.name)
        if isinstance(item, Candle):
            yield item
        elif isinstance(item, tuple):
            yield from (c for c in item if isinstance(c, Candle))


class LifecycleStore:
    SCHEMA_VERSION = 1

    def __init__(self, path):
        path = Path(path).resolve()
        # Never attach to legacy tables or a known production tree.
        if any(p.lower() == "nexus_deploy" for p in path.parts) or path.suffix.lower() not in {".db", ".sqlite", ".sqlite3"}:
            raise ValueError("isolated lifecycle database required")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if version == 0 and tables:
                raise ValueError("existing unversioned DB must not be adopted")
            if version > self.SCHEMA_VERSION:
                raise ValueError("unsupported future lifecycle schema")
            if version == 0:
                db.execute("CREATE TABLE v33_setups (setup_id TEXT PRIMARY KEY, spec TEXT NOT NULL)")
                db.execute("""CREATE TABLE v33_events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT UNIQUE NOT NULL,
                    setup_id TEXT NOT NULL REFERENCES v33_setups(setup_id),
                    event_key TEXT NOT NULL, state TEXT NOT NULL, at INTEGER NOT NULL,
                    snapshot_ref TEXT NOT NULL, payload TEXT NOT NULL,
                    UNIQUE(setup_id,event_key))""")
                db.execute("""CREATE TABLE v33_publications (
                    fingerprint TEXT PRIMARY KEY, setup_id TEXT UNIQUE NOT NULL
                    REFERENCES v33_setups(setup_id), snapshot_ref TEXT NOT NULL,
                    context_ref TEXT NOT NULL, gates TEXT NOT NULL, reserved_at INTEGER NOT NULL)""")
                db.execute("CREATE TABLE v33_migrations (version INTEGER PRIMARY KEY, description TEXT NOT NULL)")
                db.execute("INSERT INTO v33_migrations VALUES (1,'isolated append-only lifecycle')")
                for table in ("v33_setups", "v33_events", "v33_publications", "v33_migrations"):
                    for operation in ("UPDATE", "DELETE"):
                        db.execute(f"CREATE TRIGGER {table}_{operation.lower()} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT,'append only'); END")
                db.execute("PRAGMA user_version=1")
            required = {"v33_setups", "v33_events", "v33_publications", "v33_migrations"}
            actual = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not required <= actual:
                raise ValueError("incomplete lifecycle schema")
            triggers={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
            expected={f"{table}_{op}" for table in required for op in ("update","delete")}
            ledger=[r[0] for r in db.execute("SELECT version FROM v33_migrations ORDER BY version")]
            if not expected <= triggers or ledger != [self.SCHEMA_VERSION]:
                raise ValueError("lifecycle append-only schema/ledger damaged")

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def create(self, setup: Setup, *, snapshot_ref: str):
        if not snapshot_ref:
            raise ValueError("snapshot reference required")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            encoded = canonical(asdict(setup))
            old = db.execute("SELECT spec FROM v33_setups WHERE setup_id=?", (setup.setup_id,)).fetchone()
            if old:
                if old[0] != encoded:
                    raise ValueError("immutable setup collision")
                return setup.setup_id
            db.execute("INSERT INTO v33_setups VALUES (?,?)", (setup.setup_id, encoded))
            self._insert(db, setup.setup_id, "discovered", State.DISCOVERED, setup.created_at,
                         snapshot_ref, encode_evidence(Decision("setup_discovered")))
        return setup.setup_id

    @staticmethod
    def _insert(db, setup_id, key, state, at, snapshot_ref, payload):
        data = dict(setup_id=setup_id, event_key=key, state=state.value, at=at,
                    snapshot_ref=snapshot_ref, payload=payload)
        event_id = digest(data)
        db.execute("INSERT INTO v33_events(event_id,setup_id,event_key,state,at,snapshot_ref,payload) VALUES (?,?,?,?,?,?,?)",
                   (event_id, setup_id, key, state.value, at, snapshot_ref, canonical(payload)))
        return event_id

    def recover(self, setup_id):
        with self._connect() as db:
            row = db.execute("SELECT spec FROM v33_setups WHERE setup_id=?", (setup_id,)).fetchone()
            if row is None:
                raise KeyError(setup_id)
            events = tuple(dict(e) for e in db.execute("SELECT * FROM v33_events WHERE setup_id=? ORDER BY seq", (setup_id,)))
        return _decode_setup(row[0]), events

    def expire_due(self, *, at: int, snapshot_ref: str):
        """Advance due active identities using the supplied replay/runtime clock."""
        if type(at) is not int or not snapshot_ref:
            raise ValueError("explicit expiry clock/reference required")
        with self._connect() as db:
            ids = tuple(r[0] for r in db.execute("SELECT setup_id FROM v33_setups"))
        expired=[]
        for setup_id in ids:
            setup, history=self.recover(setup_id)
            if at>=setup.expires_at and State(history[-1]["state"]) not in TERMINAL:
                expired.append(self.advance(setup_id,State.EXPIRED,Decision("absolute_setup_deadline"),
                    event_key="absolute_expiry",at=at,snapshot_ref=snapshot_ref,feed_fresh=False))
        return tuple(expired)

    def advance(self, setup_id, state: State, evidence, *, event_key: str,
                at: int, snapshot_ref: str, feed_fresh: bool):
        state = State(state)
        if type(at) is not int or not event_key or not snapshot_ref:
            raise ValueError("event identity and decision time required")
        payload = encode_evidence(evidence)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT spec FROM v33_setups WHERE setup_id=?", (setup_id,)).fetchone()
            if row is None:
                raise KeyError(setup_id)
            setup = _decode_setup(row[0])
            previous = tuple(db.execute("SELECT * FROM v33_events WHERE setup_id=? ORDER BY seq", (setup_id,)))
            duplicate = next((e for e in previous if e["event_key"] == event_key), None)
            if duplicate:
                if (duplicate["state"], duplicate["at"], duplicate["snapshot_ref"], duplicate["payload"]) != (state.value, at, snapshot_ref, canonical(payload)):
                    raise ValueError("idempotency key reused with different content")
                return duplicate["event_id"]
            current = State(previous[-1]["state"])
            if current in TERMINAL or at < previous[-1]["at"]:
                raise ValueError("terminal setup or retroactive event")
            if at >= setup.expires_at and state != State.EXPIRED:
                raise ValueError("setup expired; record EXPIRED first")
            if state in {State.INVALIDATED, State.CANCELLED, State.EXPIRED}:
                if type(evidence) is not Decision or not evidence.reason:
                    raise ValueError("terminal reason required")
                if state == State.EXPIRED and at < setup.expires_at:
                    raise ValueError("expiry not reached")
            else:
                if feed_fresh is not True:
                    raise ValueError("stale or missing feed")
                if state == State.SIGNAL_PUBLISHED:
                    raise ValueError("publication requires independent reservation and receipt")
                if state != STAGES[STAGES.index(current) + 1]:
                    raise ValueError("mandatory stage skipped")
                self._validate(setup, state, evidence, at, previous)
            return self._insert(db, setup_id, event_key, state, at, snapshot_ref, payload)

    def monitor(self, setup_id, candle: Candle, *, at: int, snapshot_ref: str, feed_fresh: bool):
        """Persist closed-price invalidation/expiry even without a new setup stage.

        Normal monitoring grants no state promotion or publication permission.
        """
        if type(at) is not int or not snapshot_ref or type(candle) is not Candle:
            raise ValueError("explicit monitoring candle and decision required")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            spec=db.execute("SELECT spec FROM v33_setups WHERE setup_id=?",(setup_id,)).fetchone()
            if spec is None:
                raise KeyError(setup_id)
            setup=_decode_setup(spec[0])
            history=tuple(db.execute("SELECT * FROM v33_events WHERE setup_id=? ORDER BY seq",(setup_id,)))
            current=State(history[-1]["state"])
            if current in TERMINAL:
                return current
            if at<history[-1]["at"]:
                raise ValueError("retroactive monitoring decision")
            if at>=setup.expires_at:
                self._insert(db,setup_id,"absolute_expiry",State.EXPIRED,at,snapshot_ref,
                             encode_evidence(Decision("absolute_setup_deadline")))
                return State.EXPIRED
            if feed_fresh is not True:
                raise ValueError("stale or missing monitoring feed")
            if (candle.symbol!=setup.symbol or candle.timeframe!=setup.timeframe
                or candle.source!=setup.poi_origin.source or candle.closed_at>at
                or candle.closed_at<setup.created_at):
                raise ValueError("unverified monitoring candle")
            prior_bars=tuple(c for e in history for c in _candles(decode_evidence(json.loads(e["payload"]))))
            self._consistent_candles((*prior_bars,candle))
            if prior_bars and candle.opened_at<max(c.opened_at for c in prior_bars):
                raise ValueError("monitoring predates recorded evidence")
            invalid=(candle.close<=setup.invalidation_price if setup.direction=="LONG"
                     else candle.close>=setup.invalidation_price)
            if invalid:
                self._insert(db,setup_id,"price_invalidation:"+candle.identity,State.INVALIDATED,at,
                             snapshot_ref,encode_evidence(Observation(candle,"structural_close_invalidation")))
                return State.INVALIDATED
            return current

    @staticmethod
    def _consistent_candles(candles):
        seen={}
        for c in candles:
            key=(c.symbol,c.timeframe,c.source,c.opened_at)
            if key in seen and seen[key]!=c.identity:
                raise ValueError("source candle revised within setup evidence")
            seen[key]=c.identity

    @staticmethod
    def _validate(setup, state, evidence, at, history):
        bars = tuple(_candles(evidence))
        LifecycleStore._consistent_candles((
            *(c for e in history for c in _candles(decode_evidence(json.loads(e["payload"])))),
            *bars,
        ))
        for c in bars:
            if c.symbol != setup.symbol or c.timeframe != setup.timeframe or c.closed_at > at:
                raise ValueError("foreign or unclosed source candle")
            if c.source != setup.poi_origin.source:
                raise ValueError("mixed data provenance")
        by_state = {e["state"]: e for e in history}

        def bound(stage, event_id):
            event = by_state[stage.value]
            if event["event_id"] != event_id:
                raise ValueError("cross-setup evidence reference")
            return decode_evidence(json.loads(event["payload"]))

        long = setup.direction == "LONG"
        if state in {State.POI_SELECTED, State.APPROACHING_POI, State.POI_TOUCHED}:
            if type(evidence) is not Observation or not evidence.reason:
                raise ValueError("POI candle observation required")
            if evidence.candle.closed_at < setup.poi_eligible_at:
                raise ValueError("POI not yet eligible")
            if history[-1]["state"] != State.DISCOVERED.value:
                prior=decode_evidence(json.loads(history[-1]["payload"]))
                if evidence.candle.opened_at < prior.candle.opened_at:
                    raise ValueError("POI observation chronology")
            if state == State.POI_TOUCHED and (evidence.candle.low > setup.poi_high or evidence.candle.high < setup.poi_low):
                raise ValueError("POI not touched")
        elif state == State.LIQUIDITY_SWEPT:
            if type(evidence) is not Sweep:
                raise ValueError("sweep evidence required")
            c, ref = evidence.candle, evidence.liquidity
            touched = decode_evidence(json.loads(by_state[State.POI_TOUCHED.value]["payload"]))
            level = ref.low if long else ref.high
            if ref.closed_at > c.opened_at or c.opened_at < touched.candle.opened_at:
                raise ValueError("liquidity/touch chronology")
            if not c.low <= setup.poi_high or c.high < setup.poi_low:
                raise ValueError("sweep outside bound POI")
            if not (c.low < level < c.close if long else c.high > level > c.close):
                raise ValueError("sweep reclaim not established")
        elif state == State.MSS_CONFIRMED:
            if type(evidence) is not MSS:
                raise ValueError("MSS evidence required")
            sweep = bound(State.LIQUIDITY_SWEPT, evidence.sweep_event)
            c, swing, confirmation = evidence.candle, evidence.swing, evidence.swing_confirmation
            if c.opened_at < sweep.candle.closed_at or not swing.closed_at <= confirmation.closed_at <= sweep.candle.opened_at:
                raise ValueError("MSS/swing confirmation chronology")
            if not (c.close > swing.high if long else c.close < swing.low):
                raise ValueError("MSS close did not break referenced swing")
        elif state == State.DISPLACEMENT_CONFIRMED:
            if type(evidence) is not Displacement:
                raise ValueError("displacement evidence required")
            mss = bound(State.MSS_CONFIRMED, evidence.mss_event)
            c, base = evidence.candle, evidence.baseline
            same = c.identity == mss.candle.identity
            if not ((same and setup.allow_same_candle_displacement) or c.opened_at >= mss.candle.closed_at):
                raise ValueError("displacement chronology")
            if len(base) < 3 or any(b.closed_at > c.opened_at for b in base) or len({b.identity for b in base}) != len(base):
                raise ValueError("independent prior displacement baseline required")
            typical = sum(abs(b.close - b.open) for b in base) / len(base)
            if typical <= 0 or abs(c.close-c.open) < typical * setup.displacement_body_ratio or not (c.close > c.open if long else c.close < c.open):
                raise ValueError("directional displacement body threshold failed")
        elif state == State.FVG_CREATED:
            if type(evidence) is not FVG:
                raise ValueError("FVG evidence required")
            displacement = bound(State.DISPLACEMENT_CONFIRMED, evidence.displacement_event)
            l, m, r = evidence.left, evidence.middle, evidence.right
            if l.opened_at < displacement.candle.opened_at or l.closed_at != m.opened_at or m.closed_at != r.opened_at:
                raise ValueError("post-displacement three-candle chronology")
            if not (l.high < r.low if long else r.high < l.low):
                raise ValueError("directional FVG geometry failed")
        elif state == State.RETEST_CONFIRMED:
            if type(evidence) is not Retest:
                raise ValueError("retest evidence required")
            fvg = bound(State.FVG_CREATED, evidence.fvg_event)
            lo, hi = (fvg.left.high, fvg.right.low) if long else (fvg.right.high, fvg.left.low)
            if evidence.candle.opened_at < fvg.right.closed_at or evidence.candle.low > hi or evidence.candle.high < lo:
                raise ValueError("later retest of bound FVG required")
        elif state == State.ENTRY_READY:
            if type(evidence) is not Decision or not evidence.reason or setup.poi_qualified is not True:
                raise ValueError("provisional POI cannot establish entry readiness")
        # A closed invalidation cannot be ignored at any structural stage.
        event_bars = bars[:1] if type(evidence) not in {FVG} else bars
        if any((c.close <= setup.invalidation_price if long else c.close >= setup.invalidation_price)
               for c in event_bars if c.closed_at >= setup.created_at):
            raise ValueError("structural invalidation reached")

    def reserve_publication(self, setup_id, fingerprint, *, at, snapshot_ref, context_ref, gates):
        """Durable at-most-once reservation. Never sends; unresolved claims stay blocked."""
        if type(at) is not int or not fingerprint or not snapshot_ref or set(gates) != GATES or any(v is not True for v in gates.values()):
            raise ValueError("all independent gates must pass")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            spec = db.execute("SELECT spec FROM v33_setups WHERE setup_id=?", (setup_id,)).fetchone()
            if spec is None:
                raise KeyError(setup_id)
            setup = _decode_setup(spec[0])
            event = db.execute("SELECT * FROM v33_events WHERE setup_id=? ORDER BY seq DESC LIMIT 1", (setup_id,)).fetchone()
            if event["state"] != State.ENTRY_READY.value or not event["at"] <= at < setup.expires_at or context_ref != setup.context_ref or snapshot_ref != event["snapshot_ref"]:
                raise ValueError("candidate identity/context/freshness mismatch")
            if db.execute("SELECT 1 FROM v33_publications WHERE fingerprint=? OR setup_id=?", (fingerprint, setup_id)).fetchone():
                return False
            if at - event["at"] > 30:
                raise ValueError("entry snapshot is stale")
            db.execute("INSERT INTO v33_publications VALUES (?,?,?,?,?,?)", (fingerprint, setup_id, snapshot_ref, context_ref, canonical(gates), at))
            return True

    def confirm_publication(self, setup_id, fingerprint, receipt, *, at):
        """Record an external SHADOW receipt; caller still owns transport authorization."""
        if not receipt or type(at) is not int:
            raise ValueError("receipt and timestamp required")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            claim = db.execute("SELECT * FROM v33_publications WHERE setup_id=? AND fingerprint=?", (setup_id, fingerprint)).fetchone()
            last = db.execute("SELECT * FROM v33_events WHERE setup_id=? ORDER BY seq DESC LIMIT 1", (setup_id,)).fetchone()
            payload=encode_evidence(Decision("SHADOW receipt: " + receipt))
            if claim is not None and last["state"] == State.SIGNAL_PUBLISHED.value:
                if last["at"]==at and last["payload"]==canonical(payload):
                    return last["event_id"]
                raise ValueError("publication receipt conflict")
            if claim is None or last["state"] != State.ENTRY_READY.value or at < claim["reserved_at"]:
                raise ValueError("publication reservation/state mismatch")
            return self._insert(db, setup_id, "publication_receipt", State.SIGNAL_PUBLISHED, at,
                                claim["snapshot_ref"], payload)
