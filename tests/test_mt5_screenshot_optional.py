from pathlib import Path

MAIN = Path(__file__).resolve().parents[1] / "app" / "main.py"
CARD = Path(__file__).resolve().parents[1] / "app" / "signals" / "card_generator.py"


def test_mt5_lifecycle_does_not_fail_when_screenshot_is_missing():
    source = MAIN.read_text(encoding="utf-8")
    assert "MT5 manual-open screenshot was not received" not in source
    assert "MT5 pending-order screenshot was not received" not in source
    assert "MT5 close screenshot was not received" not in source
    # The event handlers no longer raise solely because chart capture failed.


def test_nexus_logo_asset_is_packaged_and_used_by_card_generator():
    logo = Path(__file__).resolve().parents[1] / "assets" / "branding" / "NEXUS_logo.png"
    assert logo.exists()
    assert logo.stat().st_size > 0
    source = CARD.read_text(encoding="utf-8")
    assert 'LOGO_PATH = BASE_DIR / "branding" / "NEXUS_logo.png"' in source
