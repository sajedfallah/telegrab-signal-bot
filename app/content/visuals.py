from __future__ import annotations

import io
import os
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .models import ContentDraft

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


def _draw_candles(draw: ImageDraw.ImageDraw, draft: ContentDraft, box: tuple[int, int, int, int]) -> None:
    x1, y1, x2, y2 = box
    _rounded(draw, box, 24, PANEL, BORDER, 2)
    rng = random.Random(draft.topic_slug)
    count = 25
    values = [0.45]
    for _ in range(count):
        values.append(min(0.9, max(0.12, values[-1] + rng.uniform(-0.13, 0.14))))
    step = (x2 - x1 - 60) / count
    zone_y1 = y1 + int((y2 - y1) * 0.40)
    zone_y2 = zone_y1 + 90
    draw.rounded_rectangle((x1 + 35, zone_y1, x2 - 35, zone_y2), 10, fill=(58, 67, 69), outline=GOLD, width=2)
    draw.text((x1 + 55, zone_y1 + 25), "ICT / PD ARRAY", font=_font(24, True), fill=TEXT)
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


def render_post_card(draft: ContentDraft) -> bytes:
    image = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(image)

    draw.text((56, 44), "NEXUS", font=_font(58, True), fill=TEXT)
    draw.text((58, 108), "TRADE SMARTER", font=_font(19, True), fill=MUTED)
    draw.line((56, 146, W - 56, 146), fill=BORDER, width=2)
    _rounded(draw, (W - 330, 50, W - 58, 118), 16, (11, 34, 52), BORDER, 2)
    _right_text(draw, (W - 82, 68), draft.kicker, _font(29, True), GOLD)

    _right_text(draw, (W - 58, 190), draft.title, _font(52, True), TEXT)
    draw.text((58, 204), "ICT EDUCATION · DAILY SERIES", font=_font(20, True), fill=BLUE)

    _draw_candles(draw, draft, (56, 280, W - 56, 690))

    _rounded(draw, (56, 726, W - 56, 910), 22, (8, 30, 47), BORDER, 2)
    _right_text(draw, (W - 86, 752), "تعریف ساده", _font(27, True), GOLD)
    y = 802
    for line in _wrap(draw, draft.definition, _font(29), W - 160, 3):
        _right_text(draw, (W - 86, y), line, _font(29), TEXT)
        y += 42

    _right_text(draw, (W - 58, 952), "نکات کلیدی", _font(30, True), BLUE)
    y = 1000
    for point in draft.key_points[:4]:
        draw.ellipse((W - 92, y + 8, W - 70, y + 30), fill=GREEN)
        for line in _wrap(draw, point, _font(25), W - 170, 1):
            _right_text(draw, (W - 110, y), line, _font(25), TEXT)
        y += 57

    draw.line((56, 1258, W - 56, 1258), fill=BORDER, width=2)
    draw.text((56, 1282), "NEXUS  |  EDUCATE · EMPOWER · GROW TOGETHER", font=_font(20, True), fill=MUTED)
    draw.text((W - 60, 1280), "NEXUS", font=_font(26, True), fill=TEXT, anchor="ra")

    out = io.BytesIO()
    image.save(out, format="PNG", optimize=True)
    return out.getvalue()
