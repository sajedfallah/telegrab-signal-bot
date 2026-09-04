from __future__ import annotations

"""Deterministic ICT-style morning scenarios for NEXUS public editorial.

This module does not issue trade signals. It converts fresh closed OHLC bars into
conditional 1H context, 15M liquidity/FVG/Order-Block areas and a 5M trigger
state. Public text intentionally never exposes the internal market-data source.
"""

import asyncio
import html
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx


log = logging.getLogger(__name__)
_OHLC_BASE = "https://biquote.io/api"


@dataclass(frozen=True)
class Candle:
    opened_at: datetime
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
    structure_note: str
    pdh: float | None
    pdl: float | None
    buy_liquidity: float
    sell_liquidity: float
    bullish_fvg: Zone | None
    bearish_fvg: Zone | None
    bullish_ob: Zone | None
    bearish_ob: Zone | None
    trigger_state: str


def _parse_time(value: Any) -> datetime:
    text = str(value or "").strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_ohlc_payload(payload: Any) -> list[Candle]:
    rows = payload.get("bars") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise RuntimeError("OHLC response has no bars list")
    out: list[Candle] = []
    for row in rows:
        if not isinstance(row, dict) or bool(row.get("isOpen")):
            continue
        try:
            candle = Candle(
                opened_at=_parse_time(row.get("openTime")),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
            )
        except (KeyError, TypeError, ValueError):
            continue
        if candle.high < candle.low or candle.low <= 0:
            continue
        out.append(candle)
    out.sort(key=lambda x: x.opened_at)
    if len(out) < 20:
        raise RuntimeError(f"insufficient closed OHLC history: {len(out)}")
    return out


async def fetch_ohlc(symbol: str, interval: str, *, limit: int = 200, timeout_seconds: int = 12) -> list[Candle]:
    url = f"{_OHLC_BASE}/{str(symbol).upper()}/ohlc"
    params = {"interval": interval, "limit": max(20, min(1000, int(limit)))}
    headers = {"Accept": "application/json", "User-Agent": "NEXUS/0.6.5 market-ict"}
    timeout = httpx.Timeout(max(4.0, float(timeout_seconds)))
    async with httpx.AsyncClient(
        timeout=timeout,
        headers=headers,
        follow_redirects=True,
        trust_env=True,
    ) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        return parse_ohlc_payload(response.json())


async def fetch_market_structure(symbol: str) -> tuple[list[Candle], list[Candle], list[Candle]]:
    h1, m15, m5 = await asyncio.gather(
        fetch_ohlc(symbol, "1h", limit=140),
        fetch_ohlc(symbol, "15m", limit=200),
        fetch_ohlc(symbol, "5m", limit=200),
    )
    return h1, m15, m5


def _pivots(candles: list[Candle], width: int = 2) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    highs: list[tuple[int, float]] = []
    lows: list[tuple[int, float]] = []
    if len(candles) < width * 2 + 1:
        return highs, lows
    for i in range(width, len(candles) - width):
        cur = candles[i]
        window = candles[i - width : i + width + 1]
        if cur.high == max(x.high for x in window):
            highs.append((i, cur.high))
        if cur.low == min(x.low for x in window):
            lows.append((i, cur.low))
    return highs, lows


def _structure(candles: list[Candle]) -> tuple[str, str]:
    rows = candles[-80:]
    highs, lows = _pivots(rows)
    if len(highs) >= 2 and len(lows) >= 2:
        h1, h2 = highs[-2][1], highs[-1][1]
        l1, l2 = lows[-2][1], lows[-1][1]
        if h2 > h1 and l2 > l1:
            return "BULLISH", "ساختار 1H صعودی است؛ آخرین سوئینگ‌ها Higher High / Higher Low ساخته‌اند."
        if h2 < h1 and l2 < l1:
            return "BEARISH", "ساختار 1H نزولی است؛ آخرین سوئینگ‌ها Lower High / Lower Low ساخته‌اند."
    recent = rows[-24:]
    midpoint = (max(x.high for x in recent) + min(x.low for x in recent)) / 2.0
    if rows[-1].close > midpoint and rows[-1].close >= rows[-6].close:
        return "BULLISH", "ساختار 1H تمایل صعودی دارد، اما توالی سوئینگ هنوز کاملاً یک‌طرفه نیست."
    if rows[-1].close < midpoint and rows[-1].close <= rows[-6].close:
        return "BEARISH", "ساختار 1H تمایل نزولی دارد، اما توالی سوئینگ هنوز کاملاً یک‌طرفه نیست."
    return "NEUTRAL", "ساختار 1H خنثی/رنج است؛ اولویت با واکنش قیمت به نقدینگی دو سمت محدوده است."


def _previous_day_bounds(candles: list[Candle], now_utc: datetime, local_timezone: str) -> tuple[float | None, float | None]:
    tz = ZoneInfo(local_timezone)
    today = now_utc.astimezone(tz).date()
    grouped: dict[object, list[Candle]] = {}
    for candle in candles:
        day = candle.opened_at.astimezone(tz).date()
        if day < today:
            grouped.setdefault(day, []).append(candle)
    if not grouped:
        return None, None
    day = max(grouped)
    rows = grouped[day]
    return max(x.high for x in rows), min(x.low for x in rows)


