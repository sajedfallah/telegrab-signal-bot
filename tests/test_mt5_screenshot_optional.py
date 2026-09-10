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
    logo = Path(__file__).resolve().parents[1] / "assets" / "branding" / "NEXUS_logo_2026.jpg"
    assert logo.exists()
    assert logo.stat().st_size > 0
    source = CARD.read_text(encoding="utf-8")
    assert 'LOGO_PATH = BASE_DIR / "branding" / "NEXUS_logo_2026.jpg"' in source


def test_chart_frame_uses_new_brand_and_keeps_real_chart_pixels():
    from io import BytesIO

    from PIL import Image

    from app.signals.card_generator import build_chart_frame

    chart = Image.new("RGB", (640, 360), (123, 45, 67))
    raw = BytesIO()
    chart.save(raw, format="PNG")

    framed = Image.open(BytesIO(build_chart_frame(raw.getvalue()))).convert("RGB")

    assert framed.width > chart.width
    assert framed.height > chart.height
    # Chart starts after the 30px margin and 74px branded header.
    assert framed.getpixel((30 + 320, 74 + 30 + 180)) == (123, 45, 67)
    # New cyan identity is present in the header rule.
    assert framed.getpixel((30, 74)) == (18, 229, 205)
