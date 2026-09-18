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
        return f"🕐 NEXUS HOURLY ANALYSIS | {symbol}\n\nMarket analysis unavailable: {record['error']}\n\nMODE: SHADOW — NO REAL ORDER"
    lines=[f"🕐 NEXUS HOURLY ANALYSIS | {symbol}","",f"Scanner: {record.get('scan') or '-'}",f"Supervisor: {record.get('supervisor') or '-'}",f"Current State: {record.get('final') or '-'}",f"Direction: {record.get('direction') or 'NEUTRAL'}"]
    assessments=record.get("assessments") or []
    for assessment in assessments:
        if not isinstance(assessment, Mapping):
            continue
        name=str(assessment.get("agent") or "agent")
        direction=str(assessment.get("direction") or "NEUTRAL")
        lines.extend(["",f"• {name}: {direction}"])
        for item in list(assessment.get("evidence") or [])[:8]:
            lines.append(f"  - {item}")
        missing=list(assessment.get("missing_data") or [])
        if missing:
            lines.append(f"  Missing: {', '.join(str(x) for x in missing)}")
    if record.get("entry") is not None:
        lines.extend(["","📐 ACTIVE SIGNAL CANDIDATE",f"Entry: {record.get('entry')}",f"SL: {record.get('stop_loss')}"])
        for i,tp in enumerate(record.get("take_profits") or [],1):
            lines.append(f"TP{i}: {tp}")
        lines.append(f"RR(TP1): {float(record.get('rr') or 0):.2f}")
    else:
        lines.extend(["","Signal: WAIT — no confirmed signal candidate in this snapshot"])
    lines.extend(["","MODE: SHADOW — NO REAL ORDER"])
    return "\n".join(lines)