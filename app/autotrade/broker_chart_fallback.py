from __future__ import annotations

import hashlib
import json
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
_SUPPORTED_TF = {"M1", "M5", "M15", "M30", "H1", "H4", "D1"}
_TF_SECONDS = {"M1": 60, "M5": 300, "M15": 900, "M30": 1800, "H1": 3600, "H4": 14400, "D1": 86400}
_MIN_BARS = 24
_MAX_BARS = 120
_VISIBLE_BARS = 72
_MIN_CANDLE_VIEW_RATIO = 0.34
_MAX_FEED_AGE_SECONDS = 90
_STYLE_VERSION = "nexus-signal-minimal-v7"

# Approved minimal chart palette. Keep the number of semantic colors small:
# neutral navy, cyan/teal candles, blue entry, green targets, red stop.
_BG = (5, 16, 29)
_GRID = (16, 33, 49)
_UP = (19, 219, 205)
_DOWN = (255, 83, 98)
_ENTRY = (33, 150, 243)
_SL = (255, 82, 95)
_TP = (28, 218, 126)
# Price values are intentionally secondary to semantic labels, but use the
# approved warm yellow so they remain instantly scannable.
_PRICE_TEXT = (255, 209, 102)


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


def _canonical_visual_payload(signal: Any, targets: list[float]) -> dict[str, Any]:
    """Immutable publication identity used to bind one image to one signal snapshot."""
    return {
        "signal_id": int(_signal_value(signal, "id", 0) or 0),
        "code": str(_signal_value(signal, "code", "") or ""),
        "symbol": normalize_symbol(str(_signal_value(signal, "symbol", "") or "")),
        "timeframe": str(_signal_value(signal, "timeframe", "M5") or "M5").upper(),
        "direction": str(_signal_value(signal, "direction", "") or "").upper(),
        "order_type": str(_signal_value(signal, "order_type", "MARKET") or "MARKET").upper(),
        "entry_price": float(_signal_value(signal, "entry_price", 0) or 0),
        "stop_loss": float(_signal_value(signal, "stop_loss", 0) or 0),
        "targets": [float(value) for value in targets],
        "risk_percent": float(_signal_value(signal, "risk_percent", 0) or 0),
        "rr_ratio": float(_signal_value(signal, "rr_ratio", 0) or 0),
        "destination": str(_signal_value(signal, "destination", "BOTH") or "BOTH").upper(),
    }


