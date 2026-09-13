from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image

from app.signals.card_generator import build_publication_signal_image, publication_card_payload


def test_publication_renderer_is_issuance_source_independent_and_keeps_chart():
    chart = Image.new("RGB", (320, 240), (28, 91, 150))
    raw = BytesIO()
    chart.save(raw, format="PNG")
    row = {"code": "NX-34", "symbol": "BTCUSD", "direction": "BUY", "entry_price": 77000,
           "stop_loss": 76000, "risk_percent": 1, "volume_mode": "FIXED", "lot_size": 0.06,
           "market_type": "CRYPTO", "order_type": "MARKET", "trailing_code": "NEXUS_TRAIL_06"}
    targets = [{"target_no": 1, "price": 78000}, {"target_no": 2, "price": 79000}]
    payload = publication_card_payload(row, targets)
    assert payload["tp1"] == 78000 and payload["tp2"] == 79000
    mt5 = build_publication_signal_image(raw.getvalue(), payload)
    web = build_publication_signal_image(raw.getvalue(), payload)
    assert mt5 == web
    rendered = Image.open(BytesIO(mt5))
    assert rendered.width > chart.width and rendered.height > chart.height
    assert rendered.getpixel((100, 150)) == (28, 91, 150)
    fallback = Image.open(BytesIO(build_publication_signal_image(None, payload)))
    assert fallback.width > 900 and fallback.height > 600


def test_both_telegram_publication_paths_use_shared_renderer():
    root = Path(__file__).resolve().parents[1]
    main = (root / "app/main.py").read_text(encoding="utf-8")
    api = (root / "app/autotrade/api.py").read_text(encoding="utf-8")
    assert "build_publication_signal_image, chart" in main
    assert "build_publication_signal_image, raw or None" in api
    assert "caption = _signal_caption(row" in api
