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
_SUPPORTED_TF = {"M1", "M5", "M15", "H1", "D1"}
_TF_SECONDS = {"M1": 60, "M5": 300, "M15": 900, "H1": 3600, "D1": 86400}
_MIN_BARS = 24
_MAX_BARS = 120
_MAX_FEED_AGE_SECONDS = 90
_STYLE_VERSION = "nexus-signal-canonical-v4"

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
    """Render the canonical NEXUS Mini App signal visual from broker-truth OHLC.

    The image is deterministic from the stored signal snapshot + fresh MT5
    MarketFeed candles. Uploaded/ChartAgent screenshots are never used as
    publication artwork for WEB_ADMIN signals, so stale chart objects cannot
    change ENTRY/SL/TP values shown to channel users.
    """
    width, height = 1280, 720
    image = Image.new("RGB", (width, height), _BG)
    draw = ImageDraw.Draw(image)

    header_h = 62
    footer_h = 30
    chart_left, chart_right = 28, 920
    chart_top, chart_bottom = 82, height - footer_h - 14
    rail_left, rail_right = 944, 1254
    chart_w = chart_right - chart_left
    chart_h = chart_bottom - chart_top

    code = str(_signal_value(signal, "code", "NEXUS") or "NEXUS")
    symbol = normalize_symbol(str(_signal_value(signal, "symbol", "") or ""))
    timeframe = str(_signal_value(signal, "timeframe", "M5") or "M5").upper()
    direction = str(_signal_value(signal, "direction", "") or "").upper()
    order_type = str(_signal_value(signal, "order_type", "MARKET") or "MARKET").upper()
    entry = float(_signal_value(signal, "entry_price", 0) or 0)
    sl = float(_signal_value(signal, "stop_loss", 0) or 0)
    digits = meta.get("digits")
    direction_color = _UP if direction in {"BUY", "LONG"} else _DOWN

    # Header: compact brand + signal identity. No marketing copy.
    _paste_small_logo(image)
    draw.text((28, 20), "NEXUS SIGNAL", font=_font(18, True), fill=(236, 243, 250))
    draw.text((174, 22), code, font=_font(15, True), fill=_PRICE_TEXT)
    identity = f"{symbol}  •  {direction}  •  {timeframe}  •  {order_type.replace('_', ' ')}"
    draw.text((1254, 22), identity, font=_font(14, True), fill=direction_color, anchor="ra")
    draw.line((28, header_h, 1254, header_h), fill=(25, 48, 68), width=1)

    # Chart surface.
    draw.rounded_rectangle(
        (chart_left, chart_top, chart_right, chart_bottom),
        radius=16,
        fill=(5, 15, 27),
        outline=(28, 52, 72),
        width=1,
    )
    for i in range(1, 8):
        x = int(chart_left + chart_w * i / 8)
        draw.line((x, chart_top + 1, x, chart_bottom - 1), fill=_GRID, width=1)
    for i in range(1, 6):
        y = int(chart_top + chart_h * i / 6)
        draw.line((chart_left + 1, y, chart_right - 1, y), fill=_GRID, width=1)

    level_values = [value for value in [entry, sl, *targets] if isinstance(value, (int, float)) and value > 0]
    lows = [float(item["low"]) for item in candles]
    highs = [float(item["high"]) for item in candles]
    y_min = min(lows + level_values) if level_values else min(lows)
    y_max = max(highs + level_values) if level_values else max(highs)
    span = max(y_max - y_min, max(abs(y_max), 1.0) * 0.0005)
    y_min -= span * 0.09
    y_max += span * 0.09
    span = y_max - y_min

    def y_of(price: float) -> int:
        ratio = (y_max - float(price)) / span
        return int(chart_top + ratio * chart_h)

    count = len(candles)
    step = chart_w / max(count, 1)
    body_w = max(3, min(9, int(step * 0.56)))
    for idx, candle in enumerate(candles):
        x = int(chart_left + (idx + 0.5) * step)
        o, h, l, close = map(float, (candle["open"], candle["high"], candle["low"], candle["close"]))
        color = _UP if close >= o else _DOWN
        y_h, y_l, y_o, y_c = y_of(h), y_of(l), y_of(o), y_of(close)
        draw.line((x, y_h, x, y_l), fill=color, width=1)
        body_top, body_bottom = sorted((y_o, y_c))
        if body_bottom - body_top < 2:
            body_bottom = body_top + 2
        draw.rounded_rectangle(
            (x - body_w // 2, body_top, x + body_w // 2, body_bottom),
            radius=1,
            fill=color,
        )

    level_specs: list[tuple[str, float, tuple[int, int, int]]] = []
    if entry > 0:
        level_specs.append(("ENTRY", entry, _ENTRY))
    if sl > 0:
        level_specs.append(("SL", sl, _SL))
    for idx, value in enumerate(targets[:5], start=1):
        if float(value) > 0:
            level_specs.append((f"TP{idx}", float(value), _TP))

    # Exact canonical levels across the broker chart.
    for label, price, color in level_specs:
        y = max(chart_top + 2, min(chart_bottom - 2, y_of(price)))
        _draw_dashed(draw, (chart_left + 8, y, chart_right - 8, y), color, width=2, dash=7, gap=6)
        draw.text((chart_left + 16, y - 16), label, font=_font(11, True), fill=color)

    # Right rail. Values come from the exact stored signal snapshot used by the caption.
    draw.rounded_rectangle(
        (rail_left, chart_top, rail_right, chart_bottom),
        radius=16,
        fill=(8, 21, 35),
        outline=(29, 55, 76),
        width=1,
    )
    draw.text((rail_left + 20, chart_top + 18), "TRADE LEVELS", font=_font(14, True), fill=(178, 194, 208))
    chip_w = 88
    draw.rounded_rectangle(
        (rail_right - chip_w - 18, chart_top + 12, rail_right - 18, chart_top + 40),
        radius=8,
        fill=(11, 39, 48) if direction_color == _UP else (51, 20, 28),
        outline=direction_color,
        width=1,
    )
    draw.text((rail_right - 18 - chip_w / 2, chart_top + 18), direction or "—",
              font=_font(12, True), fill=direction_color, anchor="ma")

    rail_y = chart_top + 60
    rail_gap = 54
    for label, price, color in level_specs:
        draw.text((rail_left + 20, rail_y), label, font=_font(11, True), fill=color)
        draw.text((rail_right - 20, rail_y - 2), _format_level_price(price, digits),
                  font=_font(17, True), fill=(240, 244, 248), anchor="ra")
        draw.line((rail_left + 20, rail_y + 28, rail_right - 20, rail_y + 28), fill=(25, 47, 64), width=1)
        rail_y += rail_gap

    risk = float(_signal_value(signal, "risk_percent", 0) or 0)
    rr = float(_signal_value(signal, "rr_ratio", 0) or 0)
    meta_y = max(rail_y + 4, chart_bottom - 112)
    draw.text((rail_left + 20, meta_y), "RISK", font=_font(10, True), fill=(132, 151, 169))
    draw.text((rail_left + 20, meta_y + 18), f"{risk:g}%" if risk > 0 else "—", font=_font(14, True), fill=(228, 235, 242))
    draw.text((rail_left + 124, meta_y), "R:R", font=_font(10, True), fill=(132, 151, 169))
    draw.text((rail_left + 124, meta_y + 18), f"1:{rr:g}" if rr > 0 else "—", font=_font(14, True), fill=(228, 235, 242))
    draw.text((rail_left + 206, meta_y), "SOURCE", font=_font(10, True), fill=(132, 151, 169))
    draw.text((rail_left + 206, meta_y + 18), "MT5", font=_font(14, True), fill=_PRICE_TEXT)

    broker_symbol = str(meta.get("broker_symbol") or symbol)
    captured = str(meta.get("captured_at") or "")
    footer = f"BROKER TRUTH  •  {broker_symbol}  •  {timeframe}"
    if captured:
        footer += f"  •  {captured[:19].replace('T', ' ')} UTC"
    draw.text((28, height - 22), footer, font=_font(10, False), fill=(107, 126, 143))
    draw.text((1254, height - 22), _STYLE_VERSION, font=_font(9, False), fill=(71, 91, 108), anchor="ra")

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

