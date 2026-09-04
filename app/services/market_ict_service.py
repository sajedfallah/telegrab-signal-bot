from __future__ import annotations

"""Deterministic ICT-style morning scenarios for NEXUS public editorial.

This module does not issue trade signals. It converts fresh public OHLC data into
conditional 1H context, 15M liquidity/FVG zones and a 5M trigger checklist. The
same Bitunix public futures K-line endpoint is used for BTC and GOLD so the
published reference levels come from one market-data venue.
"""

import asyncio
import html
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx


log = logging.getLogger(__name__)
BITUNIX_KLINE_URL = "https://fapi.bitunix.com/api/v1/futures/market/kline"


@dataclass(frozen=True)
class Candle:
    time: datetime
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class Zone:
    low: float
    high: float


@dataclass(frozen=True)
class IctSnapshot:
    symbol: str
    current: float
    bias: str
    pdh: float
    pdl: float
    equilibrium: float
    swing_high: float
    swing_low: float
    bullish_fvg: Zone | None
    bearish_fvg: Zone | None


def _parse_timestamp(value: object) -> datetime:
    raw = float(value or 0)
    if raw > 10_000_000_000:
        raw /= 1000.0
    return datetime.fromtimestamp(raw, tz=timezone.utc)


def parse_kline_payload(payload: object) -> list[Candle]:
    if not isinstance(payload, dict) or int(payload.get("code", -1)) != 0:
        raise RuntimeError("Bitunix kline response is not successful")
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise RuntimeError("Bitunix kline response has no data list")
    out: list[Candle] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            candle = Candle(
                time=_parse_timestamp(row.get("time")),
                open=float(row.get("open")),
                high=float(row.get("high")),
                low=float(row.get("low")),
                close=float(row.get("close")),
            )
        except Exception:
            continue
        if candle.low <= 0 or candle.high <= 0 or candle.high < candle.low:
            continue
        out.append(candle)
    out.sort(key=lambda x: x.time)
    if len(out) < 10:
        raise RuntimeError("insufficient Bitunix kline history")
    return out


async def fetch_klines(symbol: str, interval: str, limit: int = 200) -> list[Candle]:
    params = {
        "symbol": str(symbol).upper(),
        "interval": interval,
        "limit": max(20, min(int(limit), 200)),
        "type": "LAST_PRICE",
    }
    headers = {"Accept": "application/json", "User-Agent": "NEXUS/0.6.5 ICT-editorial"}
    timeout = httpx.Timeout(10.0)
    async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=True, trust_env=True) as client:
        response = await client.get(BITUNIX_KLINE_URL, params=params)
        response.raise_for_status()
        return parse_kline_payload(response.json())


async def fetch_market_structure(symbol: str) -> tuple[list[Candle], list[Candle], list[Candle]]:
    return tuple(await asyncio.gather(
        fetch_klines(symbol, "1h", 120),
        fetch_klines(symbol, "15m", 180),
        fetch_klines(symbol, "5m", 200),
    ))  # type: ignore[return-value]


def _pivots(candles: list[Candle], width: int = 2) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    highs: list[tuple[int, float]] = []
    lows: list[tuple[int, float]] = []
    if len(candles) < width * 2 + 1:
        return highs, lows
    for i in range(width, len(candles) - width):
        cur = candles[i]
        left = candles[i - width:i]
        right = candles[i + 1:i + width + 1]
        if all(cur.high > x.high for x in left + right):
            highs.append((i, cur.high))
        if all(cur.low < x.low for x in left + right):
            lows.append((i, cur.low))
    return highs, lows


def _structure_bias(candles: list[Candle]) -> str:
    highs, lows = _pivots(candles[-72:])
    if len(highs) >= 2 and len(lows) >= 2:
        hh = highs[-1][1] > highs[-2][1]
        hl = lows[-1][1] > lows[-2][1]
        lh = highs[-1][1] < highs[-2][1]
        ll = lows[-1][1] < lows[-2][1]
        if hh and hl:
            return "BULLISH"
        if lh and ll:
            return "BEARISH"
    return "NEUTRAL"


def _previous_session_bounds(candles: list[Candle], now_utc: datetime, local_timezone: str) -> tuple[float, float]:
    tz = ZoneInfo(local_timezone)
    today = now_utc.astimezone(tz).date()
    grouped: dict[object, list[Candle]] = {}
    for candle in candles:
        day = candle.time.astimezone(tz).date()
        if day < today:
            grouped.setdefault(day, []).append(candle)
    if grouped:
        day = max(grouped)
        rows = grouped[day]
        return max(x.high for x in rows), min(x.low for x in rows)
    rows = candles[-24:]
    return max(x.high for x in rows), min(x.low for x in rows)


def _latest_fvgs(candles: list[Candle]) -> tuple[Zone | None, Zone | None]:
    bullish: Zone | None = None
    bearish: Zone | None = None
    rows = candles[-100:]
    for i in range(2, len(rows)):
        left = rows[i - 2]
        cur = rows[i]
        if cur.low > left.high:
            bullish = Zone(low=left.high, high=cur.low)
        if cur.high < left.low:
            bearish = Zone(low=cur.high, high=left.low)
    return bullish, bearish


