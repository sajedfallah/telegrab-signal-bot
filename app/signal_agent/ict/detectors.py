from __future__ import annotations
from statistics import median
from .models import ICTEvent
from ..market_data.models import Candle

def _e(c,t,d,lo=None,hi=None,ref=None,parent=None,meta=None):
    return ICTEvent(c.symbol,c.timeframe,t,d,c.open_time,c.open_time,lo,hi,ref,parent_key=parent,metadata=meta or {})

def swings(cs:list[Candle],wing=2):
    out=[]
    for i in range(wing,len(cs)-wing):
        c=cs[i]; left=cs[i-wing:i]; right=cs[i+1:i+1+wing]
        if all(c.high>x.high for x in left+right): out.append(_e(c,"SWING_HIGH","BEARISH",ref=c.high,meta={"wing":wing}))
        if all(c.low<x.low for x in left+right): out.append(_e(c,"SWING_LOW","BULLISH",ref=c.low,meta={"wing":wing}))
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
        if len(prior)<3: continue
        base=median(prior)
        if base>0 and abs(c.close-c.open)>=base*factor:
            out.append(_e(c,"DISPLACEMENT","BULLISH" if c.close>c.open else "BEARISH",c.low,c.high,meta={"body":abs(c.close-c.open),"baseline":base,"factor":factor}))
    return out

def fvgs(cs):
    out=[]
    for a,b,c in zip(cs,cs[1:],cs[2:]):
        if c.low>a.high: out.append(_e(c,"FVG","BULLISH",a.high,c.low,meta={"middle":b.open_time.isoformat()}))
        if c.high<a.low: out.append(_e(c,"FVG","BEARISH",c.high,a.low,meta={"middle":b.open_time.isoformat()}))
    return out

def structure_changes(cs,sw):
    out=[]; highs=[e for e in sw if e.event_type=="SWING_HIGH"]; lows=[e for e in sw if e.event_type=="SWING_LOW"]
    for c in cs:
        ph=[x for x in highs if x.source_time<c.open_time]; pl=[x for x in lows if x.source_time<c.open_time]
        if ph and c.close>ph[-1].reference_price: out.append(_e(c,"MSS","BULLISH",ref=ph[-1].reference_price,parent=ph[-1].event_key))
        if pl and c.close<pl[-1].reference_price: out.append(_e(c,"MSS","BEARISH",ref=pl[-1].reference_price,parent=pl[-1].event_key))
    # CHOCH is an explicit first opposite MSS after the prior break direction.
    last=None
    for x in sorted(out,key=lambda e:e.source_time):
        if last and x.direction!=last.direction:
            out.append(ICTEvent(x.symbol,x.timeframe,"CHOCH",x.direction,x.source_time,x.detected_at,reference_price=x.reference_price,parent_key=x.event_key))
        last=x
    return out

def order_blocks(cs,disp):
    out=[]
    for d in disp:
        i=next((i for i,x in enumerate(cs) if x.open_time==d.source_time),None)
        if i is None: continue
        direction=d.direction
        for x in reversed(cs[max(0,i-3):i]):
            if (direction=="BULLISH" and x.close<x.open) or (direction=="BEARISH" and x.close>x.open):
                out.append(_e(x,"ORDER_BLOCK",direction,x.low,x.high,parent=d.event_key)); break
    return out

def breakers(cs,obs):
    out=[]
    for ob in obs:
        for c in cs:
            if c.open_time<=ob.source_time: continue
            broken=(ob.direction=="BULLISH" and c.close<(ob.price_low or 0)) or (ob.direction=="BEARISH" and c.close>(ob.price_high or 0))
            if broken: out.append(_e(c,"BREAKER","BEARISH" if ob.direction=="BULLISH" else "BULLISH",ob.price_low,ob.price_high,parent=ob.event_key)); break
    return out

def premium_discount(cs):
    if not cs:return []
    hi=max(x.high for x in cs); lo=min(x.low for x in cs); mid=(hi+lo)/2; c=cs[-1]
    zone="PREMIUM" if c.close>mid else "DISCOUNT" if c.close<mid else "EQUILIBRIUM"
    return [_e(c,"PREMIUM_DISCOUNT",zone,lo,hi,mid,meta={"range_high":hi,"range_low":lo})]

def daily_quadrant(cs):
    xs=cs[-10:]
    if not xs:return []
    def wick(c):
        upper=c.high-max(c.open,c.close); lower=min(c.open,c.close)-c.low
        return max(upper,lower)
    # newest wins ties
    c=max(enumerate(xs),key=lambda z:(wick(z[1]),z[0]))[1]
    upper=c.high-max(c.open,c.close); lower=min(c.open,c.close)-c.low
    if upper>=lower: start=max(c.open,c.close); end=c.high; direction="UPPER"
    else: start=min(c.open,c.close); end=c.low; direction="LOWER"
    span=end-start
    levels={"25":start+span*.25,"50":start+span*.5,"75":start+span*.75}
    return [_e(c,"DAILY_QUADRANT",direction,min(start,end),max(start,end),levels["50"],meta={"levels":levels,"lookback":10})]
