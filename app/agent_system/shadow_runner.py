from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

from .contracts import WorkflowState
from .orchestrator import ShadowRunResult, run_shadow
from .risk_gate import RiskPolicy
from .snapshot_adapter import build_mt5_snapshot
from .agents.ict import assess_ict
from .telegram_reporter import TelegramShadowReporter, format_hourly_analysis, format_shadow_record

DEFAULT_SYMBOLS = ("XAUUSD", "US30", "BTC", "SOL")

@dataclass(frozen=True)
class ShadowRunnerConfig:
    account: str
    symbols: tuple[str, ...] = DEFAULT_SYMBOLS
    interval_seconds: int = 60
    journal_dir: Path = Path("data/agent_shadow")
    risk_policy: RiskPolicy | None = None
    def __post_init__(self) -> None:
        if not self.account.strip(): raise ValueError("account is required")
        if not self.symbols: raise ValueError("at least one symbol is required")
        if self.interval_seconds < 5: raise ValueError("interval_seconds must be >= 5")

def _journal_path(root: Path, symbol: str, now: datetime | None = None) -> Path:
    day=(now or datetime.now(timezone.utc)).strftime("%Y-%m-%d"); safe="".join(ch for ch in symbol.upper() if ch.isalnum() or ch in {"-","_"}); return root/safe/f"{day}.jsonl"

def _assessment_summary(a):
    return {"agent":a.agent,"direction":a.direction.value,"evidence":list(a.evidence),"invalidation":list(a.invalidation),"missing_data":list(a.missing_data)}

def _hourly_ict_record(config: ShadowRunnerConfig, symbol: str) -> dict[str,object]:
    try:
        snapshot=build_mt5_snapshot(config.account,symbol)
        ict=assess_ict(snapshot)
        return {"symbol":snapshot.symbol,"snapshot_id":snapshot.snapshot_id,"final":"ANALYSIS","direction":ict.direction.value,"bid":snapshot.bid,"ask":snapshot.ask,"assessments":[_assessment_summary(ict)]}
    except Exception as exc:
        return {"symbol":symbol,"final":WorkflowState.NO_TRADE.value,"error":f"{type(exc).__name__}: {exc}"}

def _summary(result: ShadowRunResult) -> dict[str, object]:
    out={"symbol":result.initial_snapshot.symbol,"snapshot_id":result.initial_snapshot.snapshot_id,"scan":result.scan.state.value,"supervisor":result.supervisor.state.value,"final":result.final_decision.state.value,"direction":result.final_decision.direction.value if result.final_decision.direction else None,"risk_allowed":result.risk.allowed if result.risk else None,"risk_blocks":list(result.risk.hard_blocks) if result.risk else [],"signal_blocks":list(result.signal_blocks)}
    if result.assessments:
        out["assessments"]=[_assessment_summary(a) for a in result.assessments]
    if result.signal:
        s=result.signal; out.update({"entry":s.entry,"entry_low":s.entry_low,"entry_high":s.entry_high,"stop_loss":s.stop_loss,"take_profits":list(s.take_profits),"rr":s.rr,"signal_expires_at":s.expires_at.isoformat()})
    return out

def run_cycle(config: ShadowRunnerConfig, *, runner: Callable[...,ShadowRunResult]=run_shadow) -> tuple[dict[str,object],...]:
    output=[]
    for symbol in config.symbols:
        try: output.append(_summary(runner(config.account,symbol,risk_policy=config.risk_policy,journal_path=_journal_path(config.journal_dir,symbol))))
        except Exception as exc: output.append({"symbol":symbol,"final":WorkflowState.NO_TRADE.value,"error":f"{type(exc).__name__}: {exc}"})
    return tuple(output)

def _decision_fingerprint(record: dict[str,object]) -> tuple[object,...]:
    return (record.get("scan"),record.get("supervisor"),record.get("final"),record.get("direction"),record.get("risk_allowed"),tuple(str(x) for x in (record.get("risk_blocks") or [])),tuple(str(x) for x in (record.get("signal_blocks") or [])),record.get("entry"),record.get("stop_loss"),tuple(record.get("take_profits") or []),record.get("error"))

