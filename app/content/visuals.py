from __future__ import annotations

import io
import os
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .models import ContentDraft
from .taxonomy import category

try:
    import arabic_reshaper  # type: ignore
    from bidi.algorithm import get_display  # type: ignore
except Exception:
    arabic_reshaper = None
    get_display = None


W, H = 1080, 1350
BG = (4, 16, 27)
PANEL = (7, 25, 40)
TEXT = (238, 244, 249)
MUTED = (142, 163, 181)
BLUE = (77, 162, 255)
GOLD = (236, 183, 99)
GREEN = (68, 199, 130)
RED = (226, 83, 88)
BORDER = (42, 83, 112)

_CATEGORY_ACCENTS = {
    "ict_education": GOLD,
    "daily_analysis": BLUE,
    "quick_tip": (113, 207, 255),
    "market_news": (107, 174, 255),
    "important_news": RED,
    "news_alert": (244, 164, 74),
    "tools": (93, 198, 186),
    "risk": GREEN,
    "trade_review": (151, 128, 255),
    "mindset": (223, 151, 255),
}


def _font_candidates(bold: bool = False) -> list[str]:
    custom = os.getenv("CONTENT_FONT_BOLD_PATH" if bold else "CONTENT_FONT_PATH", "").strip()
    paths = [custom] if custom else []
    if bold:
        paths += [
            r"C:\Windows\Fonts\arialbd.ttf",
            r"C:\Windows\Fonts\segoeuib.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]
    else:
        paths += [
            r"C:\Windows\Fonts\arial.ttf",
            r"C:\Windows\Fonts\segoeui.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
    return [path for path in paths if path]


def _font(size: int, bold: bool = False):
    for path in _font_candidates(bold):
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:
                pass
    return ImageFont.load_default()


def _rtl(text: str) -> str:
    if arabic_reshaper and get_display:
        try:
            return get_display(arabic_reshaper.reshape(text))
        except Exception:
            return text
    return text


def _measure(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    box = draw.textbbox((0, 0), _rtl(text), font=font)
    return max(0, box[2] - box[0])


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int, max_lines: int) -> list[str]:
    words = str(text).split()
    lines: list[str] = []
    current = ""
    for word in words:
        test = (current + " " + word).strip()
        if not current or _measure(draw, test, font) <= max_width:
            current = test
        else:
            lines.append(current)
            current = word
            if len(lines) >= max_lines - 1:
                break
    if current and len(lines) < max_lines:
        lines.append(current)
    return lines


def _right_text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, font, fill=TEXT):
    draw.text(xy, _rtl(text), font=font, fill=fill, anchor="ra")


def _rounded(draw: ImageDraw.ImageDraw, box, radius: int, fill, outline=None, width: int = 1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def _load_logo() -> Image.Image | None:
    logo_path = Path(__file__).resolve().parents[2] / "assets" / "branding" / "NEXUS_logo.png"
    if not logo_path.exists():
        return None
    try:
        logo = Image.open(logo_path).convert("RGBA")
        logo.thumbnail((138, 78), Image.Resampling.LANCZOS)
        return logo
    except Exception:
        return None


def _draw_candles(draw: ImageDraw.ImageDraw, draft: ContentDraft, box: tuple[int, int, int, int], accent) -> None:
    x1, y1, x2, y2 = box
    _rounded(draw, box, 24, PANEL, BORDER, 2)
    rng = random.Random(draft.topic_slug)
    count = 31
    values = [0.45]
    for _ in range(count):
        values.append(min(0.9, max(0.12, values[-1] + rng.uniform(-0.13, 0.14))))
    step = (x2 - x1 - 70) / count
    zone_y1 = y1 + int((y2 - y1) * 0.42)
    zone_y2 = zone_y1 + 100
    draw.rounded_rectangle(
        (x1 + 35, zone_y1, x2 - 35, zone_y2),
        12,
        fill=(45, 58, 67),
        outline=accent,
        width=3,
    )
    draw.text((x1 + 55, zone_y1 + 30), "ICT / PD ARRAY", font=_font(23, True), fill=TEXT)
    for i in range(count):
        opened = values[i]
        closed = values[i + 1]
        high = min(0.97, max(opened, closed) + rng.uniform(0.02, 0.09))
        low = max(0.05, min(opened, closed) - rng.uniform(0.02, 0.08))
        cx = x1 + 35 + i * step
        yy = lambda value: y2 - 35 - value * (y2 - y1 - 70)
        color = GREEN if closed >= opened else RED
        draw.line((cx, yy(high), cx, yy(low)), fill=color, width=2)
        top, bottom = sorted((yy(opened), yy(closed)))
        if bottom - top < 4:
            bottom = top + 4
        draw.rectangle((cx - 6, top, cx + 6, bottom), fill=color)


def _paste_hero(image: Image.Image, draft: ContentDraft, hero_bytes: bytes | None, box, accent) -> None:
    x1, y1, x2, y2 = box
    if not hero_bytes:
        _draw_candles(ImageDraw.Draw(image), draft, box, accent)
        return
    try:
        hero = Image.open(io.BytesIO(hero_bytes)).convert("RGB")
        fitted = ImageOps.fit(hero, (x2 - x1, y2 - y1), method=Image.Resampling.LANCZOS)
        image.paste(fitted, (x1, y1))
        overlay = Image.new("RGBA", (x2 - x1, y2 - y1), (0, 0, 0, 0))
        odraw = ImageDraw.Draw(overlay)
        odraw.rectangle((0, 0, x2 - x1, y2 - y1), fill=(3, 12, 21, 66))
        for index in range(130):
            alpha = int(190 * index / 129)
            odraw.line((0, y2 - y1 - 130 + index, x2 - x1, y2 - y1 - 130 + index), fill=(3, 12, 21, alpha))
        hero_rgba = image.crop((x1, y1, x2, y2)).convert("RGBA")
        hero_rgba.alpha_composite(overlay)
        image.paste(hero_rgba.convert("RGB"), (x1, y1))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle(box, radius=24, outline=accent, width=3)
        motif = str(draft.metadata.get("visual_motif") or "NEXUS MARKET CONCEPT")
        draw.rounded_rectangle((x1 + 28, y2 - 86, min(x2 - 28, x1 + 710), y2 - 28), 14, fill=(3, 16, 27), outline=accent, width=2)
        draw.text((x1 + 48, y2 - 69), motif[:62].upper(), font=_font(19, True), fill=TEXT)
    except Exception:
        _draw_candles(ImageDraw.Draw(image), draft, box, accent)


def render_post_card(draft: ContentDraft, hero_image_bytes: bytes | None = None) -> bytes:
    image = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(image)
    cat = category(draft.category_key)
    accent = _CATEGORY_ACCENTS.get(draft.category_key, GOLD)

    # Header / permanent NEXUS identity.
    logo = _load_logo()
    if logo is not None:
        image.paste(logo, (48, 36), logo)
    else:
        draw.text((56, 44), "NEXUS", font=_font(58, True), fill=TEXT)
    draw.text((58, 116), "TRADE SMARTER", font=_font(18, True), fill=MUTED)
    draw.line((56, 154, W - 56, 154), fill=BORDER, width=2)

    chip_width = 310
    _rounded(draw, (W - chip_width - 58, 48, W - 58, 120), 18, (11, 34, 52), accent, 2)
    _right_text(draw, (W - 82, 67), f"{cat.emoji} {cat.label_fa}", _font(28, True), accent)

    # Title area.
    title_font = _font(49, True)
    title_lines = _wrap(draw, draft.title, title_font, W - 118, 2)
    y = 188
    for line in title_lines:
        _right_text(draw, (W - 58, y), line, title_font, TEXT)
        y += 58
    draw.text((58, 215), "NEXUS EDITORIAL · VERIFIED FORMAT", font=_font(18, True), fill=accent)

    hero_box = (56, 300, W - 56, 760)
    _paste_hero(image, draft, hero_image_bytes, hero_box, accent)
    draw = ImageDraw.Draw(image)

    # Definition card.
    _rounded(draw, (56, 792, W - 56, 978), 22, (8, 30, 47), BORDER, 2)
    _right_text(draw, (W - 86, 818), "تعریف ساده", _font(27, True), accent)
    y = 868
    for line in _wrap(draw, draft.definition, _font(27), W - 160, 3):
        _right_text(draw, (W - 86, y), line, _font(27), TEXT)
        y += 39

    # Key points.
    _right_text(draw, (W - 58, 1012), "نکات کلیدی", _font(29, True), accent)
    y = 1058
    for point in draft.key_points[:3]:
        draw.ellipse((W - 91, y + 8, W - 71, y + 28), fill=accent)
        lines = _wrap(draw, point, _font(24), W - 174, 1)
        if lines:
            _right_text(draw, (W - 110, y), lines[0], _font(24), TEXT)
        y += 55

    # Footer / traceability.
    draw.line((56, 1248, W - 56, 1248), fill=BORDER, width=2)
    draw.text((56, 1273), "NEXUS · EDUCATE · EMPOWER · GROW TOGETHER", font=_font(18, True), fill=MUTED)
    if draft.post_id:
        draw.text((W - 58, 1274), draft.post_id[:38], font=_font(18, True), fill=accent, anchor="ra")

    out = io.BytesIO()
    image.save(out, format="PNG", optimize=True)
    return out.getvalue()
