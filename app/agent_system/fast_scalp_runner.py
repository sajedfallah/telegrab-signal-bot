from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone

from .fast_scalp import FastScalpState, assess_fast_scalp, build_fast_scalp_signal
from .risk_gate import RiskPolicy
from .snapshot_adapter import build_mt5_snapshot
from .telegram_reporter import TelegramShadowReporter


def _fingerprint(plan):
    return (plan.symbol,plan.direction.value,round(plan.entry_low,5),round(plan.entry_high,5),round(plan.stop_loss,5),tuple(round(x,5) for x in plan.take_profits))


def _format(plan):
    lines=[
        f"⚡ NEXUS FAST SCALP | {plan.symbol} • M1",
        "",
        f"Direction: {plan.direction.value}",
        f"Entry: {plan.entry:g}",
        f"Entry Zone: {plan.entry_low:g} - {plan.entry_high:g}",
        f"SL: {plan.stop_loss:g}",
    ]
    for i,tp in enumerate(plan.take_profits,1): lines.append(f"TP{i}: {tp:g}")
    lines.extend([f"RR(TP1): {plan.rr:.2f}","","Strategy: ICT_FAST_SCALP_M1","Mode: SHADOW SIGNAL — NO AUTOTRADE"])
    return "\n".join(lines)


def run(account,symbols,interval,reporter,min_rr):
    # Fast-scalp publication remains fail-closed unless an explicit shadow RR
    # threshold is configured. This is intentionally separate from production.
    policy=RiskPolicy(version="fast-scalp-shadow-v1",min_rr=min_rr)
    sent={}
    while True:
        for symbol in symbols:
            try:
                snap=build_mt5_snapshot(account,symbol)
                setup=assess_fast_scalp(snap)
                if setup.state != FastScalpState.ENTRY_READY: continue
                plan,blocks=build_fast_scalp_signal(snap,setup)
                if plan is None: continue
                # Deterministic fast-scalp gate: freshness, quote, explicit RR policy.
                gate_blocks=[]
                if snap.data_freshness_ms>policy.max_freshness_ms: gate_blocks.append("stale_market_data")
                if snap.bid is None or snap.ask is None: gate_blocks.append("missing_quote")
                if policy.min_rr is None: gate_blocks.append("risk_policy_missing:min_rr")
                elif plan.rr<policy.min_rr: gate_blocks.append("rr_below_policy")
                high=[e for e in snap.scheduled_events if str(e.get("impact") or "").upper() in {"HIGH","CRITICAL"} and bool(e.get("active_window",False))]
                if high: gate_blocks.append("high_impact_news_window")
                if gate_blocks: continue
                fp=_fingerprint(plan)
                if sent.get(symbol)==fp: continue
                reporter.send_text(_format(plan)); sent[symbol]=fp
                print(json.dumps({"at":datetime.now(timezone.utc).isoformat(),"fast_scalp_signal":fp},ensure_ascii=False))
            except Exception as exc:
                print(json.dumps({"symbol":symbol,"fast_scalp_error":f"{type(exc).__name__}: {exc}"},ensure_ascii=False))
        time.sleep(interval)


def main():
    p=argparse.ArgumentParser(description="NEXUS M1 fast-scalp shadow signal watcher")
    p.add_argument("--account",required=True); p.add_argument("--symbols",default="XAUUSD")
    p.add_argument("--interval",type=int,default=10); p.add_argument("--min-rr",type=float,default=None)
    a=p.parse_args()
    if a.interval<5: p.error("--interval must be >= 5")
    if a.min_rr is not None and a.min_rr<=0: p.error("--min-rr must be > 0")
    token=os.getenv("NEXUS_AGENT_TEST_BOT_TOKEN","").strip(); chat=os.getenv("NEXUS_AGENT_TEST_CHAT_ID","").strip()
    if not token or not chat: raise RuntimeError("Telegram test bot token/chat id are required")
    symbols=tuple(dict.fromkeys(x.strip().upper() for x in a.symbols.split(",") if x.strip()))
    run(a.account,symbols,a.interval,TelegramShadowReporter(token,chat),a.min_rr)


if __name__=="__main__": main()
