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
_SUPPORTED_TF = {"M1", "M5", "M15", "H1", "D1"}
_MIN_BARS = 24
_MAX_BARS = 120
_MAX_FEED_AGE_SECONDS = 90

_BG = (7, 11, 18)
_PANEL = (11, 18, 29)
_GRID = (36, 48, 64)
_TEXT = (232, 239, 246)
_MUTED = (142, 156, 177)
_UP = (18, 229, 205)
_DOWN = (255, 92, 108)
_ENTRY = (59, 179, 255)
_SL = (255, 92, 108)
_TP = (224, 183, 74)


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


def _draw_dashed(draw: ImageDraw.ImageDraw, xy: tuple[int, int, int, int], fill, width: int = 2, dash: int = 10, gap: int = 7):
    x1, y1, x2, y2 = xy
    if y1 == y2:
        x = x1
        while x < x2:
            draw.line((x, y1, min(x + dash, x2), y2), fill=fill, width=width)
            x += dash + gap
        return
    draw.line(xy, fill=fill, width=width)


def _render_chart(signal: Any, candles: list[dict[str, float]], meta: dict[str, Any], targets: list[float]) -> bytes:
    width, height = 1280, 720
    image = Image.new("RGB", (width, height), _BG)
    draw = ImageDraw.Draw(image)

    left, top, right, bottom = 72, 92, 1115, 650
    chart_w, chart_h = right - left, bottom - top

    code = str(_signal_value(signal, "code", "NEXUS") or "NEXUS")
    direction = str(_signal_value(signal, "direction", "") or "").upper()
    entry = float(_signal_value(signal, "entry_price", 0) or 0)
    sl = float(_signal_value(signal, "stop_loss", 0) or 0)
    symbol_label = str(meta.get("broker_symbol") or meta.get("symbol") or "")
    tf = str(meta.get("timeframe") or "")
    age = meta.get("age_seconds")

    draw.rectangle((0, 0, width, 66), fill=(5, 13, 23))
    draw.text((28, 18), "NEXUS  |  MT5 BROKER FEED", font=_font(23, True), fill=_TEXT)
    draw.text((width - 28, 20), f"{code}  |  {symbol_label}  |  {tf}  |  {direction}", font=_font(18, True), fill=_MUTED, anchor="ra")
    draw.text((28, height - 34), f"Source: MT5 MarketFeed   Freshness: {age:.1f}s" if isinstance(age, (int, float)) else "Source: MT5 MarketFeed", font=_font(15), fill=_MUTED)

    draw.rounded_rectangle((left - 14, top - 14, right + 120, bottom + 14), radius=18, fill=_PANEL, outline=(35, 61, 86), width=2)

    level_values = [value for value in [entry, sl, *targets] if isinstance(value, (int, float)) and value > 0]
    lows = [float(c["low"]) for c in candles]
    highs = [float(c["high"]) for c in candles]
    y_min = min(lows + level_values) if level_values else min(lows)
    y_max = max(highs + level_values) if level_values else max(highs)
    span = max(y_max - y_min, max(abs(y_max), 1.0) * 0.0005)
    y_min -= span * 0.06
    y_max += span * 0.06
    span = y_max - y_min

    def y_of(price: float) -> int:
        ratio = (y_max - price) / span
        return int(top + ratio * chart_h)

    for i in range(6):
        y = int(top + chart_h * i / 5)
        draw.line((left, y, right, y), fill=_GRID, width=1)
        price = y_max - span * i / 5
        digits = meta.get("digits")
        precision = int(digits) if isinstance(digits, int) else (5 if price < 10 else 2)
        draw.text((right + 18, y - 9), f"{price:.{precision}f}", font=_font(14), fill=_MUTED)
    for i in range(7):
        x = int(left + chart_w * i / 6)
        draw.line((x, top, x, bottom), fill=(25, 36, 50), width=1)

    count = len(candles)
    step = chart_w / max(count, 1)
    body_w = max(3, min(10, int(step * 0.58)))
    for idx, candle in enumerate(candles):
        x = int(left + (idx + 0.5) * step)
        o, h, l, c = map(float, (candle["open"], candle["high"], candle["low"], candle["close"]))
        color = _UP if c >= o else _DOWN
        y_h, y_l, y_o, y_c = y_of(h), y_of(l), y_of(o), y_of(c)
        draw.line((x, y_h, x, y_l), fill=color, width=2)
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

    digits = meta.get("digits")
    precision = int(digits) if isinstance(digits, int) else (5 if max(y_max, 0) < 10 else 2)
    for label, price, color in level_specs:
        y = y_of(price)
        _draw_dashed(draw, (left, y, right, y), color, width=2)
        text = f"{label}  {price:.{precision}f}"
        bbox = draw.textbbox((0, 0), text, font=_font(15, True))
        box_w = bbox[2] - bbox[0] + 16
        draw.rounded_rectangle((right - box_w, y - 14, right, y + 14), radius=7, fill=(7, 15, 25), outline=color, width=1)
        draw.text((right - 8, y - 9), text, font=_font(15, True), fill=color, anchor="ra")

    last = candles[-1]
    last_price = float(last["close"])
    last_y = y_of(last_price)
    draw.line((left, last_y, right, last_y), fill=(116, 143, 178), width=1)
    draw.ellipse((right + 8, last_y - 5, right + 18, last_y + 5), fill=_TEXT)

    out = BytesIO()
    image.save(out, format="PNG", optimize=True)
    return out.getvalue()


def ensure_broker_chart_asset(signal: Any) -> dict[str, Any]:
    """Render a broker-truth chart from the existing MT5 MarketFeed candle store.

    This is a reliability fallback for Telegram publication, not a synthetic
    market-data source. It refuses stale/missing/insufficient candles and never
    invents OHLC values. The screenshot-only ChartAgent remains the preferred
    first path; this renderer removes ChartAgent as a single point of failure.
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
                "broker_symbol": meta.get("broker_symbol"),
                "timeframe": meta.get("timeframe"),
                "bars": len(candles),
                "age_seconds": round(float(meta.get("age_seconds") or 0.0), 3),
                "file_path": str(path),
                "bytes": len(raw),
            },
        )
        return {"ok": True, "file_path": str(path), "bytes": len(raw), "bars": len(candles), **meta}
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
                payload={"source": "MT5_MARKET_FEED", "meta": meta},
            )
        except Exception:
            pass
        return {"ok": False, "reason": f"RENDER_ERROR:{exc}", **meta}