def _liquidity(candles: list[Candle], pdh: float | None, pdl: float | None) -> tuple[float, float]:
    rows = candles[-80:]
    current = rows[-1].close
    highs, lows = _pivots(rows)
    buy_candidates = [x[1] for x in highs if x[1] > current]
    sell_candidates = [x[1] for x in lows if x[1] < current]
    if pdh is not None and pdh > current:
        buy_candidates.append(pdh)
    if pdl is not None and pdl < current:
        sell_candidates.append(pdl)
    buy = min(buy_candidates) if buy_candidates else max(x.high for x in rows[-32:])
    sell = max(sell_candidates) if sell_candidates else min(x.low for x in rows[-32:])
    return buy, sell


def _latest_fvgs(candles: list[Candle]) -> tuple[Zone | None, Zone | None]:
    bullish: Zone | None = None
    bearish: Zone | None = None
    rows = candles[-100:]
    for i in range(len(rows) - 2):
        left, right = rows[i], rows[i + 2]
        if left.high < right.low:
            bullish = Zone(left.high, right.low)
        if left.low > right.high:
            bearish = Zone(right.high, left.low)
    return bullish, bearish


def _latest_order_blocks(candles: list[Candle]) -> tuple[Zone | None, Zone | None]:
    rows = candles[-60:]
    if len(rows) < 10:
        return None, None
    ranges = [max(0.0, x.high - x.low) for x in rows[:-1]]
    avg_range = sum(ranges) / len(ranges) if ranges else 0.0
    bullish: Zone | None = None
    bearish: Zone | None = None
    for i in range(1, len(rows)):
        cur, prev = rows[i], rows[i - 1]
        displacement = avg_range > 0 and (cur.high - cur.low) >= avg_range * 1.35
        if displacement and cur.close > cur.open and prev.close < prev.open:
            bullish = Zone(prev.low, prev.high)
        if displacement and cur.close < cur.open and prev.close > prev.open:
            bearish = Zone(prev.low, prev.high)
    return bullish, bearish


def _trigger_state(candles: list[Candle]) -> str:
    if len(candles) < 16:
        return "برای ورود، Liquidity Sweep و سپس MSS/CHOCH معتبر در 5M لازم است."
    prior = candles[-14:-2]
    penultimate, last = candles[-2], candles[-1]
    prior_high = max(x.high for x in prior)
    prior_low = min(x.low for x in prior)
    bull_sweep = penultimate.low < prior_low and penultimate.close > prior_low
    bear_sweep = penultimate.high > prior_high and penultimate.close < prior_high
    bull_mss = last.close > max(x.high for x in candles[-7:-1])
    bear_mss = last.close < min(x.low for x in candles[-7:-1])
    if bull_sweep and bull_mss:
        return "Sweep سمت فروش + MSS صعودی 5M دیده می‌شود؛ فقط Retest ناحیه معتبر برای ورود بررسی شود."
    if bear_sweep and bear_mss:
        return "Sweep سمت خرید + MSS نزولی 5M دیده می‌شود؛ فقط Retest ناحیه معتبر برای ورود بررسی شود."
    if bull_sweep:
        return "Sweep سمت فروش دیده شده، اما MSS صعودی 5M هنوز تأیید نشده است."
    if bear_sweep:
        return "Sweep سمت خرید دیده شده، اما MSS نزولی 5M هنوز تأیید نشده است."
    return "در 5M فعلاً Sweep + MSS معتبر همزمان دیده نمی‌شود؛ ورود بدون Trigger انجام نشود."


def build_snapshot(
    symbol: str,
    h1: list[Candle],
    m15: list[Candle],
    m5: list[Candle],
    *,
    now_utc: datetime,
    local_timezone: str,
) -> IctSnapshot:
    if min(len(h1), len(m15), len(m5)) < 20:
        raise RuntimeError("market structure requires enough 1H, 15M and 5M candles")
    bias, note = _structure(h1)
    pdh, pdl = _previous_day_bounds(h1, now_utc, local_timezone)
    buy, sell = _liquidity(m15, pdh, pdl)
    bull_fvg, bear_fvg = _latest_fvgs(m15)
    bull_ob, bear_ob = _latest_order_blocks(m15)
    return IctSnapshot(
        symbol=str(symbol).upper(),
        current=m5[-1].close,
        bias=bias,
        structure_note=note,
        pdh=pdh,
        pdl=pdl,
        buy_liquidity=buy,
        sell_liquidity=sell,
        bullish_fvg=bull_fvg,
        bearish_fvg=bear_fvg,
        bullish_ob=bull_ob,
        bearish_ob=bear_ob,
        trigger_state=_trigger_state(m5),
    )


def _fmt(value: float | None, symbol: str) -> str:
    if value is None:
        return "—"
    decimals = 1 if str(symbol).upper().startswith("BTC") else 2
    return f"{value:,.{decimals}f}"


