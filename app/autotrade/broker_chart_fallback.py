from __future__ import annotations

import logging
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from .. import db
from .symbol_registry import normalize_symbol

log = logging.getLogger("nexus.broker_chart_fallback")

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_OUTPUT_DIR = _PROJECT_ROOT / "artifacts" / "signal_charts"
_LOGO_PATH = _PROJECT_ROOT / "assets" / "branding" / "NEXUS_logo_2026.jpg"
_SUPPORTED_TF = {"M1", "M5", "M15", "H1", "D1"}
_MIN_BARS = 24
_MAX_BARS = 120
_MAX_FEED_AGE_SECONDS = 90
_STYLE_VERSION = "nexus-clean-signal-v2"

# Approved minimal chart palette. Keep the number of semantic colors small:
# neutral navy, cyan/teal candles, blue entry, green targets, red stop.
_BG = (5, 16, 29)
_GRID = (16, 33, 49)
_UP = (19, 219, 205)
_DOWN = (255, 83, 98)
_ENTRY = (33, 150, 243)
_SL = (255, 82, 95)
_TP = (28, 218, 126)
_PRICE_TEXT = (132, 148, 164)


def _font(size: int, bold: bool = False):
    candidates = [
        r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        try:
            if Path(candidate).exists():
                return ImageFont.truetype(candidate, size=size)
        except Exception:
            pass
    return ImageFont.load_default()


def _parse_utc(value: str | None) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _age_seconds(value: str | None) -> float | None:
    parsed = _parse_utc(value)
    if parsed is None:
        return None
    return max(0.0, (datetime.now(timezone.utc) - parsed).total_seconds())


def _signal_value(signal: Any, key: str, default=None):
    if isinstance(signal, dict):
        return signal.get(key, default)
    try:
        return signal[key]
    except Exception:
        return default


def _load_series(signal: Any) -> tuple[list[dict[str, float]], dict[str, Any]]:
    account = str(_signal_value(signal, "issuer_account", "") or "").strip()
    symbol = normalize_symbol(str(_signal_value(signal, "symbol", "") or ""))
    timeframe = str(_signal_value(signal, "timeframe", "M5") or "M5").strip().upper()
    if not account or not symbol or timeframe not in _SUPPORTED_TF:
        return [], {"reason": "UNSUPPORTED_IDENTITY", "account": account, "symbol": symbol, "timeframe": timeframe}

    try:
        with db.conn() as con:
            source = con.execute(
                """SELECT broker_symbol,digits,MAX(captured_at) AS captured_at
                   FROM mt5_market_candles
                   WHERE account_number=? AND symbol=? AND timeframe=?
                   GROUP BY broker_symbol,digits
                   ORDER BY captured_at DESC LIMIT 1""",
                (account, symbol, timeframe),
            ).fetchone()
            if not source:
                return [], {"reason": "NO_SERIES", "account": account, "symbol": symbol, "timeframe": timeframe}
            rows = con.execute(
                """SELECT bar_time,open,high,low,close,tick_volume,captured_at
                   FROM mt5_market_candles
                   WHERE account_number=? AND symbol=? AND timeframe=?
                   ORDER BY bar_time DESC LIMIT ?""",
                (account, symbol, timeframe, _MAX_BARS),
            ).fetchall()
    except Exception as exc:
        return [], {"reason": f"DB_ERROR:{exc}", "account": account, "symbol": symbol, "timeframe": timeframe}

    captured_at = str(source["captured_at"] or "") or None
    age = _age_seconds(captured_at)
    meta = {
        "reason": "OK",
        "account": account,
        "symbol": symbol,
        "broker_symbol": str(source["broker_symbol"] or symbol),
        "timeframe": timeframe,
        "digits": int(source["digits"]) if source["digits"] is not None else None,
        "captured_at": captured_at,
        "age_seconds": age,
    }
    if age is None or age > _MAX_FEED_AGE_SECONDS:
        meta["reason"] = "STALE_FEED"
        return [], meta

    candles = [
        {
            "time": int(row["bar_time"]),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "tick_volume": float(row["tick_volume"] or 0.0),
        }
        for row in reversed(rows)
    ]
    if len(candles) < _MIN_BARS:
        meta["reason"] = "INSUFFICIENT_BARS"
        return [], meta
    return candles, meta


def _draw_dashed(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    fill,
    width: int = 2,
    dash: int = 6,
    gap: int = 5,
):
    x1, y1, x2, y2 = xy
    if y1 != y2:
        draw.line(xy, fill=fill, width=width)
        return
    x = x1
    while x < x2:
        draw.line((x, y1, min(x + dash, x2), y2), fill=fill, width=width)
        x += dash + gap


def _load_logo() -> Image.Image:
    try:
        if _LOGO_PATH.exists():
            logo = Image.open(_LOGO_PATH).convert("RGBA")
            alpha = logo.convert("L").point(lambda value: 0 if value < 18 else 255)
            logo.putalpha(alpha)
            bbox = alpha.getbbox()
            if bbox:
                logo = logo.crop(bbox)
            return logo
    except Exception:
        log.exception("failed loading NEXUS logo")

    # Small deterministic NEXUS mark fallback; no text and no external assets.
    logo = Image.new("RGBA", (96, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(logo)
    d.polygon([(10, 50), (10, 14), (29, 14), (58, 48), (58, 14), (75, 14), (75, 50), (56, 50), (28, 18), (28, 50)], fill=(33, 150, 243, 255))
    d.polygon([(54, 42), (82, 14), (78, 14), (78, 7), (91, 7), (91, 20), (84, 20), (62, 48)], fill=(19, 219, 205, 255))
    return logo


def _paste_small_logo(image: Image.Image) -> None:
    logo = _load_logo().copy()
    logo.thumbnail((68, 42), Image.Resampling.LANCZOS)
    x = image.width - logo.width - 18
    y = 16
    image.paste(logo, (x, y), logo)


def _resolve_label_positions(levels: list[tuple[str, int, tuple[int, int, int]]]) -> dict[str, int]:
    if not levels:
        return {}
    ordered = sorted(levels, key=lambda item: item[1])
    min_gap = 24
    top_bound = 72
    bottom_bound = 690
    placed: list[list[Any]] = []
    for label, desired, color in ordered:
        value = max(top_bound, desired)
        if placed:
            value = max(value, int(placed[-1][1]) + min_gap)
        placed.append([label, value, color])
    if placed[-1][1] > bottom_bound:
        shift = int(placed[-1][1]) - bottom_bound
        for item in placed:
            item[1] -= shift
        for idx in range(len(placed) - 2, -1, -1):
            placed[idx][1] = min(int(placed[idx][1]), int(placed[idx + 1][1]) - min_gap)
        if placed[0][1] < top_bound:
            shift_down = top_bound - int(placed[0][1])
            for item in placed:
                item[1] += shift_down
    return {str(label): int(value) for label, value, _ in placed}


def _render_chart(signal: Any, candles: list[dict[str, float]], meta: dict[str, Any], targets: list[float]) -> bytes:
    """Render the approved minimal NEXUS chart.

    Visual contract:
      * chart + small NEXUS logo only;
      * ENTRY blue, TP green, SL red;
      * short fine-dashed levels start at the latest candle and extend only
        into reserved right-side whitespace;
      * semantic labels stay small; price values use a lighter 11px font;
      * no label boxes, header, footer, source text, axes text or side panels.
    """
    width, height = 1280, 720
    image = Image.new("RGB", (width, height), _BG)
    draw = ImageDraw.Draw(image)

    candle_left, candle_right = 18, 925
    top, bottom = 24, 696
    chart_w = candle_right - candle_left
    chart_h = bottom - top

    # Low-contrast grid: enough structure without visual competition.
    for i in range(1, 8):
        x = int(width * i / 8)
        draw.line((x, 0, x, height), fill=_GRID, width=1)
    for i in range(1, 6):
        y = int(height * i / 6)
        draw.line((0, y, width, y), fill=_GRID, width=1)

    entry = float(_signal_value(signal, "entry_price", 0) or 0)
    sl = float(_signal_value(signal, "stop_loss", 0) or 0)
    level_values = [value for value in [entry, sl, *targets] if isinstance(value, (int, float)) and value > 0]
    lows = [float(c["low"]) for c in candles]
    highs = [float(c["high"]) for c in candles]
    y_min = min(lows + level_values) if level_values else min(lows)
    y_max = max(highs + level_values) if level_values else max(highs)
    span = max(y_max - y_min, max(abs(y_max), 1.0) * 0.0005)
    y_min -= span * 0.075
    y_max += span * 0.075
    span = y_max - y_min

    def y_of(price: float) -> int:
        ratio = (y_max - price) / span
        return int(top + ratio * chart_h)

    count = len(candles)
    step = chart_w / max(count, 1)
    body_w = max(3, min(9, int(step * 0.58)))
    last_x = candle_left
    for idx, candle in enumerate(candles):
        x = int(candle_left + (idx + 0.5) * step)
        last_x = x
        o, h, l, c = map(float, (candle["open"], candle["high"], candle["low"], candle["close"]))
        color = _UP if c >= o else _DOWN
        y_h, y_l, y_o, y_c = y_of(h), y_of(l), y_of(o), y_of(c)
        draw.line((x, y_h, x, y_l), fill=color, width=1)
        top_body, bottom_body = sorted((y_o, y_c))
        if bottom_body - top_body < 2:
            bottom_body = top_body + 2
        draw.rectangle((x - body_w // 2, top_body, x + body_w // 2, bottom_body), fill=color)

    level_specs: list[tuple[str, float, tuple[int, int, int]]] = []
    if entry > 0:
        level_specs.append(("ENTRY", entry, _ENTRY))
    if sl > 0:
        level_specs.append(("SL", sl, _SL))
    for idx, value in enumerate(targets[:5], start=1):
        if value > 0:
            level_specs.append((f"TP{idx}", float(value), _TP))

    desired_levels = [(label, y_of(price), color) for label, price, color in level_specs]
    label_positions = _resolve_label_positions(desired_levels)
    line_start = min(width - 300, last_x + max(8, body_w // 2 + 5))
    line_end = 1158
    label_x = 1172
    price_x = 1262
    label_font = _font(12, True)
    price_font = _font(11, False)
    digits = meta.get("digits")
    precision = int(digits) if isinstance(digits, int) else (5 if max(y_max, 0) < 10 else 2)

    for label, price, color in level_specs:
        y = y_of(price)
        label_y = label_positions.get(label, y)
        _draw_dashed(draw, (line_start, y, line_end, y), color, width=2, dash=6, gap=5)
        if abs(label_y - y) > 2:
            draw.line((line_end, y, label_x - 6, label_y), fill=color, width=1)
        draw.text((label_x, label_y), label, font=label_font, fill=color, anchor="lm")
        draw.text((price_x, label_y), f"{price:.{precision}f}", font=price_font, fill=_PRICE_TEXT, anchor="rm")

    _paste_small_logo(image)

    out = BytesIO()
    image.save(out, format="PNG", optimize=True)
    return out.getvalue()


def ensure_broker_chart_asset(signal: Any) -> dict[str, Any]:
    """Render the canonical broker-truth publication chart from MT5 MarketFeed.

    This renderer is shared by MT5_ADMIN and WEB_ADMIN publication paths. It
    never invents OHLC values and refuses stale/missing/insufficient broker data.
    """
    signal_id = int(_signal_value(signal, "id", 0) or 0)
    if signal_id <= 0:
        return {"ok": False, "reason": "BAD_SIGNAL_ID"}

    candles, meta = _load_series(signal)
    if not candles:
        return {"ok": False, **meta}

    try:
        targets = [float(row["price"]) for row in db.get_signal_targets(signal_id)]
        raw = _render_chart(signal, candles, meta, targets)
        if not raw.startswith(b"\x89PNG\r\n\x1a\n") or len(raw) < 10_000:
            return {"ok": False, "reason": "RENDER_INVALID", **meta}

        _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        code = str(_signal_value(signal, "code", f"NX-{signal_id}") or f"NX-{signal_id}")
        path = _OUTPUT_DIR / f"{code}_broker_feed_{signal_id}.png"
        temp = path.with_suffix(".tmp")
        temp.write_bytes(raw)
        temp.replace(path)
        db.save_mt5_signal_publication_asset(signal_id, str(path))
        db.add_signal_event(
            signal_id,
            "BROKER_CHART_FALLBACK_GENERATED",
            actor_type="BACKEND",
            account_number=str(meta.get("account") or ""),
            correlation_id=code,
            payload={
                "source": "MT5_MARKET_FEED",
                "style_version": _STYLE_VERSION,
                "broker_symbol": meta.get("broker_symbol"),
                "timeframe": meta.get("timeframe"),
                "bars": len(candles),
                "age_seconds": round(float(meta.get("age_seconds") or 0.0), 3),
                "file_path": str(path),
                "bytes": len(raw),
            },
        )
        return {
            "ok": True,
            "file_path": str(path),
            "bytes": len(raw),
            "bars": len(candles),
            "style_version": _STYLE_VERSION,
            **meta,
        }
    except Exception as exc:
        log.exception("broker chart fallback failed signal_id=%s", signal_id)
        try:
            db.add_signal_event(
                signal_id,
                "BROKER_CHART_FALLBACK_FAILED",
                actor_type="BACKEND",
                account_number=str(meta.get("account") or ""),
                correlation_id=str(_signal_value(signal, "code", signal_id)),
                result="FAILED",
                reason=str(exc)[:1000],
                payload={"source": "MT5_MARKET_FEED", "style_version": _STYLE_VERSION, "meta": meta},
            )
        except Exception:
            pass
        return {"ok": False, "reason": f"RENDER_ERROR:{exc}", **meta}
