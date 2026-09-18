from __future__ import annotations

import io
import re
from typing import Mapping

from PIL import Image, ImageDraw, ImageFont

from .contracts import MarketSnapshot


def _font(size: int):
    for name in ("arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def _zones(evidence):
    out=[]
    for raw in evidence:
        s=str(raw)
        m=re.search(r"Daily Quadrant (\w+) ([\d.]+)-([\d.]+); 25=([\d.]+), 50=([\d.]+), 75=([\d.]+)",s)
        if m:
            side,lo,hi,p25,p50,p75=m.groups()
            out.append(("QUADRANT",float(lo),float(hi),side))
            for label,v in (("Q25",p25),("Q50",p50),("Q75",p75)): out.append((label,float(v),float(v),""))
            continue
        m=re.search(r"15M (bullish|bearish) (FVG|OB) ([\d.]+)-([\d.]+)",s)
        if m:
            direction,kind,lo,hi=m.groups(); out.append((f"{kind} {direction.upper()}",float(lo),float(hi),""))
    return out


def render_ict_chart(snapshot: MarketSnapshot, assessment: Mapping[str,object], *, timeframe: str="M15", candle_count: int=80) -> bytes:
    rows=list(snapshot.timeframes.get(timeframe, ()))[-candle_count:]
    if len(rows)<20: raise ValueError(f"not enough {timeframe} candles for chart")
    evidence=list(assessment.get("evidence") or [])
    zones=_zones(evidence)
    highs=[float(x["high"]) for x in rows]; lows=[float(x["low"]) for x in rows]
    zvals=[v for _,lo,hi,_ in zones for v in (lo,hi)]
    visible_z=[v for v in zvals if min(lows)*0.97 <= v <= max(highs)*1.03]
    pmin=min(lows+visible_z); pmax=max(highs+visible_z); pad=max((pmax-pmin)*0.08,0.01); pmin-=pad; pmax+=pad
    W,H=1400,850; left,right,top,bottom=80,1250,85,760
    im=Image.new("RGB",(W,H),(15,18,24)); d=ImageDraw.Draw(im)
    title=_font(34); normal=_font(22); small=_font(18)
    d.text((left,25),f"NEXUS ICT • {snapshot.symbol} • {timeframe}",font=title,fill=(235,238,244))
    d.text((right-260,35),f"Bid {snapshot.bid or '-'}  Ask {snapshot.ask or '-'}",font=small,fill=(190,196,207))
    def y(v): return bottom-(v-pmin)/(pmax-pmin)*(bottom-top)
    for i in range(6):
        yy=top+i*(bottom-top)/5; price=pmax-i*(pmax-pmin)/5
        d.line((left,yy,right,yy),fill=(45,50,60),width=1); d.text((right+12,yy-10),f"{price:.2f}",font=small,fill=(160,166,178))
    for label,lo,hi,extra in zones:
        if hi<pmin or lo>pmax: continue
        y1,y2=y(hi),y(lo)
        if abs(y2-y1)<2:
            d.line((left,y1,right,y1),fill=(115,120,135),width=2)
        else:
            d.rectangle((left,y1,right,y2),outline=(100,108,125),width=2)
        d.text((left+8,min(y1,y2)+3),f"{label} {lo:g}" + (f"-{hi:g}" if hi!=lo else ""),font=small,fill=(215,220,230))
    step=(right-left)/len(rows); body=max(3,int(step*0.55))
    for i,r in enumerate(rows):
        x=left+(i+0.5)*step; o,c,h,l=map(float,(r["open"],r["close"],r["high"],r["low"]))
        up=c>=o; col=(105,190,150) if up else (215,105,115)
        d.line((x,y(h),x,y(l)),fill=col,width=2)
        d.rectangle((x-body/2,min(y(o),y(c)),x+body/2,max(y(o),y(c))+1),fill=col)
    if snapshot.bid and snapshot.ask:
        mid=(snapshot.bid+snapshot.ask)/2
        if pmin<=mid<=pmax:
            yy=y(mid); d.line((left,yy,right,yy),fill=(235,200,90),width=2); d.text((right+12,yy-10),f"NOW {mid:.2f}",font=small,fill=(235,200,90))
    d.text((left,H-55),"Source: NEXUS MT5 Market Feed • zones derived from the same ICT snapshot",font=small,fill=(145,150,162))
    buf=io.BytesIO(); im.save(buf,format="PNG",optimize=True); return buf.getvalue()
