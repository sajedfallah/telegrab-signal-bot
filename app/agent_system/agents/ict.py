from __future__ import annotations

from datetime import timezone

from ..contracts import AgentAssessment, Direction, MarketSnapshot
from ..quadrant import derive_daily_quadrant


def _rows(snapshot: MarketSnapshot, tf: str) -> tuple[dict, ...]: return snapshot.timeframes.get(tf, ())

def _pivots(rows, width=2):
    highs=[]; lows=[]
    for i in range(width,len(rows)-width):
        w=rows[i-width:i+width+1]; h=float(rows[i]["high"]); l=float(rows[i]["low"])
        if h==max(float(x["high"]) for x in w): highs.append(h)
        if l==min(float(x["low"]) for x in w): lows.append(l)
    return highs,lows

def _h1_bias(rows):
    highs,lows=_pivots(rows[-80:])
    if len(highs)>=2 and len(lows)>=2:
        if highs[-1]>highs[-2] and lows[-1]>lows[-2]: return Direction.LONG,"1H structure HH/HL"
        if highs[-1]<highs[-2] and lows[-1]<lows[-2]: return Direction.SHORT,"1H structure LH/LL"
    recent=rows[-24:]; midpoint=(max(float(x["high"]) for x in recent)+min(float(x["low"]) for x in recent))/2; close=float(rows[-1]["close"])
    if close>midpoint and close>=float(rows[-6]["close"]): return Direction.LONG,"1H structure has bullish tendency"
    if close<midpoint and close<=float(rows[-6]["close"]): return Direction.SHORT,"1H structure has bearish tendency"
    return Direction.NEUTRAL,"1H structure is neutral/ranging"

def _latest_fvg(rows):
    bull=bear=None
    for i in range(max(0,len(rows)-100),len(rows)-2):
        left,right=rows[i],rows[i+2]
        if float(left["high"])<float(right["low"]): bull=(float(left["high"]),float(right["low"]))
        if float(left["low"])>float(right["high"]): bear=(float(right["high"]),float(left["low"]))
    return bull,bear

def _latest_ob(rows):
    recent=rows[-60:]; ranges=[float(x["high"])-float(x["low"]) for x in recent[:-1]]; avg=sum(ranges)/len(ranges) if ranges else 0; bull=bear=None
    for i in range(1,len(recent)):
        cur,prev=recent[i],recent[i-1]; displacement=avg>0 and float(cur["high"])-float(cur["low"])>=avg*1.35
        if displacement and float(cur["close"])>float(cur["open"]) and float(prev["close"])<float(prev["open"]): bull=(float(prev["low"]),float(prev["high"]))
        if displacement and float(cur["close"])<float(cur["open"]) and float(prev["close"])>float(prev["open"]): bear=(float(prev["low"]),float(prev["high"]))
    return bull,bear

def _m5_trigger(rows, sweep_window=4):
    """Confirm a recent liquidity sweep with a later 5M MSS.

    A valid sweep may precede the MSS by several closed 5M candles. The sweep
    must still be inside the bounded confirmation window; older sweeps expire.
    """
    if len(rows) < 20:
        return Direction.NEUTRAL, ()

    last = rows[-1]
    bm = float(last["close"]) > max(float(x["high"]) for x in rows[-7:-1])
    sm = float(last["close"]) < min(float(x["low"]) for x in rows[-7:-1])

    start = max(12, len(rows) - 1 - sweep_window)
    sell_side = None
    buy_side = None
    for i in range(start, len(rows) - 1):
        prior = rows[max(0, i - 12):i]
        if len(prior) < 12:
            continue
        ph = max(float(x["high"]) for x in prior)
        pl = min(float(x["low"]) for x in prior)
        candle = rows[i]
        if float(candle["low"]) < pl and float(candle["close"]) > pl:
            sell_side = i
        if float(candle["high"]) > ph and float(candle["close"]) < ph:
            buy_side = i

    ev = []
    if sell_side is not None:
        ev.append(f"5M sell-side liquidity sweep/reclaim ({len(rows)-1-sell_side} bars before MSS check)")
    if buy_side is not None:
        ev.append(f"5M buy-side liquidity sweep/reclaim ({len(rows)-1-buy_side} bars before MSS check)")
    if bm:
        ev.append("5M bullish displacement/MSS")
    if sm:
        ev.append("5M bearish displacement/MSS")
    if sell_side is not None and bm:
        return Direction.LONG, tuple(ev)
    if buy_side is not None and sm:
        return Direction.SHORT, tuple(ev)
    return Direction.NEUTRAL, tuple(ev)

