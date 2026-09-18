from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone

from .fast_scalp import FastScalpState, assess_fast_scalp, build_fast_scalp_signal
from .orchestrator import run_shadow
from .risk_gate import RiskPolicy
from .snapshot_adapter import build_mt5_snapshot
from .telegram_reporter import TelegramShadowReporter, format_shadow_record


def _standard_fingerprint(record):
    return ("ICT_STANDARD_M5",record.get("symbol"),record.get("direction"),record.get("entry_low"),record.get("entry_high"),record.get("stop_loss"),tuple(record.get("take_profits") or []))


def _fast_fingerprint(plan):
    return ("ICT_FAST_SCALP_M1",plan.symbol,plan.direction.value,round(plan.entry_low,5),round(plan.entry_high,5),round(plan.stop_loss,5),tuple(round(x,5) for x in plan.take_profits))


def _format_fast(plan):
    lines=[f"⚡ NEXUS FAST SCALP | {plan.symbol} • M1","",f"Direction: {plan.direction.value}",f"Entry: {plan.entry:g}",f"Entry Zone: {plan.entry_low:g} - {plan.entry_high:g}",f"SL: {plan.stop_loss:g}"]
    for i,tp in enumerate(plan.take_profits,1): lines.append(f"TP{i}: {tp:g}")
    lines.extend([f"RR(TP1): {plan.rr:.2f}","","Strategy: ICT_FAST_SCALP_M1","Mode: SHADOW SIGNAL — NO AUTOTRADE"])
    return "\n".join(lines)


def _summary(result):
    out={"symbol":result.initial_snapshot.symbol,"scan":result.scan.state.value,"supervisor":result.supervisor.state.value,"final":result.final_decision.state.value,"direction":result.final_decision.direction.value if result.final_decision.direction else None,"risk_allowed":result.risk.allowed if result.risk else None,"risk_blocks":list(result.risk.hard_blocks) if result.risk else [],"signal_blocks":list(result.signal_blocks)}
    if result.signal:
        s=result.signal
        out.update({"entry":s.entry,"entry_low":s.entry_low,"entry_high":s.entry_high,"stop_loss":s.stop_loss,"take_profits":list(s.take_profits),"rr":s.rr,"signal_expires_at":s.expires_at.isoformat(),"strategy_id":"ICT_STANDARD_M5"})
    return out


def _fast_gate(snapshot,plan,policy):
    blocks=[]
    if snapshot.data_freshness_ms>policy.max_freshness_ms: blocks.append("stale_market_data")
    if snapshot.bid is None or snapshot.ask is None: blocks.append("missing_quote")
    if snapshot.missing_data: blocks.extend(f"missing:{x}" for x in snapshot.missing_data)
    if policy.min_rr is None: blocks.append("risk_policy_missing:min_rr")
    elif plan.rr<policy.min_rr: blocks.append("rr_below_policy")
    high=[e for e in snapshot.scheduled_events if str(e.get("impact") or "").upper() in {"HIGH","CRITICAL"} and bool(e.get("active_window",False))]
    if high: blocks.append("high_impact_news_window")
    return tuple(dict.fromkeys(blocks))


def run_cycle(account,symbols,reporter,standard_min_rr,fast_min_rr,sent=None):
    standard_policy=RiskPolicy(version="standard-m5-shadow-v1",min_rr=standard_min_rr)
    fast_policy=RiskPolicy(version="fast-scalp-m1-shadow-v1",min_rr=fast_min_rr)
    sent=sent if sent is not None else {}
    for symbol in symbols:
        try:
            standard=_summary(run_shadow(account,symbol,risk_policy=standard_policy))
            if standard.get("entry") is not None and standard.get("risk_allowed") is True:
                fp=_standard_fingerprint(standard)
                if sent.get((symbol,"M5"))!=fp:
                    reporter.send_text("📐 Strategy: ICT_STANDARD_M5\\n\\n"+format_shadow_record(standard))
                    sent[(symbol,"M5")]=fp
                    print(json.dumps({"at":datetime.now(timezone.utc).isoformat(),"standard_m5_signal":fp},ensure_ascii=False))

            snap=build_mt5_snapshot(account,symbol)
            setup=assess_fast_scalp(snap)
            if setup.state==FastScalpState.ENTRY_READY:
                plan,_=build_fast_scalp_signal(snap,setup)
                if plan is not None and not _fast_gate(snap,plan,fast_policy):
                    fp=_fast_fingerprint(plan)
                    if sent.get((symbol,"M1"))!=fp:
                        reporter.send_text(_format_fast(plan))
                        sent[(symbol,"M1")]=fp
                        print(json.dumps({"at":datetime.now(timezone.utc).isoformat(),"fast_m1_signal":fp},ensure_ascii=False))
        except Exception as exc:
            print(json.dumps({"symbol":symbol,"signal_watcher_error":f"{type(exc).__name__}: {exc}"},ensure_ascii=False))
    return sent


def run(account,symbols,interval,reporter,standard_min_rr,fast_min_rr):
    sent={}
    while True:
        sent=run_cycle(account,symbols,reporter,standard_min_rr,fast_min_rr,sent)
        time.sleep(interval)


def main():
    p=argparse.ArgumentParser(description="NEXUS unified M5 Standard + M1 Fast Scalp shadow signal watcher")
    p.add_argument("--account",required=True); p.add_argument("--symbols",default="XAUUSD")
    p.add_argument("--interval",type=int,default=10)
    p.add_argument("--standard-min-rr",type=float,default=None)
    p.add_argument("--fast-min-rr",type=float,default=None)
    a=p.parse_args()
    if a.interval<5: p.error("--interval must be >= 5")
    for name,value in (("--standard-min-rr",a.standard_min_rr),("--fast-min-rr",a.fast_min_rr)):
        if value is not None and value<=0: p.error(f"{name} must be > 0")
    token=os.getenv("NEXUS_AGENT_TEST_BOT_TOKEN","").strip(); chat=os.getenv("NEXUS_AGENT_TEST_CHAT_ID","").strip()
    if not token or not chat: raise RuntimeError("Telegram test bot token/chat id are required")
    symbols=tuple(dict.fromkeys(x.strip().upper() for x in a.symbols.split(",") if x.strip()))
    if not symbols: p.error("--symbols cannot be empty")
    run(a.account,symbols,a.interval,TelegramShadowReporter(token,chat),a.standard_min_rr,a.fast_min_rr)


if __name__=="__main__": main()
