from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Mapping

class TelegramReportError(RuntimeError): pass

@dataclass(frozen=True)
class TelegramShadowReporter:
    bot_token: str
    chat_id: str
    timeout_seconds: int = 10
    def __post_init__(self):
        if not self.bot_token.strip(): raise ValueError("bot_token is required")
        if not self.chat_id.strip(): raise ValueError("chat_id is required")
    def send_text(self,text:str)->None:
        payload=urllib.parse.urlencode({"chat_id":self.chat_id,"text":text,"disable_web_page_preview":"true"}).encode("utf-8")
        request=urllib.request.Request(f"https://api.telegram.org/bot{self.bot_token}/sendMessage",data=payload,method="POST")
        try:
            with urllib.request.urlopen(request,timeout=self.timeout_seconds) as response: body=json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc: raise TelegramReportError(f"Telegram sendMessage HTTP {exc.code}") from None
        except urllib.error.URLError as exc:
            reason=getattr(exc,"reason",None); label=type(reason).__name__ if reason is not None else "network_error"; raise TelegramReportError(f"Telegram sendMessage network failure: {label}") from None
        except (TimeoutError,OSError,ValueError,json.JSONDecodeError) as exc: raise TelegramReportError(f"Telegram sendMessage failure: {type(exc).__name__}") from None
        if not body.get("ok"): raise TelegramReportError(f"Telegram sendMessage rejected: {str(body.get('description') or 'unknown error')}")

def format_shadow_record(record:Mapping[str,object])->str:
    symbol=str(record.get("symbol") or "UNKNOWN")
    if record.get("error"): return f"⚠️ NEXUS AGENT TEST | {symbol}\n\nState: NO_TRADE\nFeed/Runner Error: {record['error']}\n\nMODE: SHADOW — NO REAL ORDER"
    scan=str(record.get("scan") or "-"); supervisor=str(record.get("supervisor") or "-"); final=str(record.get("final") or "-"); direction=str(record.get("direction") or "NEUTRAL")
    risk_allowed=record.get("risk_allowed"); risk_text="NOT_EVALUATED" if risk_allowed is None else ("PASSED" if risk_allowed else "BLOCKED")
    blocks=record.get("risk_blocks") or []; signal_blocks=record.get("signal_blocks") or []
    lines=[f"🧠 NEXUS AGENT TEST | {symbol}","",f"Scanner: {scan}",f"Supervisor: {supervisor}",f"Final: {final}",f"Direction: {direction}"]
    if record.get("entry") is not None:
        tps=record.get("take_profits") or []
        lines.extend(["", "📐 ICT SIGNAL PLAN",f"Entry: {record['entry']}",f"Entry Zone: {record.get('entry_low')} - {record.get('entry_high')}",f"SL: {record.get('stop_loss')}"])
        for i,tp in enumerate(tps,1): lines.append(f"TP{i}: {tp}")
        lines.extend([f"RR(TP1): {float(record.get('rr') or 0):.2f}",f"Expires: {record.get('signal_expires_at')}"])
    elif signal_blocks:
        lines.extend(["",f"Signal Builder: BLOCKED ({', '.join(str(x) for x in signal_blocks)})"])
    lines.extend(["",f"Risk Gate: {risk_text}",f"Risk Blocks: {', '.join(str(x) for x in blocks) if blocks else '-'}","","MODE: SHADOW — NO REAL ORDER"])
    return "\n".join(lines)


