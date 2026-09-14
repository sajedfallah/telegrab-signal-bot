from pathlib import Path

ROOT = Path(__file__).resolve().parent
html = (ROOT / "index.html").read_text(encoding="utf-8")
for marker in ("revenueChart", "signalDonut", "Signal Center", "Copy Trade", "Reports & Analytics", "Settings & Branding", "Telegram", "MT5"):
    assert marker in html, marker
print("provider panel visual contract: PASS")
