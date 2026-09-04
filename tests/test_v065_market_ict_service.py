from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services import market_ict_service as ict


def _candles(start: datetime, count: int, minutes: int, base: float, step: float) -> list[ict.Candle]:
    rows = []
    price = base
    for i in range(count):
        open_price = price
        close = price + step
        high = max(open_price, close) + abs(step) * 0.5 + 1
        low = min(open_price, close) - abs(step) * 0.5 - 1
        rows.append(
            ict.Candle(
                time=start + timedelta(minutes=minutes * i),
                open=open_price,
                high=high,
                low=low,
                close=close,
            )
        )
        price = close
    return rows


def test_parse_bitunix_kline_payload_sorts_and_parses_milliseconds():
    payload = {
        "code": 0,
        "data": [
            {"time": 1725429600000, "open": "102", "high": "104", "low": "101", "close": "103"},
            {"time": 1725426000000, "open": "100", "high": "103", "low": "99", "close": "102"},
        ] * 5,
    }
    rows = ict.parse_kline_payload(payload)
    assert len(rows) == 10
    assert rows[0].time <= rows[-1].time
    assert rows[-1].close in {102.0, 103.0}


def test_snapshot_and_render_include_1h_15m_5m_ict_contract():
    now = datetime(2026, 9, 4, 4, 30, tzinfo=timezone.utc)
    start = now - timedelta(days=4)
    h1 = _candles(start, 96, 60, 4400.0, 0.7)
    m15 = _candles(now - timedelta(hours=40), 160, 15, 4440.0, 0.15)
    m5 = _candles(now - timedelta(hours=16), 192, 5, 4460.0, 0.05)

    snap = ict.build_snapshot(
        "XAUUSDT",
        h1,
        m15,
        m5,
        now_utc=now,
        local_timezone="Asia/Tehran",
    )
    text = ict.render_persian_ict(
        snap,
        asset_fa="طلای جهانی",
        now_utc=now,
        local_timezone="Asia/Tehran",
    )

    assert snap.pdh > snap.pdl
    assert snap.current == m5[-1].close
    assert "تحلیل و سناریوی روزانه طلای جهانی" in text
    assert "Bias ساختار 1H" in text
    assert "Bullish FVG 15M" in text
    assert "Bearish FVG 15M" in text
    assert "Trigger ورود 5M" in text
    assert "Liquidity Sweep" in text
    assert "MSS/CHOCH" in text
    assert "ورود فوری" in text


def test_render_keeps_long_and_short_scenarios_even_when_bias_is_bullish():
    now = datetime(2026, 9, 4, 4, 30, tzinfo=timezone.utc)
    snap = ict.IctSnapshot(
        symbol="BTCUSDT",
        current=80000.0,
        bias="BULLISH",
        pdh=81000.0,
        pdl=77000.0,
        equilibrium=79000.0,
        swing_high=80500.0,
        swing_low=78500.0,
        bullish_fvg=ict.Zone(78600.0, 78900.0),
        bearish_fvg=ict.Zone(80300.0, 80600.0),
    )
    text = ict.render_persian_ict(
        snap,
        asset_fa="بیت‌کوین",
        now_utc=now,
        local_timezone="Asia/Tehran",
    )
    assert "صعودی" in text
    assert "سناریوی Long" in text
    assert "سناریوی Short" in text
    assert "PDH" in text and "PDL" in text