def build_snapshot(
    symbol: str,
    h1: list[Candle],
    m15: list[Candle],
    m5: list[Candle],
    *,
    now_utc: datetime,
    local_timezone: str,
) -> IctSnapshot:
    if not h1 or not m15 or not m5:
        raise RuntimeError("market structure requires 1H, 15M and 5M candles")
    pdh, pdl = _previous_session_bounds(h1, now_utc, local_timezone)
    highs, lows = _pivots(m15[-100:])
    swing_high = highs[-1][1] if highs else max(x.high for x in m15[-32:])
    swing_low = lows[-1][1] if lows else min(x.low for x in m15[-32:])
    bull_fvg, bear_fvg = _latest_fvgs(m15)
    return IctSnapshot(
        symbol=str(symbol).upper(),
        current=m5[-1].close,
        bias=_structure_bias(h1),
        pdh=pdh,
        pdl=pdl,
        equilibrium=(pdh + pdl) / 2.0,
        swing_high=swing_high,
        swing_low=swing_low,
        bullish_fvg=bull_fvg,
        bearish_fvg=bear_fvg,
    )


def _fmt(value: float, symbol: str) -> str:
    decimals = 1 if str(symbol).upper().startswith("BTC") else 2
    return f"{value:,.{decimals}f}"


def _zone_text(zone: Zone | None, symbol: str) -> str:
    if zone is None:
        return "—"
    return f"{_fmt(zone.low, symbol)} تا {_fmt(zone.high, symbol)}"


def render_persian_ict(snapshot: IctSnapshot, *, asset_fa: str, now_utc: datetime, local_timezone: str) -> str:
    tz = ZoneInfo(local_timezone)
    date_text = now_utc.astimezone(tz).strftime("%Y/%m/%d")
    bias_fa = {
        "BULLISH": "صعودی",
        "BEARISH": "نزولی",
        "NEUTRAL": "خنثی / رنج",
    }.get(snapshot.bias, "خنثی / رنج")

    if snapshot.bias == "BULLISH":
        long_text = (
            "اولویت با شکار نقدینگی سمت فروش در ناحیه Discount یا FVG صعودی 15M است؛ "
            "ورود فقط پس از Sweep و سپس MSS/CHOCH صعودی در 5M و Retest یک FVG جدید."
        )
        short_text = (
            "فقط در صورت Sweep نقدینگی بالای Swing High/PDH و شکست معتبر ساختار 5M به سمت پایین؛ "
            "بدون MSS نزولی، فروش خلاف Bias انجام نشود."
        )
    elif snapshot.bias == "BEARISH":
        long_text = (
            "فقط در صورت Sweep نقدینگی زیر Swing Low/PDL و شکست معتبر ساختار 5M به سمت بالا؛ "
            "بدون MSS صعودی، خرید خلاف Bias انجام نشود."
        )
        short_text = (
            "اولویت با شکار نقدینگی سمت خرید در ناحیه Premium یا FVG نزولی 15M است؛ "
            "ورود فقط پس از Sweep و سپس MSS/CHOCH نزولی در 5M و Retest یک FVG جدید."
        )
    else:
        long_text = (
            "پس از Sweep سمت فروش در حوالی PDL/Swing Low یا FVG صعودی 15M، منتظر MSS صعودی + "
            "Displacement و Retest در 5M بمانید."
        )
        short_text = (
            "پس از Sweep سمت خرید در حوالی PDH/Swing High یا FVG نزولی 15M، منتظر MSS نزولی + "
            "Displacement و Retest در 5M بمانید."
        )

    lines = [
        f"<b>📐 تحلیل و سناریوی روزانه {html.escape(asset_fa)} | ICT</b>",
        f"📅 {date_text}",
        "",
        f"💵 قیمت مرجع: <b>{_fmt(snapshot.current, snapshot.symbol)}</b>",
        f"🧭 Bias ساختار 1H: <b>{bias_fa}</b>",
        "",
        "<b>🔑 سطوح نقدینگی و Context</b>",
        f"• PDH: <b>{_fmt(snapshot.pdh, snapshot.symbol)}</b>",
        f"• PDL: <b>{_fmt(snapshot.pdl, snapshot.symbol)}</b>",
        f"• Equilibrium 50%: <b>{_fmt(snapshot.equilibrium, snapshot.symbol)}</b>",
        f"• 15M Swing High: <b>{_fmt(snapshot.swing_high, snapshot.symbol)}</b>",
        f"• 15M Swing Low: <b>{_fmt(snapshot.swing_low, snapshot.symbol)}</b>",
        f"• Bullish FVG 15M: <b>{_zone_text(snapshot.bullish_fvg, snapshot.symbol)}</b>",
        f"• Bearish FVG 15M: <b>{_zone_text(snapshot.bearish_fvg, snapshot.symbol)}</b>",
        "",
        "<b>🟢 سناریوی Long</b>",
        long_text,
        "",
        "<b>🔴 سناریوی Short</b>",
        short_text,
        "",
        "<b>🎯 Trigger ورود 5M</b>",
        "Liquidity Sweep → MSS/CHOCH → Displacement → FVG Retest",
        "",
        "⚠️ این تحلیل سناریومحور است؛ تا تشکیل Trigger معتبر 5M ورود فوری محسوب نمی‌شود.",
    ]
    return "\n".join(lines)


async def build_daily_ict_message(
    *,
    symbol: str,
    asset_fa: str,
    now_utc: datetime,
    local_timezone: str,
) -> str:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            h1, m15, m5 = await fetch_market_structure(symbol)
            snapshot = build_snapshot(
                symbol,
                h1,
                m15,
                m5,
                now_utc=now_utc,
                local_timezone=local_timezone,
            )
            return render_persian_ict(
                snapshot,
                asset_fa=asset_fa,
                now_utc=now_utc,
                local_timezone=local_timezone,
            )
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                await asyncio.sleep(0.8 * (attempt + 1))
    raise RuntimeError(f"ICT market data unavailable for {symbol}: {last_error}")
