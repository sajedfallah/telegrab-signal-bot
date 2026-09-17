from pathlib import Path

from app.agent_system.contracts import Direction, MarketSnapshot, SupervisorDecision, WorkflowState
from app.agent_system.orchestrator import ShadowRunResult
from app.agent_system.scanner import ScanDecision
from app.agent_system.shadow_runner import ShadowRunnerConfig, run_cycle


def _result(symbol: str) -> ShadowRunResult:
    from datetime import datetime, timezone
    s=MarketSnapshot(snapshot_id=f"shadow-{symbol}-0001",symbol=symbol,as_of=datetime(2026,9,17,tzinfo=timezone.utc),source="TEST",timeframes={},bid=100,ask=100.1,data_freshness_ms=100)
    scan=ScanDecision(state=WorkflowState.WAIT,triggers=(),blocks=())
    d=SupervisorDecision(symbol=symbol,snapshot_id=s.snapshot_id,state=WorkflowState.WAIT,direction=Direction.NEUTRAL,explanation="test")
    return ShadowRunResult(s,scan,(),d,None,d,None)


def test_shadow_runner_cycles_all_symbols_and_isolates_failures(tmp_path: Path):
    calls=[]
    def runner(account,symbol,**kwargs):
        calls.append((account,symbol,kwargs))
        if symbol=="US30":
            raise RuntimeError("feed unavailable")
        return _result(symbol)
    config=ShadowRunnerConfig(account="123",symbols=("XAUUSD","US30","BTC","SOL"),journal_dir=tmp_path)
    records=run_cycle(config,runner=runner)
    assert [x[1] for x in calls]==["XAUUSD","US30","BTC","SOL"]
    assert records[0]["final"]==WorkflowState.WAIT.value
    assert records[1]["final"]==WorkflowState.NO_TRADE.value
    assert "feed unavailable" in records[1]["error"]
    assert records[2]["symbol"]=="BTC" and records[3]["symbol"]=="SOL"


def test_shadow_runner_rejects_unsafe_fast_loop():
    try:
        ShadowRunnerConfig(account="123",interval_seconds=1)
    except ValueError as exc:
        assert "interval_seconds" in str(exc)
    else:
        raise AssertionError("expected interval validation")
