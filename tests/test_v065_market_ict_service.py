from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services import market_ict_service as ict


def _candles(start: datetime, count: int, minutes: int, base: float, step: float) -> list[ict.Candle]:
    rows: list[ict.Candle] = []
    price = base
    for i in range(count):
        open_price = price
        close = price + step
        high = max(open_price, close) + abs(step) * 0.5 + 1
        low = min(open_price, close) - abs(step) * 0.5 - 1
        rows.append(
            ict.Candle(
                opened_at=start + timedelta(minutes=minutes * i),
                open=open_price,
                high=high,
                low=low,
                close=close,
            )
        )
        price = close
    return rows


def test_parse_ohlc_payload_keeps_only_closed_bars_and_sorts():
    payload = {
        "bars": [
            {
                "openTime": "2026-09-04T02:00:00Z",
                "open": 102,
                "high": 104,
                "low": 101,
                "close": 103,
                "isOpen": False,
            },
            {
                "openTime": "2026-09-04T01:00:00Z",
                "open": 100,
                "high": 103,
                "low": 99,
                "close": 102,
                "isOpen": False,
            },
        ] * 10
        + [
            {
                "openTime": "2026-09-04T03:00:00Z",
                "open": 103,
                "high": 105,
                "low": 102,
                "close": 104,
                "isOpen": True,
            }
        ]
    }
    rows = ict.parse_ohlc_payload(payload)
    assert len(rows) == 20
    assert rows[0].opened_at <= rows[-1].opened_at
    assert all(x.opened_at.hour != 3 for x in rows)


def test_snapshot_and_render_include_1h_15m_5m_ict_contract():
    now = datetime(2026, 9, 4, 4, 30, tzinfo=timezone.utc)
    start = now - timedelta(days=4)
    h1 = _candles(start, 96, 60, 4400.0, 0.7)
    m15 = _candles(now - timedelta(hours=40), 160, 15, 4440.0, 0.15)
    m5 = _candles(now - timedelta(hours=16), 192, 5, 4460.0, 0.05)

    snap = ict.build_snapshot(
        "XAUUSD",
        h1,
        m15,
        m5,
        now_utc=now,
        local_timezone="Asia/Tehran",
    )
    text = ict.render_persian_ict(
        snap,
        asset_fa="طلای جهانی (XAU/USD)",
        now_utc=now,
        local_timezone="Asia/Tehran",
    )

    assert snap.pdh is not None and snap.pdl is not None and snap.pdh > snap.pdl
    assert snap.current == m5[-1].close
    assert "تحلیل و سناریوی روزانه طلای جهانی" in text
    assert "Bias ساختار 1H" in text
    assert "Liquidity Pools" in text
    assert "Bullish FVG" in text
    assert "Bearish FVG" in text
    assert "Bullish OB" in text
    assert "Bearish OB" in text
    assert "5M — Entry Trigger" in text
    assert "سناریوی اصلی" in text
    assert "سناریوی جایگزین" in text
    assert len(text) < 4096


def test_render_keeps_primary_and_alternative_scenarios_for_bitcoin():
    now = datetime(2026, 9, 4, 4, 30, tzinfo=timezone.utc)
    snap = ict.IctSnapshot(
        symbol="BTCUSD",
        current=80000.0,
        bias="BULLISH",
        structure_note="ساختار 1H صعودی است.",
        pdh=81000.0,
        pdl=77000.0,
        buy_liquidity=80500.0,
        sell_liquidity=78500.0,
        bullish_fvg=ict.Zone(78600.0, 78900.0),
        bearish_fvg=ict.Zone(80300.0, 80600.0),
        bullish_ob=ict.Zone(78700.0, 79000.0),
        bearish_ob=ict.Zone(80200.0, 80500.0),
        trigger_state="در 5M فعلاً Sweep + MSS معتبر همزمان دیده نمی‌شود.",
    )
    text = ict.render_persian_ict(
        snap,
        asset_fa="بیت‌کوین (BTC/USD)",
        now_utc=now,
        local_timezone="Asia/Tehran",
    )
    assert "صعودی" in text
    assert "سناریوی اصلی" in text
    assert "سناریوی جایگزین" in text
    assert "PDH" in text and "PDL" in text
    assert "BTC/USD" in text
