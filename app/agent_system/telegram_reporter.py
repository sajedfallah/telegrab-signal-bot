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
        return f"🕐 NEXUS ICT HOURLY | {symbol}\n\nAnalysis unavailable: {record['error']}\n\nMODE: SHADOW — NO REAL ORDER"
    assessments=record.get("assessments") or []
    ict=next((a for a in assessments if isinstance(a,Mapping) and str(a.get("agent") or "").startswith("nexus-ict")),None)
    direction=str((ict or {}).get("direction") or record.get("direction") or "NEUTRAL")
    lines=[f"🕐 NEXUS ICT HOURLY | {symbol}","",f"ICT Bias: {direction}",f"Market State: {record.get('final') or '-'}"]
    if ict:
        evidence=list(ict.get("evidence") or [])
        # ICT evidence is generated deterministically from 1H structure, 15M
        # location/FVG/OB/Daily Quadrant and the 5M trigger. Preserve it rather
        # than inventing narrative levels that are absent from the snapshot.
        if evidence:
            lines.extend(["","ICT Analysis:"])
            for item in evidence[:12]: lines.append(f"• {item}")
        invalidation=list(ict.get("invalidation") or [])
        if invalidation:
            lines.extend(["","Waiting / Invalidation:"])
            for item in invalidation[:6]: lines.append(f"• {item}")
        missing=list(ict.get("missing_data") or [])
        if missing: lines.extend(["",f"Missing data: {', '.join(str(x) for x in missing)}"])
    else:
        lines.extend(["","ICT Analysis: scanner did not escalate this snapshot; no directional ICT setup is asserted."])
    if record.get("entry") is not None:
        lines.extend(["","📐 SIGNAL",f"Direction: {record.get('direction')}",f"Entry: {record.get('entry')}",f"Entry Zone: {record.get('entry_low')} - {record.get('entry_high')}",f"SL: {record.get('stop_loss')}"])
        for i,tp in enumerate(record.get("take_profits") or [],1): lines.append(f"TP{i}: {tp}")
        lines.extend([f"RR(TP1): {float(record.get('rr') or 0):.2f}",f"Expires: {record.get('signal_expires_at')}"])
    else:
        lines.extend(["","Signal: WAIT — no confirmed signal in this hourly snapshot"])
    lines.extend(["","MODE: SHADOW — NO REAL ORDER"])
    return "\n".join(lines)
