from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EA = (ROOT / 'mt5/NEXUS_AutoTrade/NEXUS_AutoTrade.mq5').read_text(encoding='utf-8')
TM = (ROOT / 'mt5/NEXUS_AutoTrade/Include/TradeManager.mqh').read_text(encoding='utf-8')
RP = (ROOT / 'mt5/NEXUS_AutoTrade/Include/RiskManager.mqh').read_text(encoding='utf-8')
SP = (ROOT / 'mt5/NEXUS_AutoTrade/Include/SignalParser.mqh').read_text(encoding='utf-8')


def test_host_symbol_is_synced_and_canonicalized():
    assert 'SyncHostSymbol(true);' in EA
    assert 'CanonicalSignalSymbol(_Symbol)' in EA
    assert 'CHARTEVENT_CHART_CHANGE' in EA


def test_admin_signal_uses_correct_response_and_chart_argument_order():
    block = EA[EA.index('if(!g_api.IssueAdminSignal('):EA.index('string code=', EA.index('if(!g_api.IssueAdminSignal('))]
    assert 'reqid,\n                              response,chart_base64)' in block


def test_admin_signal_executes_the_canonical_post_response_directly():
    assert 'ParseSignalObject(issued_signal,issued)' in EA
    assert 'ProcessIncomingSignal(issued)' in EA
    assert 'stale cursor' in EA


def test_execution_has_broker_preflight_and_sizing_diagnostics():
    for token in ('TERMINAL_TRADE_ALLOWED', 'SYMBOL_TRADE_MODE', 'OrderCalcMargin', 'NEXUS MARKET PREFLIGHT'):
        assert token in TM
    assert 'risk size %.8f is below broker minimum' in RP


def test_signal_parser_can_parse_single_canonical_object():
    assert 'bool ParseSignalObject(const string obj,NexusSignal &signal)' in SP


def test_signal_workspace_has_compact_sizing_and_two_level_navigation():
    assert 'SIZING' in EA
    assert 'sig_size_risk' in EA and 'sig_size_fixed' in EA
    assert 'main_tabs[3]' in EA
    assert '"NEW SIGNAL","TRADES","SETTINGS"' in EA
    assert 'void PaintAdminTradePanel()' in EA
