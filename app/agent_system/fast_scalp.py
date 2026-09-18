from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .contracts import Direction, MarketSnapshot
from .quadrant import derive_daily_quadrant


class FastScalpState(str, Enum):
    SEARCHING = "SEARCHING"
    APPROACHING_POI = "APPROACHING_POI"
    IN_POI = "IN_POI"
    LIQUIDITY_SWEPT = "LIQUIDITY_SWEPT"
    MSS_CONFIRMED = "MSS_CONFIRMED"
    RETEST = "RETEST"
    ENTRY_READY = "ENTRY_READY"
    INVALIDATED = "INVALIDATED"


@dataclass(frozen=True)
class FastScalpAssessment:
    strategy_id: str
    symbol: str
    snapshot_id: str
    state: FastScalpState
    direction: Direction
    poi: tuple[float, float] | None
    sweep_anchor: float | None
    entry_zone: tuple[float, float] | None
    evidence: tuple[str, ...]
    blocks: tuple[str, ...]


def _rows(snapshot: MarketSnapshot, tf: str):
    return snapshot.timeframes.get(tf, ())


def _latest_fvgs(rows, lookback=100):
    out=[]
    for i in range(max(0,len(rows)-lookback),len(rows)-2):
        left,right=rows[i],rows[i+2]
        if float(left["high"]) < float(right["low"]):
            out.append((Direction.LONG,float(left["high"]),float(right["low"]),i))
        if float(left["low"]) > float(right["high"]):
            out.append((Direction.SHORT,float(right["high"]),float(left["low"]),i))
    return out


def _h1_bias(rows):
    if len(rows)<24: return Direction.NEUTRAL
    recent=rows[-24:]
    mid=(max(float(x["high"]) for x in recent)+min(float(x["low"]) for x in recent))/2
    close=float(rows[-1]["close"])
    ref=float(rows[-6]["close"])
    if close>mid and close>=ref: return Direction.LONG
    if close<mid and close<=ref: return Direction.SHORT
    return Direction.NEUTRAL


def _m1_sequence(rows, direction, sweep_window=6):
    if len(rows)<25: return None,None,None,()
    last=rows[-1]
    start=max(12,len(rows)-1-sweep_window)
    sweep_idx=None; anchor=None; ev=[]
    for i in range(start,len(rows)-1):
        prior=rows[i-12:i]
        if len(prior)<12: continue
        c=rows[i]
        if direction==Direction.LONG:
            level=min(float(x["low"]) for x in prior)
            if float(c["low"])<level and float(c["close"])>level:
                sweep_idx=i; anchor=float(c["low"])
        else:
            level=max(float(x["high"]) for x in prior)
            if float(c["high"])>level and float(c["close"])<level:
                sweep_idx=i; anchor=float(c["high"])
    if sweep_idx is None: return None,None,None,()
    ev.append("M1 liquidity sweep/reclaim confirmed")
    post=rows[sweep_idx+1:]
    if not post: return sweep_idx,anchor,None,tuple(ev)
    mss_idx=None
    for j in range(sweep_idx+1,len(rows)):
        prior=rows[max(sweep_idx,j-6):j]
        if not prior: continue
        close=float(rows[j]["close"])
        if direction==Direction.LONG and close>max(float(x["high"]) for x in prior):
            mss_idx=j; break
        if direction==Direction.SHORT and close<min(float(x["low"]) for x in prior):
            mss_idx=j; break
    if mss_idx is None: return sweep_idx,anchor,None,tuple(ev)
    ev.append("M1 displacement/MSS confirmed")
    return sweep_idx,anchor,mss_idx,tuple(ev)


