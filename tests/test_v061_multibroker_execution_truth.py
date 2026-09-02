from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_admin_signal_publication_is_gated_by_mt5_receipt():
    src = (ROOT / "app" / "autotrade" / "api.py").read_text(encoding="utf-8")
    endpoint = src[src.index('async def issue_mt5_admin_signal'):src.index('@app.post("/api/v1/admin/mt5/signals/{signal_id}/command")')]
    assert "background_tasks.add_task(_publish_mt5_admin_signal_async, row, req.chart_base64)" not in endpoint
    assert "WAITING_EXECUTION" in endpoint
    receipt_start = src.index('@app.post("/api/v1/autotrade/signal-receipt")')
    receipt = src[receipt_start:src.index('@app.post("/api/v1/autotrade/command-receipt")', receipt_start)]
    assert 'accepted = str(req.status).lower() in {"executed", "pending"}' in receipt
    assert 'background_tasks.add_task(_publish_mt5_admin_signal_async, row, None)' in receipt
    assert 'req.status' in receipt


def test_rejected_receipt_is_not_publication_trigger():
    src = (ROOT / "app" / "autotrade" / "api.py").read_text(encoding="utf-8")
    receipt_start = src.index('@app.post("/api/v1/autotrade/signal-receipt")')
    receipt = src[receipt_start:src.index('@app.post("/api/v1/autotrade/command-receipt")', receipt_start)]
    trigger_line = 'if accepted and is_authority:'
    assert trigger_line in receipt
    trigger = receipt[receipt.index(trigger_line):]
    assert '"rejected"' not in trigger.split('return {', 1)[0]


def test_symbol_mapper_scans_all_terminal_symbols_and_rejects_ambiguity():
    src = (ROOT / "mt5" / "NEXUS_AutoTrade" / "Include" / "SymbolMapper.mqh").read_text(encoding="utf-8")
    assert 'SymbolsTotal(false)' in src
    assert 'SymbolName(i,false)' in src
    assert 'best_matches' in src
    assert 'if(best=="" || best_matches>1)' in src


def test_mt5_broker_capability_panel_exposes_native_contract():
    src = (ROOT / "mt5" / "NEXUS_AutoTrade" / "NEXUS_AutoTrade.mq5").read_text(encoding="utf-8")
    for token in ("SYMBOL_TRADE_MODE", "SYMBOL_ORDER_MODE", "SYMBOL_FILLING_MODE", "SYMBOL_TRADE_TICK_SIZE", "SYMBOL_TRADE_TICK_VALUE", "SYMBOL_VOLUME_MIN", "SYMBOL_VOLUME_STEP", "SYMBOL_VOLUME_MAX", "SYMBOL_TRADE_STOPS_LEVEL", "SYMBOL_TRADE_FREEZE_LEVEL"):
        assert token in src
    assert "EXEC SYMBOL" in src
    assert "CANON" in src


def test_live_admin_signal_center_uses_authoritative_receipt_and_trade_state():
    src = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    assert 'async def _render_admin_signal_center' in src
    assert 'db.mt5_signal_live_state' in src
    assert 'signal_refresh' in src
    assert 'MT5 Live Center' in src


def test_fresh_db_release_has_reset_script_and_no_runtime_db():
    assert (ROOT / "RESET_VNEXT_DB.bat").exists()
    assert not (ROOT / "nexus_bot.db").exists()
