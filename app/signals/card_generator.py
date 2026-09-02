from __future__ import annotations

from functools import lru_cache
from io import BytesIO
from pathlib import Path
import os

from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASE_DIR = PROJECT_ROOT / "assets"
LOGO_PATH = BASE_DIR / "branding" / "NEXUS_logo.png"

W, H = 1080, 1600
BG = (7, 8, 10)
PANEL = (18, 20, 25)
LINE = (55, 58, 66)
TEXT = (245, 247, 250)
MUTED = (170, 178, 190)
ACCENT = (65, 214, 157)
DANGER = (255, 96, 108)
GOLD = (220, 171, 52)
BLUE = (73, 170, 255)
PURPLE = (190, 120, 255)
ORANGE = (255, 158, 55)


@lru_cache(maxsize=1)
def _b_yekan_path() -> str | None:
    """Locate B Yekan without bundling/distributing the font file.

    On Windows Server the preferred location is C:\\Windows\\Fonts. User-installed
    fonts under LOCALAPPDATA are also supported. The project intentionally does not
    ship font binaries.
    """
    configured = os.environ.get("REPORT_FA_FONT_PATH", "").strip()
    if configured:
        configured_path = Path(configured)
        if configured_path.exists():
            return str(configured_path)

    candidates = [
        Path(r"C:\Windows\Fonts\BYekan.ttf"),
        Path(r"C:\Windows\Fonts\B Yekan.ttf"),
        Path(r"C:\Windows\Fonts\B_Yekan.ttf"),
        Path(r"C:\Windows\Fonts\B-Yekan.ttf"),
    ]
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates += [
            Path(local) / "Microsoft" / "Windows" / "Fonts" / "BYekan.ttf",
            Path(local) / "Microsoft" / "Windows" / "Fonts" / "B Yekan.ttf",
        ]
    for p in candidates:
        if p.exists():
            return str(p)

    # Font filenames vary by installer. Scan only the normal Windows font dirs.
    dirs = [Path(r"C:\Windows\Fonts")]
    if local:
        dirs.append(Path(local) / "Microsoft" / "Windows" / "Fonts")
    for folder in dirs:
        try:
            for p in folder.iterdir():
                if not p.is_file() or p.suffix.lower() not in {".ttf", ".otf"}:
                    continue
                normalized = p.stem.lower().replace(" ", "").replace("_", "").replace("-", "")
                if "byekan" in normalized:
                    return str(p)
        except Exception:
            continue
    return None


