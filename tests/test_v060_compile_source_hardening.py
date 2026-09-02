from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EA = (ROOT / "mt5" / "NEXUS_AutoTrade" / "NEXUS_AutoTrade.mq5").read_text(encoding="utf-8")
TRAIL = (ROOT / "mt5" / "NEXUS_AutoTrade" / "Include" / "TrailingEngine.mqh").read_text(encoding="utf-8")

def test_trailing_state_helpers_are_file_scope_not_class_static_members():
    assert "string NexusTrailPrefix(" in TRAIL
    assert "double NexusTrailGet(" in TRAIL
    assert "void NexusTrailSet(" in TRAIL
    assert "static double G(" not in TRAIL
    assert "static void S(" not in TRAIL

def test_ea_release_version_is_consistent():
    assert '#property version   "1.65"' in EA
    assert '#property version   "1.58"' not in EA
    assert 'NEXUS_EA_VERSION "0.6.5"' in EA

def test_admin_signal_panel_has_five_targets_and_channel_access():
    for token in ("sig_tp1", "sig_tp2", "sig_tp3", "sig_tp4", "sig_tp5",
                  "sig_dest_free", "sig_dest_vip", "sig_dest_both",
                  'CHANNEL / ACCESS', 'ISSUE SIGNAL'):
        assert token in EA


def test_admin_signal_rejects_zero_risk_and_can_resolve_market_entry():
    assert 'risk<=0' in EA
    assert 'g_admin_signal_order=="MARKET" && entry<=0' in EA
    assert 'SymbolInfoDouble(symbol,SYMBOL_ASK)' in EA
    assert 'SymbolInfoDouble(symbol,SYMBOL_BID)' in EA
