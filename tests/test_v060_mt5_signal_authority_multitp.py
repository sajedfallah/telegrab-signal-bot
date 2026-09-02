from pathlib import Path
import importlib

ROOT = Path(__file__).resolve().parents[1]
MQ = (ROOT / "mt5" / "NEXUS_AutoTrade" / "NEXUS_AutoTrade.mq5").read_text(encoding="utf-8")
API_CLIENT = (ROOT / "mt5" / "NEXUS_AutoTrade" / "Include" / "APIClient.mqh").read_text(encoding="utf-8")
TRAIL = (ROOT / "mt5" / "NEXUS_AutoTrade" / "Include" / "TrailingEngine.mqh").read_text(encoding="utf-8")
API = (ROOT / "app" / "autotrade" / "api.py").read_text(encoding="utf-8")
DB = (ROOT / "app" / "db.py").read_text(encoding="utf-8")
SERVICE = (ROOT / "app" / "autotrade" / "service.py").read_text(encoding="utf-8")

def test_admin_signal_ui_exposes_channel_selector_and_five_tps():
    for token in [
        'sig_tp1', 'sig_tp2', 'sig_tp3', 'sig_tp4', 'sig_tp5',
        'sig_dest_free', 'sig_dest_vip', 'sig_dest_both',
        'CHANNEL / ACCESS',
    ]:
        assert token in MQ

def test_admin_signal_sends_all_selected_targets_and_destination():
    assert 'targets+=DoubleToString(tps[i],8)' in MQ
    assert 'g_manual_destination' in MQ
    assert r'\"destination\"' in API_CLIENT
    assert 'destination,const string request_id' in API_CLIENT

def test_backend_preserves_destination_and_up_to_ten_targets():
    assert 'destination: str = Field(default="BOTH", pattern="^(?:FREE|VIP|BOTH)$")' in API
    assert 'targets: list[float] = Field(min_length=1, max_length=10)' in API
    assert 'destination=destination' in DB
    assert '"destination": str(row["destination"] or "BOTH").upper()' in SERVICE

def test_trailing_processes_target_ladder():
    for token in ['TargetCount', 'TargetClosePct', 'field+"_done"', 'MoveSL(ticket,pt,Target(sig,n-1))']:
        assert token in TRAIL
