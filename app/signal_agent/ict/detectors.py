from __future__ import annotations
from dataclasses import replace
from statistics import median
from .models import ICTEvent, EventStatus
from ..market_data.models import Candle

def _e(c,t,d,lo=None,hi=None,ref=None,parent=None,meta=None,status=EventStatus.ACTIVE):
    return ICTEvent(c.symbol,c.timeframe,t,d,c.open_time,c.open_time,lo,hi,ref,status,parent,meta or {})

def swings(cs,wing=2):
    out=[]
    for i in range(wing,len(cs)-wing):
        c=cs[i]; near=cs[i-wing:i]+cs[i+1:i+1+wing]
        if all(c.high>x.high for x in near): out.append(_e(c,"SWING_HIGH","BEARISH",ref=c.high,meta={"wing":wing}))
        if all(c.low<x.low for x in near): out.append(_e(c,"SWING_LOW","BULLISH",ref=c.low,meta={"wing":wing}))
    return out

def liquidity(cs,sw):
    return [ICTEvent(e.symbol,e.timeframe,"LIQUIDITY_POOL","BUY_SIDE" if e.event_type=="SWING_HIGH" else "SELL_SIDE",e.source_time,e.detected_at,reference_price=e.reference_price,parent_key=e.event_key,metadata={"source":e.event_type}) for e in sw]

def sweeps(cs,liq):
    out=[]
    for l in liq:
        for c in cs:
            if c.open_time<=l.source_time: continue
            p=l.reference_price
            if l.direction=="BUY_SIDE" and c.high>p and c.close<p: out.append(_e(c,"LIQUIDITY_SWEEP","BEARISH",ref=p,parent=l.event_key)); break
            if l.direction=="SELL_SIDE" and c.low<p and c.close>p: out.append(_e(c,"LIQUIDITY_SWEEP","BULLISH",ref=p,parent=l.event_key)); break
    return out

def displacement(cs,lookback=10,factor=1.5):
    out=[]
    for i,c in enumerate(cs):
        prior=[abs(x.close-x.open) for x in cs[max(0,i-lookback):i]]
        if len(prior)>=3:
            base=median(prior)
            if base>0 and abs(c.close-c.open)>=base*factor:
                out.append(_e(c,"DISPLACEMENT","BULLISH" if c.close>c.open else "BEARISH",c.low,c.high,meta={"body":abs(c.close-c.open),"baseline":base,"factor":factor}))
    return out

def fvgs(cs):
    out=[]
    for i,(a,b,c) in enumerate(zip(cs,cs[1:],cs[2:])):
        event=None
        if c.low>a.high:event=_e(c,"FVG","BULLISH",a.high,c.low,meta={"middle":b.open_time.isoformat()})
        elif c.high<a.low:event=_e(c,"FVG","BEARISH",c.high,a.low,meta={"middle":b.open_time.isoformat()})
        if event:
            status=EventStatus.ACTIVE; meta=dict(event.metadata)
            for x in cs[i+3:]:
                touched=x.low<=event.price_high and x.high>=event.price_low
                invalid=(event.direction=="BULLISH" and x.close<event.price_low) or (event.direction=="BEARISH" and x.close>event.price_high)
                if invalid: status=EventStatus.INVALIDATED; meta["lifecycle_time"]=x.open_time.isoformat(); break
                if touched: status=EventStatus.MITIGATED; meta["lifecycle_time"]=x.open_time.isoformat(); break
            out.append(replace(event,status=status,metadata=meta))
    return out

def structure_changes(cs,sw):
    raw=[]; highs=[e for e in sw if e.event_type=="SWING_HIGH"]; lows=[e for e in sw if e.event_type=="SWING_LOW"]
    last_break={"BULLISH":None,"BEARISH":None}
    for c in cs:
        ph=[x for x in highs if x.source_time<c.open_time]; pl=[x for x in lows if x.source_time<c.open_time]
        if ph and c.close>ph[-1].reference_price and last_break["BULLISH"]!=ph[-1].event_key:
            raw.append(_e(c,"MSS","BULLISH",ref=ph[-1].reference_price,parent=ph[-1].event_key)); last_break["BULLISH"]=ph[-1].event_key
        if pl and c.close<pl[-1].reference_price and last_break["BEARISH"]!=pl[-1].event_key:
            raw.append(_e(c,"MSS","BEARISH",ref=pl[-1].reference_price,parent=pl[-1].event_key)); last_break["BEARISH"]=pl[-1].event_key
    out=list(raw); last=None
    for x in sorted(raw,key=lambda e:e.source_time):
        if last and x.direction!=last.direction:
            out.append(ICTEvent(x.symbol,x.timeframe,"CHOCH",x.direction,x.source_time,x.detected_at,reference_price=x.reference_price,parent_key=x.event_key))
        last=x
    return out

def order_blocks(cs,disp):
    out=[]
    for d in disp:
        i=next((i for i,x in enumerate(cs) if x.open_time==d.source_time),None)
        if i is None: continue
        for x in reversed(cs[max(0,i-3):i]):
            if (d.direction=="BULLISH" and x.close<x.open) or (d.direction=="BEARISH" and x.close>x.open):
                status=EventStatus.ACTIVE; meta={}
                for later in cs[i+1:]:
                    invalid=(d.direction=="BULLISH" and later.close<x.low) or (d.direction=="BEARISH" and later.close>x.high)
                    if invalid:status=EventStatus.INVALIDATED;meta["invalidated_at"]=later.open_time.isoformat();break
                out.append(_e(x,"ORDER_BLOCK",d.direction,x.low,x.high,parent=d.event_key,status=status,meta=meta)); break
    return out

def breakers(cs,obs):
    out=[]
    for ob in obs:
        if ob.status!=EventStatus.INVALIDATED:continue
        t=ob.metadata.get("invalidated_at")
        c=next((x for x in cs if x.open_time.isoformat()==t),None)
        if c:out.append(_e(c,"BREAKER","BEARISH" if ob.direction=="BULLISH" else "BULLISH",ob.price_low,ob.price_high,parent=ob.event_key))
    return out

def premium_discount(cs):
    if not cs:return []
    hi=max(x.high for x in cs); lo=min(x.low for x in cs); mid=(hi+lo)/2;c=cs[-1]
    zone="PREMIUM" if c.close>mid else "DISCOUNT" if c.close<mid else "EQUILIBRIUM"
    return [_e(c,"PREMIUM_DISCOUNT",zone,lo,hi,mid,meta={"range_high":hi,"range_low":lo})]

def daily_quadrant(cs):
    xs=cs[-10:]
    if not xs:return []
    def wick(c):return max(c.high-max(c.open,c.close),min(c.open,c.close)-c.low)
    c=max(enumerate(xs),key=lambda z:(wick(z[1]),z[0]))[1]
    up=c.high-max(c.open,c.close);down=min(c.open,c.close)-c.low
    start,end,direction=(max(c.open,c.close),c.high,"UPPER") if up>=down else (min(c.open,c.close),c.low,"LOWER")
    span=end-start;levels={"25":start+span*.25,"50":start+span*.5,"75":start+span*.75}
    return [_e(c,"DAILY_QUADRANT",direction,min(start,end),max(start,end),levels["50"],meta={"levels":levels,"lookback":10})]
