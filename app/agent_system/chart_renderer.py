from __future__ import annotations

import io
import re
from typing import Mapping

from PIL import Image, ImageDraw, ImageFont

from .contracts import MarketSnapshot
from .quadrant import derive_daily_quadrant


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
            _tf,direction,kind,lo,hi=m.groups(); out.append((f"{kind} {direction.upper()}",float(lo),float(hi),""))
    return out


def render_ict_chart(snapshot: MarketSnapshot, assessment: Mapping[str,object], *, timeframe: str="M15", candle_count: int=180) -> bytes:
    rows=list(snapshot.timeframes.get(timeframe, ()))[-candle_count:]
    if len(rows)<20: raise ValueError(f"not enough {timeframe} candles for chart")
    evidence=list(assessment.get("evidence") or [])
    zones=_zones(evidence)
    highs=[float(x["high"]) for x in rows]; lows=[float(x["low"]) for x in rows]
    zvals=[v for _,lo,hi,_ in zones for v in (lo,hi)]
    visible_z=[v for v in zvals if min(lows)*0.97 <= v <= max(highs)*1.03]
    pmin=min(lows+visible_z); pmax=max(highs+visible_z); pad=max((pmax-pmin)*0.18,0.01); pmin-=pad; pmax+=pad
    W,H=1600,900; left,right,top,bottom=42,1480,105,735
    im=Image.new("RGB",(W,H),(15,18,24)); d=ImageDraw.Draw(im, "RGB")
    title=_font(38); normal=_font(22); small=_font(18); tiny=_font(15)
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
    step=(right-left)/len(rows)
    body=max(3,int(step*0.55))

    # ICT zones are rays: they begin at the candle that created them and extend
    # only to the right. Never back-fill a zone across candles that predate it.
    origins={}
    for i in range(max(0,len(rows)-100),len(rows)-2):
        lft,rgt=rows[i],rows[i+2]
        if float(lft["high"])<float(rgt["low"]):
            origins[("FVG BULLISH",float(lft["high"]),float(rgt["low"]))]=i
        if float(lft["low"])>float(rgt["high"]):
            origins[("FVG BEARISH",float(rgt["high"]),float(lft["low"]))]=i
    recent_start=max(0,len(rows)-60)
    recent=rows[recent_start:]
    ranges=[float(x["high"])-float(x["low"]) for x in recent[:-1]]
    avg=sum(ranges)/len(ranges) if ranges else 0
    for j in range(1,len(recent)):
        cur,prev=recent[j],recent[j-1]
        displacement=avg>0 and float(cur["high"])-float(cur["low"])>=avg*1.35
        if displacement and float(cur["close"])>float(cur["open"]) and float(prev["close"])<float(prev["open"]):
            origins[("OB BULLISH",float(prev["low"]),float(prev["high"]))]=recent_start+j-1
        if displacement and float(cur["close"])<float(cur["open"]) and float(prev["close"])>float(prev["open"]):
            origins[("OB BEARISH",float(prev["low"]),float(prev["high"]))]=recent_start+j-1
    q=derive_daily_quadrant(snapshot.timeframes.get("D1", ()))
    q_origin=0
    if q:
        q_origin=next((i for i,r in enumerate(rows) if int(r["time"])>=q.candle_time),0)

    def origin_x(label,lo,hi):
        if label=="QUADRANT" or label in level_styles:
            idx=q_origin
        else:
            idx=origins.get((label,lo,hi),0)
        return left+(idx+0.5)*step

    for label,lo,hi,extra in zones:
        if hi<pmin or lo>pmax: continue
        y1,y2=y(hi),y(lo); x1=origin_x(label,lo,hi)
        if label in level_styles:
            col=level_styles[label]
            d.line((x1,y1,right,y1),fill=col,width=2)
            d.text((right+12,y1-10),f"{label} {lo:.2f}",font=small,fill=col)
            continue
        outline,fill=zone_styles.get(label,((125,130,145),(50,54,64)))
        top_y,bottom_y=min(y1,y2),max(y1,y2)
        if label=="QUADRANT":
            # Approved template: Daily Quadrant has NO background fill.
            # Only thin, muted boundary rays plus Q25/Q50/Q75 levels.
            for yy in (top_y,bottom_y):
                dash=12; gap=8; xx=x1
                while xx<right:
                    d.line((xx,yy,min(xx+dash,right),yy),fill=(150,125,205),width=1)
                    xx+=dash+gap
            tag=f"Daily Quadrant  {lo:.2f}-{hi:.2f}"
            d.text((x1+8,top_y+6),tag,font=small,fill=(180,155,225))
            continue
        if bottom_y-top_y<5: bottom_y=top_y+5
        # Approved minimal template: FVG/OB zones are visual only.
        # Their meaning is carried by color + legend; no text is drawn inside zones.
        d.rectangle((x1,top_y,right,bottom_y),fill=fill,outline=outline,width=2)

    for i,r in enumerate(rows):
        x=left+(i+0.5)*step; o,c,h,l=map(float,(r["open"],r["close"],r["high"],r["low"]))
        up=c>=o; col=(105,190,150) if up else (215,105,115)
        d.line((x,y(h),x,y(l)),fill=col,width=2)
        d.rectangle((x-body/2,min(y(o),y(c)),x+body/2,max(y(o),y(c))+1),fill=col)
    if snapshot.bid and snapshot.ask:
        mid=(snapshot.bid+snapshot.ask)/2
        if pmin<=mid<=pmax:
            yy=y(mid); d.line((left,yy,right,yy),fill=(235,200,90),width=2); d.text((right+12,yy-10),f"NOW {mid:.2f}",font=small,fill=(235,200,90))
    guide_y=785
    d.rounded_rectangle((left,guide_y,right,855),radius=12,outline=(48,58,72),width=2)
    guide=[("Daily Quadrant",(170,135,255)),("Bullish FVG",(70,205,150)),("Bearish FVG",(235,95,110)),("Bullish OB",(70,150,235)),("Bearish OB",(240,155,65)),("Current Price",(235,200,90))]
    gx=left+18
    for name,col in guide:
        d.rounded_rectangle((gx,guide_y+18,gx+24,guide_y+42),radius=4,fill=col)
        d.text((gx+34,guide_y+18),name,font=tiny,fill=(210,216,226))
        gx+=205
    d.text((left,H-28),"SAME DATA  •  CLEANER PICTURE  •  RIGHT-EXTENSION ZONES",font=tiny,fill=(145,150,162))
    footer="Source: NEXUS MT5 Market Feed  •  Zones derived from the same ICT snapshot"
    fw=d.textbbox((0,0),footer,font=tiny)[2]
    d.text((right-fw,H-28),footer,font=tiny,fill=(145,150,162))
    buf=io.BytesIO(); im.save(buf,format="PNG",optimize=True); return buf.getvalue()
