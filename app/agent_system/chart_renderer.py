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
    im=Image.new("RGB",(W,H),(15,18,24)); d=ImageDraw.Draw(im, "RGB")
    title=_font(34); normal=_font(22); small=_font(18)
    d.text((left,25),f"NEXUS ICT • {snapshot.symbol} • {timeframe}",font=title,fill=(235,238,244))
    d.text((right-260,35),f"Bid {snapshot.bid or '-'}  Ask {snapshot.ask or '-'}",font=small,fill=(190,196,207))
    def y(v): return bottom-(v-pmin)/(pmax-pmin)*(bottom-top)
    for i in range(6):
        yy=top+i*(bottom-top)/5; price=pmax-i*(pmax-pmin)/5
        d.line((left,yy,right,yy),fill=(45,50,60),width=1); d.text((right+12,yy-10),f"{price:.2f}",font=small,fill=(160,166,178))
    zone_styles = {
        "QUADRANT": ((170, 135, 255), (70, 55, 105)),
        "FVG BULLISH": ((70, 205, 150), (28, 82, 62)),
        "FVG BEARISH": ((235, 95, 110), (92, 38, 46)),
        "OB BULLISH": ((70, 150, 235), (28, 60, 92)),
        "OB BEARISH": ((240, 155, 65), (95, 62, 26)),
    }
    level_styles = {"Q25": (145, 125, 210), "Q50": (190, 155, 245), "Q75": (220, 180, 255)}
    for label,lo,hi,extra in zones:
        if hi<pmin or lo>pmax: continue
        y1,y2=y(hi),y(lo)
        if label in level_styles:
            col=level_styles[label]
            d.line((left,y1,right,y1),fill=col,width=2)
            d.text((right+12,y1-10),f"{label} {lo:.2f}",font=small,fill=col)
            continue
        outline,fill=zone_styles.get(label,((125,130,145),(50,54,64)))
        top_y,bottom_y=min(y1,y2),max(y1,y2)
        if bottom_y-top_y<5: bottom_y=top_y+5
        d.rectangle((left,top_y,right,bottom_y),fill=fill,outline=outline,width=2)
        tag=f"{label}  {lo:.2f}-{hi:.2f}"
        tw=d.textbbox((0,0),tag,font=small)[2]
        d.rectangle((left+8,top_y+5,left+20+tw,top_y+32),fill=(15,18,24))
        d.text((left+14,top_y+7),tag,font=small,fill=outline)
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