def format_hourly_analysis(record:Mapping[str,object])->str:
    symbol=str(record.get("symbol") or "UNKNOWN")
    if record.get("error"):
        return f"📊 آپدیت NEXUS | {symbol}\n\nبچه‌ها، فعلاً داده کافی برای آپدیت بازار نداریم: {record['error']}"
    assessments=record.get("assessments") or []
    ict=next((a for a in assessments if isinstance(a,Mapping) and str(a.get("agent") or "").startswith("nexus-ict")),None)
    direction=str((ict or {}).get("direction") or record.get("direction") or "NEUTRAL")
    bias={"LONG":"صعودی","SHORT":"نزولی","NEUTRAL":"خنثی / منتظر تأیید"}.get(direction,direction)
    bid=record.get("bid"); ask=record.get("ask")
    analysis_tf=str(record.get("analysis_timeframe") or "M5")
    lines=[f"📊 آپدیت NEXUS | {symbol} • {analysis_tf}","",f"بچه‌های نکسوس، یه آپدیت سریع از بازار داشته باشیم 👇","",f"📍 قیمت فعلی MT5: Bid {bid or '-'} | Ask {ask or '-'}",f"🧭 وضعیت فعلی ICT: {bias}"]
    evidence=list((ict or {}).get("evidence") or [])
    h1=[str(x) for x in evidence if str(x).startswith("1H ")]
    quadrant=[str(x) for x in evidence if str(x).startswith("Daily Quadrant ")]
    inside=any(str(x).startswith("Price is inside Daily Quadrant") for x in evidence)
    fvgs=[str(x) for x in evidence if f"{analysis_tf} bullish FVG" in str(x) or f"{analysis_tf} bearish FVG" in str(x)]
    obs=[str(x) for x in evidence if f"{analysis_tf} bullish OB" in str(x) or f"{analysis_tf} bearish OB" in str(x)]
    triggers=[str(x) for x in evidence if str(x).startswith(f"{analysis_tf} ")]
    translations={
        "1H structure HH/HL":"ساختار 1H فعلاً HH/HL است؛ یعنی دست بالا هنوز با خریدارهاست.",
        "1H structure LH/LL":"ساختار 1H فعلاً LH/LL است؛ یعنی فشار اصلی سمت فروشنده‌هاست.",
        "1H structure has bullish tendency":"ساختار 1H فعلاً تمایل صعودی دارد.",
        "1H structure has bearish tendency":"ساختار 1H فعلاً تمایل نزولی دارد.",
        "1H structure is neutral/ranging":"ساختار 1H فعلاً رنج و بدون جهت واضح است.",
        "5M bullish displacement/MSS":"روی 5M جابه‌جایی/MSS صعودی دیده شده.",
        "5M bearish displacement/MSS":"روی 5M جابه‌جایی/MSS نزولی دیده شده.",
    }
    lines.extend(["","🔹 نمای 1H:"])
    lines.append("• "+translations.get(h1[0],h1[0]) if h1 else "• فعلاً ساختار مشخص 1H در داده تحلیل ثبت نشده.")
    lines.extend(["","🎯 Daily Quadrant:"])
    if quadrant:
        import re
        q=re.search(r"Daily Quadrant (\w+) ([\d.]+)-([\d.]+); 25=([\d.]+), 50=([\d.]+), 75=([\d.]+)",quadrant[0])
        if q:
            side,low,high,l25,l50,l75=q.groups()
            side_fa="بخش بالایی Wick" if side=="UPPER" else ("بخش پایینی Wick" if side=="LOWER" else side)
            lines.extend([f"• محدوده کامل: {low} تا {high} ({side_fa})",f"• سطح 25٪: {l25}",f"• سطح 50٪: {l50}",f"• سطح 75٪: {l75}"])
            if inside: lines.append("• قیمت الان داخل همین Quadrant روزانه است؛ پس این محدوده برای واکنش و برگشت احتمالی وزن بالایی دارد.")
        else: lines.append("• "+quadrant[0])
    else: lines.append("• Quadrant معتبر در Snapshot فعلی ثبت نشده.")
    lines.extend(["",f"📐 نواحی مهم {analysis_tf}:"])
    if fvgs or obs:
        for x in fvgs+obs:
            s=x.replace(f"{analysis_tf} bullish FVG",f"• FVG صعودی {analysis_tf}:").replace(f"{analysis_tf} bearish FVG",f"• FVG نزولی {analysis_tf}:").replace(f"{analysis_tf} bullish OB",f"• OB صعودی {analysis_tf}:").replace(f"{analysis_tf} bearish OB",f"• OB نزولی {analysis_tf}:")
            lines.append(s)
    else: lines.append("• FVG/OB فعالی در Snapshot فعلی ثبت نشده.")
    lines.extend(["","⏳ الان دقیقاً منتظر چی هستیم؟"])
    hi=record.get("m5_recent_high"); lo=record.get("m5_recent_low")
    if lo is not None: lines.append(f"• سناریوی Long در {analysis_tf}: محدوده نقدینگی پایین تا حوالی {float(lo):g} زیر نظر است؛ اول Sweep/Reclaim سمت Sell-side و بعد MSS/Displacement صعودی {analysis_tf} لازم داریم.")
    if hi is not None: lines.append(f"• سناریوی Short در {analysis_tf}: محدوده نقدینگی بالا تا حوالی {float(hi):g} زیر نظر است؛ اول Sweep/Reclaim سمت Buy-side و بعد MSS/Displacement نزولی {analysis_tf} لازم داریم.")
    for x in triggers[:4]:
        translated=x.replace(f"{analysis_tf} bullish displacement/MSS",f"روی {analysis_tf} جابه‌جایی/MSS صعودی دیده شده.").replace(f"{analysis_tf} bearish displacement/MSS",f"روی {analysis_tf} جابه‌جایی/MSS نزولی دیده شده.")
        lines.append("• "+translations.get(x,translated))
    invalid=list((ict or {}).get("invalidation") or [])
    if "HTF/LTF alignment required" in invalid: lines.append(f"• اگر تریگر {analysis_tf} خلاف جهت ساختار 1H باشد، عجله نمی‌کنیم و منتظر هم‌جهتی می‌مانیم.")
    missing=list((ict or {}).get("missing_data") or [])
    if missing: lines.extend(["",f"⚠️ داده ناقص: {', '.join(str(x) for x in missing)}"])
    lines.extend(["","📌 جمع‌بندی:"])
    if direction=="LONG": lines.append("فعلاً ساختار به نفع Long تأیید شده، ولی ورود فقط بعد از تکمیل شرایط اجرایی و Risk Gate.")
    elif direction=="SHORT": lines.append("فعلاً ساختار به نفع Short تأیید شده، ولی ورود فقط بعد از تکمیل شرایط اجرایی و Risk Gate.")
    else: lines.append(f"فعلاً ورود نداریم. بازار توی ناحیه‌های مهم قرار گرفته و منتظریم {analysis_tf} جهت بعدی رو با Sweep + MSS مشخص کنه؛ بدون تأیید وارد نمی‌شیم.")
    return "\n".join(lines)