def _report_records(records,reporter,*,change_only=False,last_sent=None):
    if reporter is None:return
    state=last_sent if last_sent is not None else {}
    for record in records:
        symbol=str(record.get("symbol") or "UNKNOWN"); fp=_decision_fingerprint(record)
        if change_only and state.get(symbol)==fp: continue
        try: reporter.send_text(format_shadow_record(record)); state[symbol]=fp
        except Exception as exc: print(json.dumps({"telegram_report_error":f"{type(exc).__name__}: {exc}","symbol":symbol},ensure_ascii=False))

def run_forever(config,reporter=None,*,change_only=False,hourly_analysis=False,hourly_seconds=3600):
    last_sent={}; last_hourly_at=0.0
    while True:
        records=run_cycle(config); now_mono=time.monotonic(); print(json.dumps({"at":datetime.now(timezone.utc).isoformat(),"records":records},ensure_ascii=False))
        if reporter is not None and hourly_analysis and (last_hourly_at == 0.0 or now_mono-last_hourly_at >= hourly_seconds):
            for symbol in config.symbols:
                record=_hourly_ict_record(config,symbol)
                try: reporter.send_text(format_hourly_analysis(record))
                except Exception as exc: print(json.dumps({"telegram_report_error":f"{type(exc).__name__}: {exc}","symbol":str(record.get("symbol") or "UNKNOWN"),"report":"hourly_analysis"},ensure_ascii=False))
            last_hourly_at=now_mono
        # Signals are time-sensitive: publish a new/changed plan immediately. Other
        # state changes remain optional through the existing change-only reporter.
        signal_records=[r for r in records if r.get("entry") is not None and r.get("risk_allowed") is True]
        _report_records(signal_records,reporter,change_only=True,last_sent=last_sent)
        if change_only and not hourly_analysis: _report_records(records,reporter,change_only=True,last_sent=last_sent)
        time.sleep(config.interval_seconds)

def _symbols(value):
    items=tuple(dict.fromkeys(x.strip().upper() for x in value.split(",") if x.strip()))
    if not items: raise argparse.ArgumentTypeError("symbols cannot be empty")
    return items

def _reporter_from_env(enabled):
    if not enabled:return None
    token=os.getenv("NEXUS_AGENT_TEST_BOT_TOKEN","").strip(); chat_id=os.getenv("NEXUS_AGENT_TEST_CHAT_ID","").strip()
    if not token or not chat_id: raise RuntimeError("Telegram test reporting requires NEXUS_AGENT_TEST_BOT_TOKEN and NEXUS_AGENT_TEST_CHAT_ID")
    return TelegramShadowReporter(token,chat_id)

def main(argv: Iterable[str]|None=None)->int:
    parser=argparse.ArgumentParser(description="NEXUS Agent System V1 observation-only shadow runner")
    parser.add_argument("--account",required=True); parser.add_argument("--symbols",type=_symbols,default=DEFAULT_SYMBOLS); parser.add_argument("--interval",type=int,default=60); parser.add_argument("--journal-dir",default="data/agent_shadow"); parser.add_argument("--once",action="store_true"); parser.add_argument("--telegram",action="store_true"); parser.add_argument("--telegram-changes-only",action="store_true"); parser.add_argument("--telegram-hourly-analysis",action="store_true",help="Send a full market analysis to Telegram every hour while still publishing signal plans immediately"); parser.add_argument("--min-rr",type=float,default=None,help="Explicit shadow risk-policy minimum RR; omitted means fail closed")
    args=parser.parse_args(list(argv) if argv is not None else None)
    if args.telegram_changes_only and not args.telegram: parser.error("--telegram-changes-only requires --telegram")
    if args.telegram_hourly_analysis and not args.telegram: parser.error("--telegram-hourly-analysis requires --telegram")
    if args.min_rr is not None and args.min_rr <= 0: parser.error("--min-rr must be > 0")
    policy=RiskPolicy(version="agent-shadow-signal-v1",min_rr=args.min_rr)
    config=ShadowRunnerConfig(account=args.account,symbols=args.symbols,interval_seconds=args.interval,journal_dir=Path(args.journal_dir),risk_policy=policy); reporter=_reporter_from_env(args.telegram)
    if args.once:
        records=run_cycle(config); print(json.dumps({"at":datetime.now(timezone.utc).isoformat(),"records":records},ensure_ascii=False)); _report_records(records,reporter); return 0
    run_forever(config,reporter,change_only=args.telegram_changes_only,hourly_analysis=args.telegram_hourly_analysis); return 0

if __name__=="__main__": raise SystemExit(main())
