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
        return f"🕐 تحلیل ساعتی NEXUS | {symbol}\n\nتحلیل در دسترس نیست: {record['error']}\n\nحالت: SHADOW — بدون معامله واقعی"
    assessments=record.get("assessments") or []
    ict=next((a for a in assessments if isinstance(a,Mapping) and str(a.get("agent") or "").startswith("nexus-ict")),None)
    direction=str((ict or {}).get("direction") or record.get("direction") or "NEUTRAL")
    bias={"LONG":"صعودی","SHORT":"نزولی","NEUTRAL":"خنثی / در انتظار تأیید"}.get(direction,direction)
    lines=[f"🕐 تحلیل ساعتی NEXUS | {symbol}","",f"📍 قیمت MT5: Bid {record.get('bid') or '-'} | Ask {record.get('ask') or '-'}",f"🧭 دیدگاه ICT: {bias}"]
    if ict:
        evidence=list(ict.get("evidence") or [])
        if evidence:
            lines.extend(["","🔎 ساختار و نواحی مهم:"])
            translations={
                "1H structure HH/HL":"ساختار 1H: سقف و کف بالاتر (HH/HL) — تمایل صعودی",
                "1H structure LH/LL":"ساختار 1H: سقف و کف پایین‌تر (LH/LL) — تمایل نزولی",
                "1H structure has bullish tendency":"ساختار 1H تمایل صعودی دارد",
                "1H structure has bearish tendency":"ساختار 1H تمایل نزولی دارد",
                "1H structure is neutral/ranging":"ساختار 1H خنثی / رنج است",
                "5M bullish displacement/MSS":"5M: جابه‌جایی/MSS صعودی مشاهده شده",
                "5M bearish displacement/MSS":"5M: جابه‌جایی/MSS نزولی مشاهده شده",
                "Price is inside Daily Quadrant HTF reaction zone; lower-timeframe confirmation remains mandatory":"قیمت داخل Daily Quadrant است؛ این ناحیه واکنشی HTF مهم است و ورود فقط با تأیید 5M معتبر می‌شود",
                "5M trigger conflicts with 1H bias; wait":"تریگر 5M با Bias تایم 1H تضاد دارد؛ فعلاً صبر",
            }
            for item in evidence[:14]:
                item=str(item); lines.append(f"• {translations.get(item,item)}")
        invalid=list(ict.get("invalidation") or [])
        if invalid:
            lines.extend(["","⏳ چیزی که منتظرش هستیم:"])
            for item in invalid[:6]:
                s=str(item)
                if s=="valid 5M liquidity sweep + MSS confirmation required": s="Sweep معتبر نقدینگی + تأیید MSS در 5M"
                elif s=="HTF/LTF alignment required": s="هم‌جهتی ساختار HTF و تریگر LTF"
                elif s=="invalidate if 5M bullish structure fails after trigger": s="سناریوی Long با شکست ساختار صعودی 5M نامعتبر می‌شود"
                elif s=="invalidate if 5M bearish structure fails after trigger": s="سناریوی Short با شکست ساختار نزولی 5M نامعتبر می‌شود"
                lines.append(f"• {s}")
        missing=list(ict.get("missing_data") or [])
        if missing: lines.extend(["",f"⚠️ داده ناقص: {', '.join(str(x) for x in missing)}"])
    else:
        lines.extend(["","⚠️ تحلیل ICT برای این Snapshot در دسترس نیست."])
    if record.get("entry") is not None and record.get("risk_allowed") is True:
        lines.extend(["","🚨 سیگنال تأییدشده",f"جهت: {record.get('direction')}",f"Entry: {record.get('entry')}",f"Entry Zone: {record.get('entry_low')} - {record.get('entry_high')}",f"SL: {record.get('stop_loss')}"])
        for i,tp in enumerate(record.get("take_profits") or [],1): lines.append(f"TP{i}: {tp}")
        lines.append(f"RR(TP1): {float(record.get('rr') or 0):.2f}")
    else:
        lines.extend(["","📌 جمع‌بندی: فعلاً ورود تأییدشده نداریم؛ نواحی بالا زیر نظر می‌مانند و برای تأیید 5M صبر می‌کنیم."])
    lines.extend(["","حالت: SHADOW — بدون معامله واقعی"])
    return "\n".join(lines)
