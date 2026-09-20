import json
from pathlib import Path

def _fresh_db(monkeypatch, tmp_path):
    from app import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "obs.db")
    db.init_db()
    db.upsert_user(1001, "obs", "Observer")
    return db

def _signal(db):
    return db.create_signal(
        market_type="FOREX", symbol="XAUUSD", direction="BUY", entry_price=2500,
        stop_loss=2490, targets=[2520], risk_percent=1, rr_ratio=2,
        destination="VIP", chart_file_id=None, created_by=1001,
    )

def test_observation_is_idempotent_and_snapshot_is_immutable(monkeypatch, tmp_path):
    db=_fresh_db(monkeypatch,tmp_path); sig=_signal(db)
    first=db.upsert_autotrade_observation(1001,sig["id"],"ACC-1",broker="Demo",ea_version="0.6.5",
        config_snapshot={"risk_percent":1.0},decision_status="RECEIVED")
    second=db.upsert_autotrade_observation(1001,sig["id"],"ACC-1",decision_status="REJECTED",
        reason_code="ENTRY_DEVIATION",reason_detail="too far",config_snapshot={"risk_percent":9.0})
    assert first["id"]==second["id"]
    assert second["decision_status"]=="REJECTED"
    assert second["reason_code"]=="ENTRY_DEVIATION"
    assert json.loads(second["config_snapshot_json"])["risk_percent"]==1.0

def test_same_signal_can_have_multiple_account_observations(monkeypatch,tmp_path):
    db=_fresh_db(monkeypatch,tmp_path); sig=_signal(db)
    a=db.upsert_autotrade_observation(1001,sig["id"],"ACC-A")
    b=db.upsert_autotrade_observation(1001,sig["id"],"ACC-B")
    assert a["id"] != b["id"]

def test_execution_attempt_is_idempotent_and_keeps_telemetry(monkeypatch,tmp_path):
    db=_fresh_db(monkeypatch,tmp_path); sig=_signal(db)
    obs=db.upsert_autotrade_observation(1001,sig["id"],"ACC-1")
    a=db.add_autotrade_execution_attempt(obs["id"],attempt_no=1,requested_price=2500,market_bid=2500.1,
        market_ask=2500.3,spread=0.2,requested_volume=0.1,status="ATTEMPTED")
    b=db.add_autotrade_execution_attempt(obs["id"],attempt_no=1,executed_price=2500.4,executed_volume=0.1,
        slippage=0.4,latency_ms=83,status="EXECUTED")
    assert a["id"]==b["id"]
    assert b["status"]=="EXECUTED"
    assert b["slippage"]==0.4
    assert b["latency_ms"]==83

def test_unknown_reason_is_normalized(monkeypatch,tmp_path):
    db=_fresh_db(monkeypatch,tmp_path); sig=_signal(db)
    obs=db.upsert_autotrade_observation(1001,sig["id"],"ACC-1",decision_status="REJECTED",
        reason_code="some broker prose",reason_detail="raw diagnostic")
    assert obs["reason_code"]=="UNKNOWN"
    assert obs["reason_detail"]=="raw diagnostic"

def test_release_a_schema_contains_lifecycle_metric_columns(monkeypatch,tmp_path):
    db=_fresh_db(monkeypatch,tmp_path)
    with db.conn() as con:
        cols={r[1] for r in con.execute("PRAGMA table_info(autotrade_trade_executions)").fetchall()}
    required={"observation_id","attempt_id","event_subtype","event_time_ms","remaining_volume",
              "sl_before","sl_after","tp_before","tp_after","spread","latency_ms",
              "mfe_price","mae_price","mfe_r","mae_r","config_snapshot_json"}
    assert required <= cols

def test_release_a_api_contract_is_present():
    root=Path(__file__).resolve().parents[1]
    api=(root/"app/autotrade/api.py").read_text(encoding="utf-8")
    assert '/api/v1/autotrade/observation' in api
    assert '/api/v1/autotrade/execution-attempt' in api
    assert "ObservationRequest" in api and "ExecutionAttemptRequest" in api


def test_mt5_observation_is_non_blocking_to_execution_path():
    root=Path(__file__).resolve().parents[1]
    ea=(root/"mt5/NEXUS_AutoTrade/NEXUS_AutoTrade.mq5").read_text(encoding="utf-8")
    # Release A telemetry must not introduce a synchronous HTTP request before
    # ValidateEntry/OpenSignal, otherwise an observability outage can delay trading.
    start=ea.index("bool ProcessIncomingSignal")
    end=ea.index("void PollSignals", start)
    flow=ea[start:end]
    first_observe=flow.find("ObserveSignal(")
    open_call=flow.find("g_trade.OpenSignal(")
    assert first_observe == -1 or first_observe > open_call

def test_mt5_emits_execution_attempt_telemetry():
    root=Path(__file__).resolve().parents[1]
    ea=(root/"mt5/NEXUS_AutoTrade/NEXUS_AutoTrade.mq5").read_text(encoding="utf-8")
    api=(root/"mt5/NEXUS_AutoTrade/Include/APIClient.mqh").read_text(encoding="utf-8")
    assert "ExecutionAttempt(" in api
    assert "g_api.ExecutionAttempt(" in ea
    assert "QueueExecutionAttempt(" in ea

def test_mt5_populates_release_a_trade_metrics():
    root=Path(__file__).resolve().parents[1]
    ea=(root/"mt5/NEXUS_AutoTrade/NEXUS_AutoTrade.mq5").read_text(encoding="utf-8")
    required=("latency_ms","mfe_r","mae_r","remaining_volume","sl_before","sl_after","tp_before","tp_after")
    for token in required:
        assert token in ea, f"MT5 does not emit {token}"


def test_execution_attempt_contract_supports_exact_signal_linkage():
    root=Path(__file__).resolve().parents[1]
    api=(root/"app/autotrade/api.py").read_text(encoding="utf-8")
    client=(root/"mt5/NEXUS_AutoTrade/Include/APIClient.mqh").read_text(encoding="utf-8")
    assert "signal_db_id: int | None" in api
    assert "WHERE telegram_id=? AND signal_id=? AND account_number=?" in api
    assert '\"signal_db_id\":%I64d' in client

def test_observation_queue_is_fifo_and_position_state_tracks_excursions():
    root=Path(__file__).resolve().parents[1]
    ea=(root/"mt5/NEXUS_AutoTrade/NEXUS_AutoTrade.mq5").read_text(encoding="utf-8")
    assert "while(i<ArraySize(g_pending_observations))" in ea
    assert "double mfe_price;" in ea
    assert "double mae_price;" in ea


def test_execution_attempt_captures_volume_and_broker_retcode():
    root=Path(__file__).resolve().parents[1]
    manager=(root/"mt5/NEXUS_AutoTrade/Include/TradeManager.mqh").read_text(encoding="utf-8")
    ea=(root/"mt5/NEXUS_AutoTrade/NEXUS_AutoTrade.mq5").read_text(encoding="utf-8")
    assert "LastRequestedVolume()" in manager
    assert "LastRetcode()" in manager
    assert "g_trade.LastRequestedVolume()" in ea
    assert "g_trade.LastRetcode()" in ea
