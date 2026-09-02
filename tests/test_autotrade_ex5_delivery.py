from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_current_mt5_source_is_packaged_and_compile_is_explicit():
    src = ROOT / "mt5" / "NEXUS_AutoTrade" / "NEXUS_AutoTrade.mq5"
    note = ROOT / "MT5_COMPILE_REQUIRED.md"
    assert src.is_file() and src.stat().st_size > 0
    assert note.is_file() and note.stat().st_size > 0
    assert '#property version   "1.65"' in src.read_text(encoding="utf-8")


def test_license_delivery_sends_ex5_guide_then_home():
    src = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    start = src.index("async def send_autotrade_license")
    end = src.index("async def send_license_link", start)
    block = src[start:end]
    assert "bot.send_document" in block
    assert 'filename="NEXUS_AutoTrade.ex5"' in block
    assert "آموزش نصب NEXUS معاملات خودکار" in block
    assert "await push_home_to_bottom" in block
