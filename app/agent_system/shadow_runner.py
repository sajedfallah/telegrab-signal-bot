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
from .telegram_reporter import TelegramShadowReporter, format_shadow_record


DEFAULT_SYMBOLS = ("XAUUSD", "US30", "BTC", "SOL")


@dataclass(frozen=True)
class ShadowRunnerConfig:
    account: str
    symbols: tuple[str, ...] = DEFAULT_SYMBOLS
    interval_seconds: int = 60
    journal_dir: Path = Path("data/agent_shadow")
    risk_policy: RiskPolicy | None = None

    def __post_init__(self) -> None:
        if not self.account.strip():
            raise ValueError("account is required")
        if not self.symbols:
            raise ValueError("at least one symbol is required")
        if self.interval_seconds < 5:
            raise ValueError("interval_seconds must be >= 5")


def _journal_path(root: Path, symbol: str, now: datetime | None = None) -> Path:
    day = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d")
    safe_symbol = "".join(ch for ch in symbol.upper() if ch.isalnum() or ch in {"-", "_"})
    return root / safe_symbol / f"{day}.jsonl"


def _summary(result: ShadowRunResult) -> dict[str, object]:
    return {
        "symbol": result.initial_snapshot.symbol,
        "snapshot_id": result.initial_snapshot.snapshot_id,
        "scan": result.scan.state.value,
        "supervisor": result.supervisor.state.value,
        "final": result.final_decision.state.value,
        "direction": result.final_decision.direction.value if result.final_decision.direction else None,
        "risk_allowed": result.risk.allowed if result.risk else None,
        "risk_blocks": list(result.risk.hard_blocks) if result.risk else [],
    }


def run_cycle(
    config: ShadowRunnerConfig,
    *,
    runner: Callable[..., ShadowRunResult] = run_shadow,
) -> tuple[dict[str, object], ...]:
    """Run one read-only observation cycle for all configured symbols."""
    output: list[dict[str, object]] = []
    for symbol in config.symbols:
        try:
            result = runner(
                config.account,
                symbol,
                risk_policy=config.risk_policy,
                journal_path=_journal_path(config.journal_dir, symbol),
            )
            output.append(_summary(result))
        except Exception as exc:
            output.append({"symbol": symbol, "final": WorkflowState.NO_TRADE.value, "error": f"{type(exc).__name__}: {exc}"})
    return tuple(output)


def _report_records(records: tuple[dict[str, object], ...], reporter: TelegramShadowReporter | None) -> None:
    if reporter is None:
        return
    for record in records:
        try:
            reporter.send_text(format_shadow_record(record))
        except Exception as exc:
            # Telegram reporting is non-authoritative. A reporting outage must
            # never change market decisions or create an execution path.
            print(json.dumps({"telegram_report_error": f"{type(exc).__name__}: {exc}", "symbol": record.get("symbol")}, ensure_ascii=False))


def run_forever(config: ShadowRunnerConfig, reporter: TelegramShadowReporter | None = None) -> None:
    while True:
        records = run_cycle(config)
        print(json.dumps({"at": datetime.now(timezone.utc).isoformat(), "records": records}, ensure_ascii=False))
        _report_records(records, reporter)
        time.sleep(config.interval_seconds)


def _symbols(value: str) -> tuple[str, ...]:
    items = tuple(dict.fromkeys(x.strip().upper() for x in value.split(",") if x.strip()))
    if not items:
        raise argparse.ArgumentTypeError("symbols cannot be empty")
    return items


def _reporter_from_env(enabled: bool) -> TelegramShadowReporter | None:
    if not enabled:
        return None
    token = os.getenv("NEXUS_AGENT_TEST_BOT_TOKEN", "").strip()
    chat_id = os.getenv("NEXUS_AGENT_TEST_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise RuntimeError("Telegram test reporting requires NEXUS_AGENT_TEST_BOT_TOKEN and NEXUS_AGENT_TEST_CHAT_ID")
    return TelegramShadowReporter(token, chat_id)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="NEXUS Agent System V1 observation-only shadow runner")
    parser.add_argument("--account", required=True, help="Existing MT5 market-feed account number")
    parser.add_argument("--symbols", type=_symbols, default=DEFAULT_SYMBOLS, help="Comma-separated canonical symbols")
    parser.add_argument("--interval", type=int, default=60, help="Seconds between observation cycles")
    parser.add_argument("--journal-dir", default="data/agent_shadow", help="Isolated JSONL journal root")
    parser.add_argument("--once", action="store_true", help="Run one observation cycle and exit")
    parser.add_argument("--telegram", action="store_true", help="Send observation results only to the isolated Agent Test Bot")
    args = parser.parse_args(list(argv) if argv is not None else None)

    config = ShadowRunnerConfig(account=args.account, symbols=args.symbols, interval_seconds=args.interval, journal_dir=Path(args.journal_dir), risk_policy=None)
    reporter = _reporter_from_env(args.telegram)
    if args.once:
        records = run_cycle(config)
        print(json.dumps({"at": datetime.now(timezone.utc).isoformat(), "records": records}, ensure_ascii=False))
        _report_records(records, reporter)
        return 0
    run_forever(config, reporter)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