def assess_fast_scalp(snapshot: MarketSnapshot) -> FastScalpAssessment:
    blocks=[]; ev=[]
    for tf,minimum in (("D1",10),("H1",20),("M15",20),("M5",20),("M1",25)):
        if len(_rows(snapshot,tf))<minimum: blocks.append(f"candles:{tf}")
    if snapshot.data_freshness_ms>30000: blocks.append("stale_market_data")
    if snapshot.bid is None or snapshot.ask is None: blocks.append("quote")
    if blocks:
        return FastScalpAssessment("ICT_FAST_SCALP_M1",snapshot.symbol,snapshot.snapshot_id,FastScalpState.SEARCHING,Direction.NEUTRAL,None,None,None,(),tuple(blocks))

    h1,m15,m5,m1=(_rows(snapshot,x) for x in ("H1","M15","M5","M1"))
    price=(float(snapshot.bid)+float(snapshot.ask))/2
    bias=_h1_bias(h1); ev.append(f"1H bias {bias.value}")
    if bias==Direction.NEUTRAL:
        return FastScalpAssessment("ICT_FAST_SCALP_M1",snapshot.symbol,snapshot.snapshot_id,FastScalpState.SEARCHING,bias,None,None,None,tuple(ev),("neutral_h1_bias",))

    # HTF location: most recent directional M15 FVG aligned with H1. Daily
    # Quadrant is an additional high-priority POI when current price is inside it.
    aligned=[x for x in _latest_fvgs(m15) if x[0]==bias]
    poi=(aligned[-1][1],aligned[-1][2]) if aligned else None
    q=derive_daily_quadrant(_rows(snapshot,"D1"))
    in_q=bool(q and q.contains(price))
    if in_q:
        ev.append("price inside Daily Quadrant")
    if poi:
        ev.append(f"M15 aligned FVG {poi[0]:g}-{poi[1]:g}")
    if poi is None and not in_q:
        return FastScalpAssessment("ICT_FAST_SCALP_M1",snapshot.symbol,snapshot.snapshot_id,FastScalpState.SEARCHING,bias,None,None,None,tuple(ev),("no_valid_htf_poi",))

    in_poi=in_q or (poi is not None and poi[0]<=price<=poi[1])
    if not in_poi:
        # Watch before touch: distance <= one recent M5 average range.
        ranges=[float(x["high"])-float(x["low"]) for x in m5[-20:]]
        avg=sum(ranges)/len(ranges) if ranges else 0
        distance=min(abs(price-poi[0]),abs(price-poi[1])) if poi else 10**9
        state=FastScalpState.APPROACHING_POI if avg>0 and distance<=avg else FastScalpState.SEARCHING
        return FastScalpAssessment("ICT_FAST_SCALP_M1",snapshot.symbol,snapshot.snapshot_id,state,bias,poi,None,None,tuple(ev),("waiting_for_poi_touch",))

    ev.append("HTF POI active; M1 trigger armed")
    sweep_idx,anchor,mss_idx,seq_ev=_m1_sequence(m1,bias)
    ev.extend(seq_ev)
    if sweep_idx is None:
        return FastScalpAssessment("ICT_FAST_SCALP_M1",snapshot.symbol,snapshot.snapshot_id,FastScalpState.IN_POI,bias,poi,None,None,tuple(ev),("waiting_m1_liquidity_sweep",))
    if mss_idx is None:
        return FastScalpAssessment("ICT_FAST_SCALP_M1",snapshot.symbol,snapshot.snapshot_id,FastScalpState.LIQUIDITY_SWEPT,bias,poi,anchor,None,tuple(ev),("waiting_m1_mss",))

    # Retest uses a directional M1 FVG created at/after the MSS. Never fabricate
    # an entry zone; if no real gap exists, stay confirmed but not entry-ready.
    fvgs=[x for x in _latest_fvgs(m1,40) if x[0]==bias and x[3]>=max(0,mss_idx-2)]
    entry_zone=(fvgs[-1][1],fvgs[-1][2]) if fvgs else None
    if entry_zone is None:
        return FastScalpAssessment("ICT_FAST_SCALP_M1",snapshot.symbol,snapshot.snapshot_id,FastScalpState.MSS_CONFIRMED,bias,poi,anchor,None,tuple(ev),("waiting_m1_fvg",))
    ev.append(f"M1 directional FVG {entry_zone[0]:g}-{entry_zone[1]:g}")
    if entry_zone[0]<=price<=entry_zone[1]:
        ev.append("M1 FVG retest active")
        return FastScalpAssessment("ICT_FAST_SCALP_M1",snapshot.symbol,snapshot.snapshot_id,FastScalpState.ENTRY_READY,bias,poi,anchor,entry_zone,tuple(ev),())
    return FastScalpAssessment("ICT_FAST_SCALP_M1",snapshot.symbol,snapshot.snapshot_id,FastScalpState.RETEST,bias,poi,anchor,entry_zone,tuple(ev),("waiting_m1_fvg_retest",))