@lru_cache(maxsize=128)
def _font(size: int, bold: bool = False, fa: bool = False):
    candidates: list[str] = []
    if fa:
        yekan = _b_yekan_path()
        if yekan:
            candidates.append(yekan)
    if bold:
        candidates += [
            r"C:\Windows\Fonts\arialbd.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]
    candidates += [
        r"C:\Windows\Fonts\arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for p in candidates:
        try:
            if Path(p).exists():
                return ImageFont.truetype(p, size=size)
        except Exception:
            pass
    return ImageFont.load_default()


def _text(draw: ImageDraw.ImageDraw, xy, text: str, size: int, *, bold=False, fill=TEXT,
          anchor=None, fa: bool = False):
    kwargs = dict(font=_font(size, bold, fa), fill=fill, anchor=anchor)
    if fa:
        # Pillow 11.x Windows wheels normally include libraqm. If unavailable, keep
        # rendering instead of crashing; the deployment README explains the font check.
        try:
            draw.text(xy, str(text), direction="rtl", language="fa", **kwargs)
            return
        except Exception:
            pass
    draw.text(xy, str(text), **kwargs)


def _fit_text(draw: ImageDraw.ImageDraw, text: str, max_width: int, start_size: int, *,
              bold=False, fa=False, min_size=16):
    size = start_size
    while size > min_size:
        f = _font(size, bold, fa)
        try:
            bbox = draw.textbbox((0, 0), str(text), font=f, direction="rtl" if fa else None, language="fa" if fa else None)
        except Exception:
            bbox = draw.textbbox((0, 0), str(text), font=f)
        if bbox[2] - bbox[0] <= max_width:
            return f, size
        size -= 1
    return _font(min_size, bold, fa), min_size


def _open_logo() -> Image.Image | None:
    """Load the NEXUS logo, with a deterministic branded fallback.

    The deployment ZIP may not contain a binary logo asset. In that case we
    still render a visible NEXUS brand mark instead of silently returning no
    logo and publishing a raw chart.
    """
    try:
        if LOGO_PATH.exists():
            return Image.open(LOGO_PATH).convert("RGBA")
    except Exception:
        pass

    # Vector fallback: no external asset, font or network dependency.
    w, h = 720, 360
    logo = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(logo)
    gold = (220, 171, 52, 255)
    white = (245, 247, 250, 255)
    d.rounded_rectangle((12, 12, w - 12, h - 12), radius=42, outline=gold, width=6)
    # Stylized N / market arrow.
    d.line((100, 250, 100, 105, 205, 250, 205, 105), fill=gold, width=22, joint="curve")
    d.line((235, 250, 330, 105, 425, 250), fill=gold, width=22, joint="curve")
    d.polygon([(470, 225), (610, 115), (610, 165), (650, 165), (650, 80), (565, 80),
               (565, 115), (470, 190)], fill=gold)
    f = _font(72, True, False)
    d.text((92, 265), "NEXUS", font=f, fill=white, anchor="la")
    return logo


def _paste_logo(canvas: Image.Image, box: tuple[int, int, int, int]) -> None:
    logo = _open_logo()
    if logo is None:
        return
    x1, y1, x2, y2 = box
    max_w, max_h = max(1, x2 - x1), max(1, y2 - y1)
    logo.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
    x = x1 + (max_w - logo.width) // 2
    y = y1 + (max_h - logo.height) // 2
    canvas.paste(logo, (x, y), logo)


def _load_chart(raw: bytes | None) -> Image.Image:
    if not raw:
        return Image.new("RGB", (900, 600), (12, 12, 12))
    try:
        return Image.open(BytesIO(raw)).convert("RGB")
    except Exception:
        return Image.new("RGB", (900, 600), (12, 12, 12))


def build_chart_frame(chart_bytes: bytes | None) -> bytes:
    """Simple NEXUS chart frame. The chart is contained, never cropped."""
    chart = _load_chart(chart_bytes)
    max_chart_w, max_chart_h = 1280, 900
    scale = min(max_chart_w / chart.width, max_chart_h / chart.height, 1.0)
    if scale != 1.0:
        chart = chart.resize(
            (max(1, int(chart.width * scale)), max(1, int(chart.height * scale))),
            Image.Resampling.LANCZOS,
        )

    side_w = 260
    margin = 36
    chart_border = 3
    canvas_w = chart.width + side_w + margin * 3
    canvas_h = max(chart.height + margin * 2, 640)
    canvas = Image.new("RGB", (canvas_w, canvas_h), (0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    chart_x = margin
    chart_y = (canvas_h - chart.height) // 2
    draw.rectangle(
        (
            chart_x - chart_border,
            chart_y - chart_border,
            chart_x + chart.width + chart_border,
            chart_y + chart.height + chart_border,
        ),
        outline=(55, 55, 55),
        width=chart_border,
    )
    canvas.paste(chart, (chart_x, chart_y))

    logo_x1 = chart_x + chart.width + margin
    _paste_logo(canvas, (logo_x1, margin, canvas_w - margin, canvas_h - margin))

    out = BytesIO()
    canvas.save(out, format="PNG", optimize=True)
    return out.getvalue()


def _row(draw: ImageDraw.ImageDraw, y: int, label: str, value: str, *, value_fill=TEXT) -> int:
    _text(draw, (92, y), label, 27, bold=True, fill=MUTED)
    _text(draw, (92, y + 34), value, 38, bold=True, fill=value_fill)
    draw.line((92, y + 86, 988, y + 86), fill=LINE, width=2)
    return y + 100


def build_signal_card(chart_bytes: bytes | None, signal: dict) -> bytes:
    """Information-only signal card. Chart is published separately."""
    canvas = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(canvas)

    _text(draw, (72, 58), "NEXUS SIGNAL", 45, bold=True, fill=TEXT)
    _text(draw, (72, 111), str(signal.get("code", "NX-DRAFT")), 29, bold=True, fill=GOLD)
    _paste_logo(canvas, (780, 28, 1010, 175))
    draw.line((72, 190, 1008, 190), fill=LINE, width=2)

    symbol = str(signal.get("symbol", "—")).upper()
    direction = str(signal.get("direction", "—")).upper()
    market = str(signal.get("market_type", "—")).upper()
    dir_fill = ACCENT if direction in {"BUY", "LONG"} else DANGER

    y = 220
    y = _row(draw, y, "MARKET", market)
    y = _row(draw, y, "SYMBOL", symbol)
    y = _row(draw, y, "DIRECTION", direction, value_fill=dir_fill)
    order_type = str(signal.get("order_type") or "MARKET").upper()
    y = _row(draw, y, "ORDER TYPE", order_type, value_fill=GOLD if order_type=="LIMIT" else TEXT)
    y = _row(draw, y, "ENTRY", str(signal.get("entry", "—")))
    y = _row(draw, y, "STOP LOSS", str(signal.get("stop_loss", "—")), value_fill=DANGER)
    y = _row(draw, y, "TP1", str(signal.get("tp1") or "-----"), value_fill=ACCENT)
    y = _row(draw, y, "TP2", str(signal.get("tp2") or "-----"), value_fill=ACCENT)
    y = _row(draw, y, "TP3", str(signal.get("tp3") or "-----"), value_fill=ACCENT)

    if market == "FOREX":
        volume_mode = str(signal.get("volume_mode") or "RISK").upper()
        if volume_mode == "FIXED":
            y = _row(draw, y, "LOT SIZE", str(signal.get("lot_size") or "—"), value_fill=GOLD)
            y = _row(draw, y, "RISK", "FIXED LOT", value_fill=GOLD)
        else:
            y = _row(draw, y, "LOT SIZE", "AUTO", value_fill=GOLD)
            y = _row(draw, y, "RISK", f"{signal.get('risk_percent', '—')}%", value_fill=GOLD)
    else:
        y = _row(draw, y, "LEVERAGE", str(signal.get("leverage") or "—"), value_fill=GOLD)
        y = _row(draw, y, "RISK", f"{signal.get('risk_percent', '—')}%", value_fill=GOLD)
    y = _row(draw, y, "R:R", str(signal.get("rr", "—")))

    trail_code = str(signal.get("trailing_code") or "—")
    trail_name = str(signal.get("trailing_name") or "—")
    _text(draw, (92, y), "TRAILING", 27, bold=True, fill=MUTED)
    _text(draw, (92, y + 34), trail_code, 33, bold=True, fill=GOLD)
    _text(draw, (92, y + 75), trail_name, 30, bold=True, fill=TEXT)

    out = BytesIO()
    canvas.save(out, format="PNG", optimize=True)
    return out.getvalue()


def build_result_card(chart_bytes: bytes | None, signal: dict, result_value: str, result_label: str) -> bytes:
    """Information-only result card. Final chart is published in its own frame."""
    canvas = Image.new("RGB", (W, 1080), BG)
    draw = ImageDraw.Draw(canvas)

    _text(draw, (72, 58), "NEXUS RESULT", 45, bold=True)
    _text(draw, (72, 111), str(signal.get("code", "—")), 29, bold=True, fill=GOLD)
    _paste_logo(canvas, (780, 28, 1010, 175))
    draw.line((72, 190, 1008, 190), fill=LINE, width=2)

    symbol = str(signal.get("symbol", "—")).upper()
    direction = str(signal.get("direction", "—")).upper()
    dir_fill = ACCENT if direction in {"BUY", "LONG"} else DANGER

    y = 245
    y = _row(draw, y, "SYMBOL", symbol)
    y = _row(draw, y, "DIRECTION", direction, value_fill=dir_fill)
    y = _row(draw, y, "ENTRY", str(signal.get("entry_price", signal.get("entry", "—"))))
    y = _row(draw, y, "EXIT", str(signal.get("exit_price", "—")))

    value_text = str(result_value)
    if value_text.startswith("+") or value_text in {"0", "0.0", "0 Pips", "+0 Pips", "+0%", "0%"}:
        result_fill = ACCENT
    elif value_text.startswith("-"):
        result_fill = DANGER
    else:
        result_fill = TEXT
    y = _row(draw, y, "RESULT", value_text, value_fill=result_fill)
    _text(draw, (92, y + 10), "STATUS", 27, bold=True, fill=MUTED)
    _text(draw, (92, y + 50), str(result_label), 42, bold=True, fill=result_fill)

    out = BytesIO()
    canvas.save(out, format="PNG", optimize=True)
    return out.getvalue()


# -------------------------
# NEXUS Report Card v7.0.1
# -------------------------
_REPORT_W, _REPORT_H = 1080, 1320
_REPORT_BG = (5, 9, 13)
_REPORT_PANEL = (10, 18, 24)
_REPORT_PANEL_2 = (12, 22, 29)
_REPORT_LINE = (53, 62, 70)
_REPORT_WHITE = (245, 247, 250)
_REPORT_MUTED = (178, 184, 194)
_REPORT_GREEN = (100, 203, 57)
_REPORT_RED = (255, 65, 65)
_REPORT_GOLD = (242, 183, 62)
_REPORT_ORANGE = (255, 151, 38)
_REPORT_BLUE = (62, 164, 255)
_REPORT_PURPLE = (192, 104, 240)

_FA_DIGITS = str.maketrans("0123456789.%", "۰۱۲۳۴۵۶۷۸۹٫٪")


def _fa_num(value: str) -> str:
    return str(value).translate(_FA_DIGITS)


def _signed(value: float, decimals: int = 1) -> str:
    if abs(value) < 0.0000001:
        value = 0.0
    return f"{value:+.{decimals}f}".rstrip("0").rstrip(".")


def _value_color(value: float, neutral=_REPORT_WHITE):
    if value > 0:
        return _REPORT_GREEN
    if value < 0:
        return _REPORT_RED
    return neutral


def _rounded(draw, box, radius=20, *, fill=None, outline=None, width=1):
    draw.rounded_rectangle(box, radius, fill=fill, outline=outline, width=width)


def _draw_metric(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], label: str, value: str,
                 value_fill, *, fa: bool):
    x1, y1, x2, y2 = box
    cx = (x1 + x2) // 2
    _text(draw, (cx, y1 + 24), label, 21, bold=False, fill=_REPORT_MUTED, anchor="ma", fa=fa)
    _text(draw, (cx, y1 + 58), value, 31, bold=True, fill=value_fill, anchor="ma", fa=fa)


def _draw_summary(draw: ImageDraw.ImageDraw, y: int, stats: dict, *, fa: bool):
    x1, x2 = 32, _REPORT_W - 32
    _rounded(draw, (x1, y, x2, y + 205), 18, fill=_REPORT_PANEL, outline=(100, 86, 56), width=2)
    title = "خلاصه کلی عملکرد" if fa else "Overall Performance"
    _text(draw, (_REPORT_W // 2, y + 16), title, 29, bold=True, fill=_REPORT_GOLD, anchor="ma", fa=fa)

    # Core performance metrics stay unit-neutral. Market results are displayed in
    # two separate cells so percent and pips are never visually mixed.
    core = [
        (("کل معاملات" if fa else "Total"), str(stats.get("closed", 0)), _REPORT_GOLD),
        (("تعداد برد" if fa else "Wins"), str(stats.get("wins", 0)), _REPORT_GREEN),
        (("تعداد باخت" if fa else "Losses"), str(stats.get("losses", 0)), _REPORT_RED),
        (("نرخ برد" if fa else "Win rate"), f"{stats.get('win_rate', 0):g}%", _REPORT_GREEN),
    ]
    inner_x1 = x1 + 20
    usable = (x2 - x1) - 40
    cell_w = usable // 4
    for i, (label, value, col) in enumerate(core):
        bx1 = inner_x1 + i * cell_w
        bx2 = bx1 + cell_w
        if i:
            draw.line((bx1, y + 58, bx1, y + 137), fill=_REPORT_LINE, width=1)
        if fa:
            value = _fa_num(value)
        _draw_metric(draw, (bx1, y + 50, bx2, y + 140), label, value, col, fa=fa)

    crypto = float(stats.get("crypto_pct", 0))
    forex = float(stats.get("forex_pips", 0))
    crypto_label = "سود / زیان کریپتو" if fa else "Crypto P/L"
    forex_label = "سود / زیان فارکس" if fa else "Forex P/L"
    crypto_value = f"{_signed(crypto, 2)}%"
    forex_value = f"{_signed(forex, 1)} {'پیپ' if fa else 'pips'}"
    if fa:
        crypto_value = _fa_num(crypto_value)
        forex_value = _fa_num(forex_value)

    _rounded(draw, (x1 + 26, y + 150, 520, y + 193), 11, fill=(20, 16, 10), outline=_REPORT_ORANGE, width=1)
    _text(draw, (292, y + 157), f"{crypto_label}   {crypto_value}", 21, bold=True,
          fill=_value_color(crypto, _REPORT_ORANGE), anchor="ma", fa=fa)
    _rounded(draw, (560, y + 150, x2 - 26, y + 193), 11, fill=(9, 18, 27), outline=_REPORT_BLUE, width=1)
    _text(draw, (788, y + 157), f"{forex_label}   {forex_value}", 21, bold=True,
          fill=_value_color(forex, _REPORT_BLUE), anchor="ma", fa=fa)


def _draw_market_icon(draw: ImageDraw.ImageDraw, cx: int, cy: int, market: str, color):
    draw.ellipse((cx - 25, cy - 25, cx + 25, cy + 25), outline=color, width=3)
    if market == "CRYPTO":
        # A simple Bitcoin-like B mark, drawn without depending on emoji fonts.
        _text(draw, (cx, cy - 1), "B", 30, bold=True, fill=color, anchor="mm")
        draw.line((cx - 5, cy - 17, cx - 5, cy + 17), fill=color, width=2)
        draw.line((cx + 5, cy - 17, cx + 5, cy + 17), fill=color, width=2)
    else:
        _text(draw, (cx, cy), "FX", 20, bold=True, fill=color, anchor="mm")


def _draw_market_section(draw: ImageDraw.ImageDraw, y: int, market: str, free: dict, vip: dict, *, fa: bool) -> int:
    market = market.upper()
    accent = _REPORT_ORANGE if market == "CRYPTO" else _REPORT_BLUE
    title = (("بازار کریپتو" if market == "CRYPTO" else "بازار فارکس") if fa
             else ("Crypto Market" if market == "CRYPTO" else "Forex Market"))
    unit = "%" if market == "CRYPTO" else ("پیپ" if fa else "pips")

    section_h = 328
    _rounded(draw, (24, y, _REPORT_W - 24, y + section_h), 20, fill=(7, 15, 20), outline=accent, width=2)
    _draw_market_icon(draw, 77, y + 46, market, accent)
    _text(draw, (_REPORT_W // 2, y + 20), title, 34, bold=True, fill=accent, anchor="ma", fa=fa)
    draw.line((190, y + 61, 890, y + 61), fill=(73, 64, 45), width=1)

    header_y = y + 79
    row1_y = y + 121
    row2_y = y + 216
    cols = [
        ("کانال" if fa else "Channel", 174),
        ("کل معاملات" if fa else "Total", 394),
        ("تعداد برد" if fa else "Wins", 548),
        ("تعداد باخت" if fa else "Losses", 688),
        ("نرخ برد" if fa else "Win rate", 820),
        (("سود / زیان" if fa else "P/L"), 962),
    ]
    for label, cx in cols:
        _text(draw, (cx, header_y), label, 20, fill=_REPORT_MUTED, anchor="ma", fa=fa)

    def row(row_y: int, name: str, stats: dict, channel_color, is_vip: bool):
        _rounded(draw, (38, row_y, _REPORT_W - 38, row_y + 82), 14,
                 fill=_REPORT_PANEL_2, outline=(62, 68, 76), width=1)
        badge_fill = (45, 27, 58) if is_vip else (17, 67, 53)
        _rounded(draw, (55, row_y + 13, 285, row_y + 69), 13, fill=badge_fill, outline=channel_color, width=1)
        _text(draw, (270, row_y + 28), name, 25, bold=True, fill=_REPORT_WHITE, anchor="ra", fa=fa)

        total = int(stats.get("total", 0))
        wins = int(stats.get("wins", 0))
        losses = int(stats.get("losses", 0))
        rate = float(stats.get("win_rate", 0))
        result_key = "result_pct" if market == "CRYPTO" else "result_pips"
        result = float(stats.get(result_key, 0))
        values = [
            (394, str(total), _REPORT_WHITE),
            (548, str(wins), _REPORT_GREEN if not is_vip else _REPORT_PURPLE),
            (688, str(losses), _REPORT_RED),
            (820, f"{rate:g}%", _REPORT_GREEN if not is_vip else _REPORT_PURPLE),
            (962, f"{_signed(result, 2 if market == 'CRYPTO' else 1)}{unit if market == 'CRYPTO' else ' ' + unit}", _value_color(result, _REPORT_PURPLE if is_vip else _REPORT_WHITE)),
        ]
        for cx, value, col in values:
            if fa:
                value = _fa_num(value)
            _text(draw, (cx, row_y + 27), value, 27, bold=True, fill=col, anchor="ma", fa=fa)

    row(row1_y, "کانال عمومی" if fa else "Public Channel", free, _REPORT_GREEN, False)
    row(row2_y, "کانال وی‌آی‌پی" if fa else "VIP Channel", vip, _REPORT_PURPLE, True)
    return y + section_h


def build_report_card(kind: str, period_text: str, summary: dict,
                      crypto_free: dict, crypto_vip: dict,
                      forex_free: dict, forex_vip: dict,
                      lang: str = "fa") -> bytes:
    """Build the final NEXUS daily/weekly report as ONE standalone flash card.

    - No chart/photo is embedded.
    - No Telegram caption is required.
    - Crypto P/L is expressed as percent.
    - Forex P/L is expressed as pips.
    - Public and VIP channel results are separated inside each market section.
    - Persian rendering prefers the locally installed B Yekan font.
    """
    fa = str(lang).lower().startswith("fa")
    canvas = Image.new("RGB", (_REPORT_W, _REPORT_H), _REPORT_BG)
    draw = ImageDraw.Draw(canvas)

    # Main frame
    _rounded(draw, (8, 8, _REPORT_W - 8, _REPORT_H - 8), 26,
             fill=_REPORT_BG, outline=_REPORT_GOLD, width=2)

    # Header
    _paste_logo(canvas, (32, 26, 180, 164))
    if fa:
        title = "گزارش روزانه نکسوس" if kind == "daily" else "گزارش هفتگی نکسوس"
        _text(draw, (1024, 40), title, 48, bold=True, fill=_REPORT_WHITE, anchor="ra", fa=True)
        _text(draw, (1024, 102), period_text, 27, fill=_REPORT_MUTED, anchor="ra", fa=True)
    else:
        title = "NEXUS DAILY REPORT" if kind == "daily" else "NEXUS WEEKLY REPORT"
        _text(draw, (1024, 42), title, 45, bold=True, fill=_REPORT_WHITE, anchor="ra")
        _text(draw, (1024, 104), period_text, 26, fill=_REPORT_MUTED, anchor="ra")

    _draw_summary(draw, 181, summary, fa=fa)
    y = _draw_market_section(draw, 415, "CRYPTO", crypto_free, crypto_vip, fa=fa)
    y = _draw_market_section(draw, y + 24, "FOREX", forex_free, forex_vip, fa=fa)

    # Footer brand and accounting note
    footer_y = y + 26
    _text(draw, (_REPORT_W // 2, footer_y), "نکسوس" if fa else "NEXUS", 34, bold=True,
          fill=_REPORT_GOLD, anchor="ma", fa=fa)
    _text(draw, (_REPORT_W // 2, footer_y + 42), "هوشمند معامله کن" if fa else "Trade Smarter", 22,
          fill=_REPORT_MUTED, anchor="ma", fa=fa)
    note = ("کریپتو بر پایه درصد حرکت قیمت و فارکس بر پایه پیپ محاسبه شده است."
            if fa else "Crypto is reported by price-move percentage; Forex is reported in pips.")
    _rounded(draw, (104, footer_y + 84, _REPORT_W - 104, footer_y + 134), 16,
             fill=(12, 17, 22), outline=(77, 70, 54), width=1)
    _text(draw, (_REPORT_W // 2, footer_y + 98), note, 19, fill=_REPORT_MUTED, anchor="ma", fa=fa)

    out = BytesIO()
    canvas.save(out, format="PNG", optimize=True)
    return out.getvalue()


def build_report_cover(kind: str = "daily") -> bytes:
    """Backward-compatible logo cover retained for external imports.

    NEXUS v7.0.1 no longer uses this in scheduled channel reports; those use
    build_report_card() and are sent as a single image with no caption.
    """
    canvas = Image.new("RGB", (1080, 540), (0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    _paste_logo(canvas, (290, 70, 790, 430))
    draw.line((120, 470, 960, 470), fill=(45, 45, 45), width=2)
    out = BytesIO()
    canvas.save(out, format="PNG", optimize=True)
    return out.getvalue()
