from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
MAIN=(ROOT/'app'/'main.py').read_text(encoding='utf-8')
UI=(ROOT/'app'/'ui.py').read_text(encoding='utf-8')
DB=(ROOT/'app'/'db.py').read_text(encoding='utf-8')
CFG=(ROOT/'app'/'config.py').read_text(encoding='utf-8')
REQ=(ROOT/'requirements.txt').read_text(encoding='utf-8')
EX=(ROOT/'app'/'autotrade'/'exchange_service.py').read_text(encoding='utf-8')

def test_transient_autotrade_notifications():
    assert '_delete_transient_notification' in MAIN
    assert 'AUTOTRADE_NOTIFICATION_TTL_SECONDS' in (ROOT/'.env.example').read_text(encoding='utf-8')
    assert 'push_home_to_bottom(bot,uid)' not in MAIN.split('async def autotrade_notification_worker',1)[1].split('async def backup_worker',1)[0]

def test_canonical_mt5_guide_path():
    block=MAIN.split('async def autotrade_video_guide',1)[1].split('async def autotrade_help',1)[0]
    assert 'assets" / "guides" / "NEXUS_AutoTrade_MT5_Guide.mp4' in block
    assert 'assets" / "autotrade" / "NEXUS_AutoTrade_Guide.mp4' not in block

def test_exchange_connection_flow_is_real_not_placeholder():
    block=MAIN.split('async def autotrade_exchange',1)[1].split('async def public_channel',1)[0]
    assert 'exchange_select:' in UI
    assert 'Flow.exchange_api_key' in block
    assert 'test_exchange_connection' in block
    assert 'encrypt_credentials' in block
    assert 'save_exchange_account' in block
    assert 'Live exchange API execution is not enabled' not in block

def test_exchange_security_and_dependencies():
    assert 'cryptography' in REQ and 'ccxt' in REQ
    assert 'EXCHANGE_CREDENTIALS_KEY' in CFG
    assert 'Fernet' in (ROOT/'app'/'autotrade'/'exchange_crypto.py').read_text(encoding='utf-8')
    assert 'fetch_balance()' in EX
    assert 'api_passphrase_enc' in DB
