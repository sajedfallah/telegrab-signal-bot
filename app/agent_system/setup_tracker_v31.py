"""Non-executing closed-candle ICT setup tracker.

Tracks an ordered sweep -> MSS/displacement -> newly formed FVG -> retest.
Reports a single setup identity and observed stage. It cannot authorize orders
or replace the strict signal publication gate.
"""
from __future__ import annotations

from hashlib import sha256
from typing import Any

from .contracts import Direction, MarketSnapshot
from .agents.ict import _h1_bias


def track_ict_setup(snapshot: MarketSnapshot, timeframe: str) -> dict[str, Any]:
    output: dict[str, Any] = dict(status="WAIT", setup_id=None, direction=None,
        sweep_time=None, mss_time=None, fvg_time=None, retest_time=None,
        fvg=None, blocks=[], confirmed_for_signal=False)
    if timeframe not in {"M1", "M5"}:
        output["blocks"]=["analysis_timeframe_not_execution_trigger"]
        return output
    if (snapshot.data_freshness_ms > 30000 or snapshot.missing_data
        or snapshot.bid is None or snapshot.ask is None or snapshot.ask < snapshot.bid):
        output["blocks"]=["market_data_not_verified"]
        return output
    rows=list(snapshot.timeframes.get(timeframe, ()))
    h1=list(snapshot.timeframes.get("H1", ()))
    if len(rows)<30 or len(h1)<24:
        output["blocks"]=["insufficient_candles"]
        return output
    direction,_=_h1_bias(h1)
    if direction not in {Direction.LONG,Direction.SHORT}:
        output["blocks"]=["neutral_h1_bias"]
        return output
    # Last candle may still be forming. All evidence below uses closed bars only.
    bars=rows[:-1]
    candidate=None
    for idx in range(max(12,len(bars)-20),len(bars)):
        prior=bars[idx-12:idx]
        bar=bars[idx]
        low,high,close=(float(bar[k]) for k in ("low","high","close"))
        if direction==Direction.LONG:
            level=min(float(b["low"]) for b in prior)
            valid=low<level<close
        else:
            level=max(float(b["high"]) for b in prior)
            valid=high>level>close
        if valid:
            candidate=idx
    if candidate is None:
        output["blocks"]=["waiting_for_directional_sweep"]
        return output
    raw=bars[candidate].get("time")
    if raw is None:
        output["blocks"]=["sweep_candle_time_missing"]
        return output
    setup_id=sha256(f"{snapshot.symbol}:{timeframe}:{direction.value}:{raw}".encode()).hexdigest()[:16]
    output.update(status="SWEEP_OBSERVED",setup_id=setup_id,direction=direction.value,
                  sweep_time=raw,blocks=["waiting_for_mss"])
    sweep=candidate
    for mss in range(sweep+1,len(bars)):
        prev=bars[max(sweep,mss-6):mss]
        if not prev: continue
        candle=bars[mss]
        close=float(candle["close"])
        broken=(close>max(float(x["high"]) for x in prev) if direction==Direction.LONG
                else close<min(float(x["low"]) for x in prev))
        if not broken: continue
        body=abs(float(candle["close"])-float(candle["open"]))
        previous_bodies=[abs(float(x["close"])-float(x["open"])) for x in bars[max(0,mss-12):mss]]
        typical=sum(previous_bodies)/len(previous_bodies) if previous_bodies else 0
        if typical<=0 or body<1.3*typical: continue
        output.update(status="MSS_OBSERVED",mss_time=candle.get("time"),blocks=["waiting_for_post_mss_fvg"])
        for i in range(max(0,mss-2),len(bars)-2):
            left,right=bars[i],bars[i+2]
            if direction==Direction.LONG:
                lo,hi=float(left["high"]),float(right["low"])
            else:
                lo,hi=float(right["high"]),float(left["low"])
            if lo>=hi or i+2<mss: continue
            output.update(status="FVG_OBSERVED",fvg_time=right.get("time"),
                          fvg=[lo,hi],blocks=["waiting_for_later_retest"])
            for retest in range(i+3,len(bars)):
                rb=bars[retest]
                if float(rb["low"])<=hi and float(rb["high"])>=lo:
                    output.update(status="RETEST_OBSERVED",retest_time=rb.get("time"),
                                  blocks=["poi_and_risk_reverification_required"])
                    return output
        return output
    return output