def signal_visual_fingerprint(signal: Any, targets: list[float]) -> str:
    payload = json.dumps(
        _canonical_visual_payload(signal, targets),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _format_level_price(value: float, digits: int | None) -> str:
    precision = int(digits) if isinstance(digits, int) and 0 <= int(digits) <= 8 else (5 if abs(value) < 10 else 2)
    return f"{float(value):.{precision}f}"


def _signal_anchor(signal: Any, timeframe: str) -> tuple[int | None, str | None, str | None]:
    """Resolve the broker chart candle that contains the signal entry event.

    opened_at is authoritative when present. Pending orders may instead have
    limit_activated_at. issued_at/created_at keep older rows reconstructable.
    The returned epoch is floored to the MT5 candle open for the signal TF.
    """
    for field in ("opened_at", "limit_activated_at", "issued_at", "created_at"):
        parsed = _parse_utc(_signal_value(signal, field))
        if parsed is None:
            continue
        seconds = _TF_SECONDS.get(timeframe)
        if not seconds:
            return None, None, None
        epoch = int(parsed.timestamp())
        bar_time = epoch - (epoch % seconds)
        return bar_time, parsed.isoformat(), field
    return None, None, None


def _load_series(signal: Any) -> tuple[list[dict[str, float]], dict[str, Any]]:
    """Load a fresh broker source while reconstructing the entry-time chart.

    Freshness is validated against the latest MarketFeed capture, but when the
    signal has an execution/issue timestamp the visible candle window ends at
    that signal's MT5 bar. This prevents later preview/repair renders from using
    today's latest candle and making the original ENTRY appear detached.
    """
    account = str(_signal_value(signal, "issuer_account", "") or "").strip()
    symbol = normalize_symbol(str(_signal_value(signal, "symbol", "") or ""))
    timeframe = str(_signal_value(signal, "timeframe", "M5") or "M5").strip().upper()
    if not account or not symbol or timeframe not in _SUPPORTED_TF:
        return [], {"reason": "UNSUPPORTED_IDENTITY", "account": account, "symbol": symbol, "timeframe": timeframe}

    anchor_bar_time, anchor_time, anchor_field = _signal_anchor(signal, timeframe)

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

            if anchor_bar_time is not None:
                rows = con.execute(
                    """SELECT bar_time,open,high,low,close,tick_volume,captured_at
                       FROM mt5_market_candles
                       WHERE account_number=? AND symbol=? AND timeframe=? AND bar_time<=?
                       ORDER BY bar_time DESC LIMIT ?""",
                    (account, symbol, timeframe, int(anchor_bar_time), _MAX_BARS),
                ).fetchall()
            else:
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
        "anchor_applied": anchor_bar_time is not None,
        "anchor_bar_time": anchor_bar_time,
        "anchor_time": anchor_time,
        "anchor_field": anchor_field,
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
        meta["reason"] = "INSUFFICIENT_ANCHORED_BARS" if anchor_bar_time is not None else "INSUFFICIENT_BARS"
        return [], meta

    # If the exact bucket is not retained, fail rather than silently presenting
    # a later candle as the original entry. This keeps preview/repair truthful.
    if anchor_bar_time is not None and int(candles[-1]["time"]) != int(anchor_bar_time):
        meta["reason"] = "ENTRY_ANCHOR_BAR_MISSING"
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


def _resolve_label_positions(
    levels: list[tuple[str, int, tuple[int, int, int]]],
    *,
    top_bound: int,
    bottom_bound: int,
    min_gap: int = 26,
) -> dict[str, int]:
    """Resolve right-edge labels inside the actual chart viewport.

    Older minimal-card builds kept the legacy 72..690 bounds from the previous
    rail layout, which could detach labels from their level lines on a 900px
    edge-to-edge chart. Bounds are now supplied by the renderer.
    """
    if not levels:
        return {}
    ordered = sorted(levels, key=lambda item: item[1])
    placed: list[list[Any]] = []
    for label, desired, color in ordered:
        value = max(top_bound, min(bottom_bound, desired))
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


def _price_viewport(
    candles: list[dict[str, float]],
    level_values: list[float],
) -> tuple[float, float]:
    """Keep broker candles readable without hiding exact signal levels.

    Nearby levels are included in the natural viewport. Very distant SL/TP
    values no longer flatten the entire candle structure; those levels are
    edge-pinned by the renderer while retaining their exact numeric labels.
    """
    lows = [float(item["low"]) for item in candles]
    highs = [float(item["high"]) for item in candles]
    candle_min = min(lows)
    candle_max = max(highs)
    reference = max(abs(candle_max), 1.0)
    candle_span = max(candle_max - candle_min, reference * 0.0005)

    # The candle body must keep at least ~34% of the vertical viewport.
    max_view_span = candle_span / _MIN_CANDLE_VIEW_RATIO
    center = (candle_min + candle_max) / 2.0
    y_min = candle_min
    y_max = candle_max

    for value in sorted(
        [float(v) for v in level_values if isinstance(v, (int, float)) and float(v) > 0],
        key=lambda v: min(abs(v - candle_min), abs(v - candle_max)),
    ):
        candidate_min = min(y_min, value)
        candidate_max = max(y_max, value)
        if candidate_max - candidate_min <= max_view_span:
            y_min, y_max = candidate_min, candidate_max

    span = max(y_max - y_min, candle_span)
    pad = span * 0.10
    y_min -= pad
    y_max += pad

    # Keep the padded viewport centered enough that candle data cannot collapse
    # against one edge after one-sided TP/SL expansion.
    final_span = y_max - y_min
    candle_center = (candle_min + candle_max) / 2.0
    allowed_span = max(final_span, candle_span / _MIN_CANDLE_VIEW_RATIO)
    lower = candle_center - allowed_span / 2.0
    upper = candle_center + allowed_span / 2.0
    y_min = min(y_min, lower)
    y_max = max(y_max, upper)
    return y_min, y_max


def _render_chart(signal: Any, candles: list[dict[str, float]], meta: dict[str, Any], targets: list[float]) -> bytes:
    """Render the approved minimal NEXUS signal flash card.

    The publication image contains only the broker-truth candlestick chart,
    the NEXUS logo, and the signal levels drawn directly on the chart. No
    header, information rail, footer, marketing copy, or auxiliary panels are
    allowed in this renderer.
    """
    width, height = 1600, 900
    image = Image.new("RGB", (width, height), _BG)
    draw = ImageDraw.Draw(image)

    # Edge-to-edge chart with only a small safe margin for Telegram compression.
    chart_left, chart_right = 20, width - 20
    chart_top, chart_bottom = 20, height - 20
    chart_w = chart_right - chart_left
    chart_h = chart_bottom - chart_top

    entry = float(_signal_value(signal, "entry_price", 0) or 0)
    sl = float(_signal_value(signal, "stop_loss", 0) or 0)
    digits = meta.get("digits")

    # Quiet chart surface: no container card, title rail, or footer.
    for i in range(1, 12):
        x = int(chart_left + chart_w * i / 12)
        draw.line((x, chart_top, x, chart_bottom), fill=_GRID, width=1)
    for i in range(1, 7):
        y = int(chart_top + chart_h * i / 7)
        draw.line((chart_left, y, chart_right, y), fill=_GRID, width=1)

    # Keep the flash card visually legible: use the most relevant entry-time
    # candles rather than squeezing 120 bars into Telegram's image viewport.
    render_candles = candles[-_VISIBLE_BARS:] if len(candles) > _VISIBLE_BARS else candles

    level_values = [value for value in [entry, sl, *targets] if isinstance(value, (int, float)) and value > 0]
    y_min, y_max = _price_viewport(render_candles, level_values)
    span = y_max - y_min

    def y_of(price: float) -> int:
        ratio = (y_max - float(price)) / span
        return int(chart_top + ratio * chart_h)

    count = len(render_candles)
    step = chart_w / max(count, 1)
    body_w = max(4, min(12, int(step * 0.56)))
    for idx, candle in enumerate(render_candles):
        x = int(chart_left + (idx + 0.5) * step)
        o, h, l, close = map(float, (candle["open"], candle["high"], candle["low"], candle["close"]))
        color = _UP if close >= o else _DOWN
        y_h, y_l, y_o, y_c = y_of(h), y_of(l), y_of(o), y_of(close)
        draw.line((x, y_h, x, y_l), fill=color, width=2)
        body_top, body_bottom = sorted((y_o, y_c))
        if body_bottom - body_top < 3:
            body_bottom = body_top + 3
        draw.rounded_rectangle(
            (x - body_w // 2, body_top, x + body_w // 2, body_bottom),
            radius=1,
            fill=color,
        )

    # Levels remain part of the chart itself. Labels are deliberately tiny and
    # live at the far-right edge; there is no separate information panel.
    level_specs: list[tuple[str, float, tuple[int, int, int]]] = []
    if sl > 0:
        level_specs.append(("SL", sl, _SL))
    if entry > 0:
        level_specs.append(("ENTRY", entry, _ENTRY))
    for idx, value in enumerate(targets[:5], start=1):
        if float(value) > 0:
            level_specs.append((f"TP{idx}", float(value), _TP))

    label_positions = _resolve_label_positions(
        [(label, max(chart_top + 10, min(chart_bottom - 10, y_of(price))), color) for label, price, color in level_specs],
        top_bound=chart_top + 20,
        bottom_bound=chart_bottom - 20,
        min_gap=28,
    )
    label_x = chart_right - 12
    line_right = chart_right - 150

    for label, price, color in level_specs:
        raw_y = y_of(price)
        y = max(chart_top + 10, min(chart_bottom - 10, raw_y))
        # Off-viewport levels are pinned to the top/bottom edge instead of
        # expanding the scale until candles become a flat line.
        _draw_dashed(draw, (chart_left + 12, y, line_right, y), color, width=2, dash=10, gap=8)
        ly = label_positions.get(label, y)
        text = f"{label}  {_format_level_price(price, digits)}"
        bbox = draw.textbbox((0, 0), text, font=_font(12, True))
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        pad_x, pad_y = 10, 6
        x1 = label_x - tw - pad_x * 2
        y1 = ly - th // 2 - pad_y
        x2 = label_x
        y2 = ly + th // 2 + pad_y
        draw.rounded_rectangle((x1, y1, x2, y2), radius=7, fill=(5, 16, 29), outline=color, width=1)
        draw.text((label_x - pad_x, ly), text, font=_font(12, True), fill=color, anchor="rm")

    # Approved branding: logo only. No NEXUS SIGNAL title or other copy.
    logo = _load_logo().copy()
    logo.thumbnail((150, 92), Image.Resampling.LANCZOS)
    logo_x = chart_left + 28
    logo_y = chart_top + 24
    image.paste(logo, (logo_x, logo_y), logo)

    out = BytesIO()
    image.save(out, format="PNG", optimize=True)
    return out.getvalue()


def ensure_broker_chart_asset(signal: Any) -> dict[str, Any]:
    """Render and stage the canonical broker-truth publication image.

    For WEB_ADMIN/Mini App signals this is the publication authority. It uses
    only stored signal values and fresh MT5 MarketFeed OHLC. A ChartAgent
    screenshot may still exist for diagnostics, but it cannot become the
    Telegram publication image.
    """
    signal_id = int(_signal_value(signal, "id", 0) or 0)
    if signal_id <= 0:
        return {"ok": False, "reason": "BAD_SIGNAL_ID"}

    candles, meta = _load_series(signal)
    if not candles:
        return {"ok": False, **meta}

    try:
        targets = [float(row["price"]) for row in db.get_signal_targets(signal_id)]
        fingerprint = signal_visual_fingerprint(signal, targets)
        raw = _render_chart(signal, candles, meta, targets)
        if not raw.startswith(b"\x89PNG\r\n\x1a\n") or len(raw) < 10_000:
            return {"ok": False, "reason": "RENDER_INVALID", "fingerprint": fingerprint, **meta}

        _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        code = str(_signal_value(signal, "code", f"NX-{signal_id}") or f"NX-{signal_id}")
        path = _OUTPUT_DIR / f"{code}_canonical_{signal_id}_{fingerprint[:12]}.png"
        temp = path.with_suffix(".tmp")
        temp.write_bytes(raw)
        temp.replace(path)
        db.save_mt5_signal_publication_asset(signal_id, str(path))
        db.add_signal_event(
            signal_id,
            "CANONICAL_SIGNAL_VISUAL_GENERATED",
            actor_type="BACKEND",
            account_number=str(meta.get("account") or ""),
            correlation_id=code,
            payload={
                "source": "MT5_MARKET_FEED",
                "style_version": _STYLE_VERSION,
                "signal_visual_fingerprint": fingerprint,
                "broker_symbol": meta.get("broker_symbol"),
                "timeframe": meta.get("timeframe"),
                "bars": len(candles),
                "age_seconds": round(float(meta.get("age_seconds") or 0.0), 3),
                "anchor_applied": bool(meta.get("anchor_applied")),
                "anchor_bar_time": meta.get("anchor_bar_time"),
                "anchor_field": meta.get("anchor_field"),
                "file_path": str(path),
                "image_sha256": hashlib.sha256(raw).hexdigest(),
                "bytes": len(raw),
            },
        )
        return {
            "ok": True,
            "file_path": str(path),
            "bytes": len(raw),
            "bars": len(candles),
            "style_version": _STYLE_VERSION,
            "fingerprint": fingerprint,
            "image_sha256": hashlib.sha256(raw).hexdigest(),
            **meta,
        }
    except Exception as exc:
        log.exception("canonical broker chart render failed signal_id=%s", signal_id)
        try:
            db.add_signal_event(
                signal_id,
                "CANONICAL_SIGNAL_VISUAL_FAILED",
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