def _zone_text(zone: Zone | None, symbol: str) -> str:
    if zone is None:
        return "—"
    return f"{_fmt(zone.low, symbol)} تا {_fmt(zone.high, symbol)}"


def render_persian_ict(snapshot: IctSnapshot, *, asset_fa: str, now_utc: datetime, local_timezone: str) -> str:
    tz = ZoneInfo(local_timezone)
    date_text = now_utc.astimezone(tz).strftime("%Y/%m/%d")
    bias_fa = {"BULLISH": "صعودی", "BEARISH": "نزولی", "NEUTRAL": "خنثی / رنج"}.get(
        snapshot.bias, "خنثی / رنج"
    )

    if snapshot.bias == "BULLISH":
        primary = (
            f"سناریوی اصلی LONG: برداشت نقدینگی سمت فروش نزدیک {_fmt(snapshot.sell_liquidity, snapshot.symbol)} "
            "یا ورود به Discount/FVG صعودی 15M، سپس MSS/CHOCH صعودی و Retest معتبر در 5M. "
            f"هدف اولیه نقدینگی سمت خرید حوالی {_fmt(snapshot.buy_liquidity, snapshot.symbol)} است."
        )
        alternative = (
            f"SHORT فقط اگر بالای {_fmt(snapshot.buy_liquidity, snapshot.symbol)} نقدینگی جمع شود و "
            "Displacement نزولی همراه با شکست ساختار 5M شکل بگیرد."
        )
    elif snapshot.bias == "BEARISH":
        primary = (
            f"سناریوی اصلی SHORT: برداشت نقدینگی سمت خرید نزدیک {_fmt(snapshot.buy_liquidity, snapshot.symbol)} "
            "یا ورود به Premium/FVG نزولی 15M، سپس MSS/CHOCH نزولی و Retest معتبر در 5M. "
            f"هدف اولیه نقدینگی سمت فروش حوالی {_fmt(snapshot.sell_liquidity, snapshot.symbol)} است."
        )
        alternative = (
            f"LONG فقط اگر زیر {_fmt(snapshot.sell_liquidity, snapshot.symbol)} نقدینگی جمع شود و "
            "Displacement صعودی همراه با بازپس‌گیری ساختار 5M شکل بگیرد."
        )
    else:
        primary = (
            f"LONG پس از Sweep زیر {_fmt(snapshot.sell_liquidity, snapshot.symbol)} + MSS صعودی 5M؛ "
            f"هدف نقدینگی بالای {_fmt(snapshot.buy_liquidity, snapshot.symbol)}."
        )
        alternative = (
            f"SHORT پس از Sweep بالای {_fmt(snapshot.buy_liquidity, snapshot.symbol)} + MSS نزولی 5M؛ "
            f"هدف نقدینگی پایین {_fmt(snapshot.sell_liquidity, snapshot.symbol)}."
        )

    lines = [
        f"<b>📐 تحلیل و سناریوی روزانه {html.escape(asset_fa)} | ICT</b>",
        f"📅 {date_text}",
        "",
        f"💵 قیمت مرجع: <b>{_fmt(snapshot.current, snapshot.symbol)}</b>",
        f"🧭 Bias ساختار 1H: <b>{bias_fa}</b>",
        f"{html.escape(snapshot.structure_note)}",
        "",
        "<b>🔑 Liquidity Pools</b>",
        f"• Buy-side Liquidity: <b>{_fmt(snapshot.buy_liquidity, snapshot.symbol)}</b>",
        f"• Sell-side Liquidity: <b>{_fmt(snapshot.sell_liquidity, snapshot.symbol)}</b>",
        f"• PDH: <b>{_fmt(snapshot.pdh, snapshot.symbol)}</b> | PDL: <b>{_fmt(snapshot.pdl, snapshot.symbol)}</b>",
        "",
        "<b>📦 15M — FVG / Order Block</b>",
        f"• Bullish FVG: <b>{_zone_text(snapshot.bullish_fvg, snapshot.symbol)}</b>",
        f"• Bearish FVG: <b>{_zone_text(snapshot.bearish_fvg, snapshot.symbol)}</b>",
        f"• Bullish OB: <b>{_zone_text(snapshot.bullish_ob, snapshot.symbol)}</b>",
        f"• Bearish OB: <b>{_zone_text(snapshot.bearish_ob, snapshot.symbol)}</b>",
        "",
        f"<b>🎯 5M — Entry Trigger</b>\n{html.escape(snapshot.trigger_state)}",
        "",
        f"<b>🟢 سناریوی اصلی</b>\n{html.escape(primary)}",
        "",
        f"<b>⚪ سناریوی جایگزین</b>\n{html.escape(alternative)}",
        "",
        "⚠️ این تحلیل نقشه سناریویی روز است؛ ورود فقط پس از تأیید ساختاری 5M و مدیریت ریسک انجام شود.",
    ]
    text = "\n".join(lines)
    if len(text) > 4000:
        raise RuntimeError("ICT message exceeds Telegram safe length")
    return text


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