def assess_ict(snapshot: MarketSnapshot) -> AgentAssessment:
    missing=list(snapshot.missing_data); d1,h1,m15,m5=(_rows(snapshot,tf) for tf in ("D1","H1","M15","M5"))
    for tf,rows,minimum in (("D1",d1,10),("H1",h1,20),("M15",m15,20),("M5",m5,20)):
        if len(rows)<minimum: missing.append(f"candles:{tf}")
    if snapshot.data_freshness_ms>30000: missing.append("stale_market_data")
    if missing:
        return AgentAssessment(agent_id="nexus-ict-v1",symbol=snapshot.symbol,snapshot_id=snapshot.snapshot_id,direction=Direction.NEUTRAL,confidence=None,evidence=("ICT assessment failed closed because required market inputs are incomplete",),invalidations=("fresh D1/H1/M15/M5 snapshot required",),missing_data=tuple(dict.fromkeys(missing)),created_at=snapshot.as_of.astimezone(timezone.utc))
    bias,bias_note=_h1_bias(h1); bull_fvg,bear_fvg=_latest_fvg(m15); bull_ob,bear_ob=_latest_ob(m15); trigger,trigger_ev=_m5_trigger(m5); evidence=[bias_note]; invalid=[]
    q=derive_daily_quadrant(d1)
    price=(float(snapshot.bid)+float(snapshot.ask))/2 if snapshot.bid and snapshot.ask else float(snapshot.last or 0)
    if q:
        evidence.append(f"Daily Quadrant {q.wick_side} {q.low:g}-{q.high:g}; 25={q.level_25:g}, 50={q.level_50:g}, 75={q.level_75:g}")
        if q.contains(price): evidence.append("Price is inside Daily Quadrant HTF reaction zone; lower-timeframe confirmation remains mandatory")
    if bull_fvg: evidence.append(f"15M bullish FVG {bull_fvg[0]:g}-{bull_fvg[1]:g}")
    if bear_fvg: evidence.append(f"15M bearish FVG {bear_fvg[0]:g}-{bear_fvg[1]:g}")
    if bull_ob: evidence.append(f"15M bullish OB {bull_ob[0]:g}-{bull_ob[1]:g}")
    if bear_ob: evidence.append(f"15M bearish OB {bear_ob[0]:g}-{bear_ob[1]:g}")
    evidence.extend(trigger_ev); direction=Direction.NEUTRAL
    if bias==Direction.LONG and trigger==Direction.LONG: direction=Direction.LONG; invalid.append("invalidate if 5M bullish structure fails after trigger")
    elif bias==Direction.SHORT and trigger==Direction.SHORT: direction=Direction.SHORT; invalid.append("invalidate if 5M bearish structure fails after trigger")
    elif trigger!=Direction.NEUTRAL and trigger!=bias: evidence.append("5M trigger conflicts with 1H bias; wait"); invalid.append("HTF/LTF alignment required")
    else: invalid.append("valid 5M liquidity sweep + MSS confirmation required")
    return AgentAssessment(agent_id="nexus-ict-v1",symbol=snapshot.symbol,snapshot_id=snapshot.snapshot_id,direction=direction,confidence=None,evidence=tuple(evidence),invalidations=tuple(invalid),missing_data=(),created_at=snapshot.as_of.astimezone(timezone.utc))
