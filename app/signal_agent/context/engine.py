from __future__ import annotations
from datetime import datetime,timezone
from .models import ContextSnapshot
TFS=("D1","H4","H1","M15","M5")
class ContextEngine:
    def build(self,symbol,candles_by_tf,events,as_of=None):
        as_of=as_of or datetime.now(timezone.utc)
        closed={tf:self._closed(candles_by_tf.get(tf,[]),tf,as_of) for tf in TFS}
        events=[e for e in events if e.symbol.upper()==symbol.upper() and e.source_time<=as_of]
        latest={tf:(cs[-1] if cs else None) for tf,cs in closed.items()}
        anchor=next((latest[x] for x in ("M5","M15","H1","H4","D1") if latest[x]),None)
        if not anchor:return self._empty(symbol,as_of)
        price=anchor.close
        bias={tf:self._bias(tf,events) for tf in TFS}
        htf=self._htf(bias);alignment=self._alignment(bias,htf)
        dr=self._range(closed);loc=self._location(price,dr)
        q=self._quadrant(events);qrel=self._qrel(price,q)
        liq,sweeps=self._liquidity(price,events)
        pois=self._pois(price,events)
        session=self._session(closed.get("M5") or closed.get("M15") or [],events,as_of)
        state=self._state(bias,htf,alignment,events)
        reasons=self._reasons(htf,alignment,loc,qrel,sweeps,pois,session)
        keys=sorted({e.event_key for e in events})
        return ContextSnapshot(symbol.upper(),as_of,price,bias,htf,alignment,dr,loc,q,qrel,liq,sweeps,pois,session,state,reasons,keys)
    @staticmethod
    def _closed(cs,tf,as_of):
        sec={"M5":300,"M15":900,"H1":3600,"H4":14400,"D1":86400}[tf]
        return sorted([c for c in cs if c.open_time.timestamp()+sec<=as_of.timestamp()],key=lambda c:c.open_time)
    @staticmethod
    def _bias(tf,events):
        xs=[e for e in events if e.timeframe.upper()==tf and e.event_type in ("MSS","CHOCH")]
        if not xs:return "NEUTRAL"
        return sorted(xs,key=lambda e:e.source_time)[-1].direction
    @staticmethod
    def _htf(b):
        xs=[b[x] for x in ("D1","H4","H1") if b[x]!="NEUTRAL"]
        if not xs:return "NEUTRAL"
        if len(set(xs))==1:return xs[0]
        return "MIXED"
    @staticmethod
    def _alignment(b,htf):
        l=[b["M15"],b["M5"]];active=[x for x in l if x!="NEUTRAL"]
        if htf=="MIXED":return "HTF_CONFLICT"
        if htf=="NEUTRAL":return "UNRESOLVED"
        if not active:return "HTF_ONLY"
        return "ALIGNED" if all(x==htf for x in active) else "HTF_ALIGNED_LTF_COUNTERTREND"
    @staticmethod
    def _range(closed):
        cs=closed.get("H1") or closed.get("H4") or closed.get("D1") or []
        if not cs:return {}
        hi=max(c.high for c in cs[-20:]);lo=min(c.low for c in cs[-20:])
        return {"high":hi,"low":lo,"equilibrium":(hi+lo)/2,"timeframe":cs[-1].timeframe}
    @staticmethod
    def _location(price,r):
        if not r:return "UNKNOWN"
        return "PREMIUM" if price>r["equilibrium"] else "DISCOUNT" if price<r["equilibrium"] else "EQUILIBRIUM"
    @staticmethod
    def _quadrant(events):
        xs=[e for e in events if e.event_type=="DAILY_QUADRANT"]
        if not xs:return None
        e=sorted(xs,key=lambda x:x.source_time)[-1];lv=e.metadata.get("levels",{})
        return {"low":e.price_low,"high":e.price_high,"levels":lv,"priority_levels":["50","75"],"source_event_key":e.event_key}
    @staticmethod
    def _qrel(price,q):
        if not q:return "NONE"
        if price<q["low"] or price>q["high"]:return "OUTSIDE"
        lv=q["levels"];pairs=sorted((float(v),k) for k,v in lv.items())
        eps=max(1e-9,(q["high"]-q["low"])*1e-6)
        for v,k in pairs:
            if abs(price-v)<=eps:return "Q"+k
        if price<pairs[0][0]:return "INSIDE_BELOW_Q25"
        if price<pairs[1][0]:return "Q25_50"
        if price<pairs[2][0]:return "Q50_75"
        return "INSIDE_ABOVE_Q75"
    @staticmethod
    def _liquidity(price,events):
        pools=[e for e in events if e.event_type=="LIQUIDITY_POOL" and e.status.value=="ACTIVE" and e.reference_price is not None]
        buy=sorted([e for e in pools if e.direction=="BUY_SIDE" and e.reference_price>=price],key=lambda e:e.reference_price-price)
        sell=sorted([e for e in pools if e.direction=="SELL_SIDE" and e.reference_price<=price],key=lambda e:price-e.reference_price)
        def item(x):
            return None if not x else {"price":x.reference_price,"distance":abs(x.reference_price-price),"source_event_key":x.event_key}
        sw=sorted([e for e in events if e.event_type=="LIQUIDITY_SWEEP"],key=lambda e:e.source_time)[-10:]
        return {"nearest_buy_side":item(buy[0]) if buy else None,"nearest_sell_side":item(sell[0]) if sell else None},[{"direction":e.direction,"time":e.source_time.isoformat(),"source_event_key":e.event_key} for e in sw]
    @staticmethod
    def _pois(price,events):
        out=[]
        for e in events:
            if e.event_type not in ("FVG","ORDER_BLOCK","BREAKER") or e.status.value!="ACTIVE":continue
            lo=e.price_low;hi=e.price_high
            dist=0 if lo is not None and hi is not None and lo<=price<=hi else min(abs(price-x) for x in (lo,hi) if x is not None)
            out.append({"type":e.event_type,"direction":e.direction,"timeframe":e.timeframe,"low":lo,"high":hi,"distance":dist,"source_event_key":e.event_key})
        return sorted(out,key=lambda x:(x["distance"],x["type"],x["source_event_key"]))
    @staticmethod
    def _session(cs,events,as_of):
        active=[e for e in events if e.event_type=="SESSION_CONTEXT" and e.source_time<=as_of]
        name=sorted(active,key=lambda e:e.source_time)[-1].direction if active else "OFF_SESSION"
        day=[c for c in cs if c.open_time.date()==as_of.date()]
        return {"name":name,"open":day[0].open if day else None,"high":max((c.high for c in day),default=None),"low":min((c.low for c in day),default=None)}
    @staticmethod
    def _state(b,htf,alignment,events):
        if all(v=="NEUTRAL" for v in b.values()):return "INSUFFICIENT_DATA"
        if htf=="MIXED" or alignment=="HTF_CONFLICT":return "CONFLICTED"
        if alignment=="ALIGNED":return "TRENDING"
        if any(e.event_type=="CHOCH" for e in events):return "TRANSITION"
        return "RANGING"
    @staticmethod
    def _reasons(htf,alignment,loc,qrel,sweeps,pois,session):
        r=[f"HTF_{htf}",f"STRUCTURE_{alignment}",f"PRICE_{loc}",f"QUADRANT_{qrel}",f"SESSION_{session['name']}"]
        if sweeps:r.append("RECENT_LIQUIDITY_SWEEP")
        if pois:r.append("ACTIVE_POI_PRESENT")
        return sorted(set(r))
    @staticmethod
    def _empty(symbol,as_of):
        return ContextSnapshot(symbol.upper(),as_of,0.0,{x:"NEUTRAL" for x in TFS},"NEUTRAL","UNRESOLVED",{},"UNKNOWN",None,"NONE",{"nearest_buy_side":None,"nearest_sell_side":None},[],[],{"name":"OFF_SESSION","open":None,"high":None,"low":None},"INSUFFICIENT_DATA",["INSUFFICIENT_DATA"],[])
