from __future__ import annotations

import io
import random
from PIL import Image, ImageDraw

from app.content.visuals import W, H, BG, PANEL, TEXT, MUTED, GOLD, GREEN, RED, BORDER, _font, _rtl, _wrap, _right_text, _rounded, _load_logo


def _candles(draw: ImageDraw.ImageDraw, box: tuple[int,int,int,int], slug: str, mode: str) -> None:
    x1,y1,x2,y2 = box
    _rounded(draw, box, 28, PANEL, BORDER, 2)
    rng = random.Random(f"academy:{slug}:{mode}")
    n = 24
    vals = [0.34]
    drift = 0.025 if slug in {"market_structure","mss","displacement"} else 0.0
    for i in range(n):
        pulse = 0.06 if i in {6,12,18} else 0
        vals.append(max(0.10, min(0.90, vals[-1] + drift + rng.uniform(-0.07,0.06) + (pulse if i % 2 == 0 else -pulse/2))))
    step = (x2-x1-110)/n
    yy=lambda v: y2-55-v*(y2-y1-110)
    for i in range(n):
        o,c=vals[i],vals[i+1]
        hi=min(.96,max(o,c)+rng.uniform(.02,.07)); lo=max(.05,min(o,c)-rng.uniform(.02,.07))
        cx=x1+55+i*step; color=GREEN if c>=o else RED
        draw.line((cx,yy(hi),cx,yy(lo)),fill=color,width=3)
        top,bottom=sorted((yy(o),yy(c))); bottom=max(bottom,top+5)
        draw.rounded_rectangle((cx-7,top,cx+7,bottom),3,fill=color)

    accent=GOLD
    if slug == "market_structure":
        labels=[(5,"HL"),(9,"HH"),(13,"HL"),(19,"HH")]
        for idx,label in labels:
            cx=x1+55+idx*step; cy=yy(vals[idx+1])
            draw.ellipse((cx-7,cy-7,cx+7,cy+7),fill=accent)
            draw.text((cx,cy-40),label,font=_font(25,True),fill=accent,anchor="mm")
        draw.line((x1+55,y2-95,x2-55,y1+95),fill=accent,width=3)
    elif slug == "liquidity":
        level=yy(max(vals[7:14]))
        draw.line((x1+55,level,x2-55,level),fill=accent,width=3)
        draw.text((x1+65,level-35),"BUY-SIDE LIQUIDITY",font=_font(20,True),fill=accent)
    elif slug == "fvg":
        mid=(y1+y2)//2
        draw.rounded_rectangle((x1+360,mid-70,x1+650,mid+70),18,outline=accent,width=4)
        draw.text((x1+505,mid),"FVG",font=_font(34,True),fill=accent,anchor="mm")
    elif slug == "order_block":
        draw.rounded_rectangle((x1+120,y2-220,x1+360,y2-90),18,outline=accent,width=4)
        draw.text((x1+240,y2-155),"ORDER BLOCK",font=_font(24,True),fill=accent,anchor="mm")
    elif slug == "mss":
        level=yy(vals[10]); draw.line((x1+55,level,x2-55,level),fill=accent,width=3)
        draw.text((x2-80,level-34),"MSS",font=_font(27,True),fill=accent,anchor="ra")
    elif slug == "premium_discount":
        mid=(y1+y2)//2; draw.line((x1+55,mid,x2-55,mid),fill=accent,width=3)
        draw.text((x2-75,mid-45),"PREMIUM",font=_font(24,True),fill=RED,anchor="ra")
        draw.text((x2-75,mid+22),"DISCOUNT",font=_font(24,True),fill=GREEN,anchor="ra")
    elif slug == "session_liquidity":
        third=(x2-x1-110)/3
        for j,name in enumerate(("ASIA","LONDON","NEW YORK")):
            left=x1+55+j*third; draw.line((left,y1+55,left,y2-55),fill=BORDER,width=2)
            draw.text((left+10,y1+65),name,font=_font(20,True),fill=accent)


def _header(image: Image.Image, title: str, step: str) -> tuple[ImageDraw.ImageDraw,int]:
    draw=ImageDraw.Draw(image); logo=_load_logo()
    if logo is not None: image.paste(logo,(48,32),logo)
    else: draw.text((52,42),"NEXUS",font=_font(54,True),fill=TEXT)
    draw.text((56,120),f"ACADEMY V2 · {step}",font=_font(22,True),fill=GOLD)
    draw.line((56,162,W-56,162),fill=BORDER,width=2)
    y=205
    for line in _wrap(draw,title,_font(48,True),W-120,2):
        _right_text(draw,(W-60,y),line,_font(48,True),TEXT); y+=58
    return draw,y


def render_academy_slide(*, title: str, slug: str, step: str, body: str,
                         bullets: list[str] | None = None, note: str = "") -> bytes:
    image=Image.new("RGB",(W,H),BG); draw,y=_header(image,title,step)
    chart=(56,330,W-56,790); _candles(draw,chart,slug,step)
    _rounded(draw,(56,825,W-56,1190),24,(8,29,46),BORDER,2)
    y=860
    for line in _wrap(draw,body,_font(30),W-150,4):
        _right_text(draw,(W-82,y),line,_font(30),TEXT); y+=43
    for point in (bullets or [])[:3]:
        draw.ellipse((W-100,y+8,W-82,y+26),fill=GOLD)
        lines=_wrap(draw,point,_font(26),W-185,2)
        for line in lines:
            _right_text(draw,(W-118,y),line,_font(26),TEXT); y+=37
        y+=12
    if note:
        draw.line((56,1220,W-56,1220),fill=BORDER,width=2)
        _right_text(draw,(W-58,1250),note,_font(24,True),GOLD)
    draw.text((56,1285),"NEXUS ACADEMY · ONE CONCEPT · ONE CHART · ONE EXERCISE",font=_font(17,True),fill=MUTED)
    out=io.BytesIO(); image.save(out,format="PNG",optimize=True); return out.getvalue()
