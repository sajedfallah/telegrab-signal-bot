from __future__ import annotations

import io
from pathlib import Path
from urllib.parse import urlparse

import qrcode
from qrcode.constants import ERROR_CORRECT_H
from PIL import Image, ImageDraw, ImageFont, ImageOps


def _font(size: int, bold: bool = False):
    candidates = (
        [r"C:\Windows\Fonts\segoeuib.ttf", r"C:\Windows\Fonts\arialbd.ttf"]
        if bold
        else [r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\arial.ttf"]
    ) + [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    ]
    for raw in candidates:
        path = Path(raw)
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size=size)
            except Exception:
                pass
    return ImageFont.load_default()


def validate_folder_url(url: str) -> str:
    value = str(url or "").strip()
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.netloc.lower() not in {"t.me", "telegram.me"}:
        raise ValueError("NEXUS folder URL must be an HTTPS Telegram URL")
    if not parsed.path.startswith("/addlist/"):
        raise ValueError("NEXUS folder URL must be a Telegram addlist URL")
    return value


def build_nexus_folder_qr(folder_url: str) -> bytes:
    """Generate a scan-safe NEXUS-branded QR PNG from the official folder URL."""
    folder_url = validate_folder_url(folder_url)

    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_H,
        box_size=16,
        border=4,
    )
    qr.add_data(folder_url)
    qr.make(fit=True)

    monochrome = qr.make_image(fill_color="black", back_color="white").convert("L")
    mask = ImageOps.invert(monochrome)
    w, h = monochrome.size

    # Magenta-to-blue styling based on the QR artwork supplied for the folder.
    gradient = Image.new("RGB", (w, h), "white")
    gp = gradient.load()
    top = (211, 81, 154)
    bottom = (76, 157, 245)
    for y in range(h):
        t = y / max(1, h - 1)
        color = tuple(int(top[i] * (1 - t) + bottom[i] * t) for i in range(3))
        for x in range(w):
            gp[x, y] = color

    colored_qr = Image.composite(gradient, Image.new("RGB", (w, h), "white"), mask)

    canvas = Image.new("RGB", (1080, 1080), "white")
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((28, 28, 1052, 1052), radius=58, outline=(225, 229, 236), width=4)
    draw.text((540, 70), "NEXUS", font=_font(58, True), fill=(17, 24, 39), anchor="ma")
    draw.text((540, 136), "OFFICIAL TELEGRAM ECOSYSTEM", font=_font(22, True), fill=(107, 114, 128), anchor="ma")

    max_qr = 820
    scale = min(max_qr / colored_qr.width, max_qr / colored_qr.height)
    qr_size = max(1, int(colored_qr.width * scale))
    colored_qr = colored_qr.resize((qr_size, qr_size), Image.Resampling.NEAREST)
    x = (1080 - qr_size) // 2
    y = 190
    canvas.paste(colored_qr, (x, y))

    draw.text(
        (540, 1030),
        "SCAN OR TAP ‘ENTER NEXUS’ IN THE BOT",
        font=_font(20, True),
        fill=(107, 114, 128),
        anchor="mm",
    )

    out = io.BytesIO()
    canvas.save(out, format="PNG", optimize=True)
    return out.getvalue()
