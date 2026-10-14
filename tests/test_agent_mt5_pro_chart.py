import io
from datetime import datetime, timezone
from PIL import Image

from app.agent_system.chart_renderer import render_ict_chart
from app.agent_system.contracts import MarketSnapshot


def test_pro_chart_renders_valid_png_with_zones_and_time_axis():
    rows = tuple({
        "time": 1760000000 + i * 60, "open": 100 + i * 0.01,
        "close": 100 + i * 0.01 + (0.09 if i % 2 else -0.07),
        "high": 100 + i * 0.01 + 0.22,
        "low": 100 + i * 0.01 - 0.20,
    } for i in range(75))
    snap = MarketSnapshot(snapshot_id="pro-chart-test",symbol="XAUUSD",
        as_of=datetime.now(timezone.utc),source="test",
        timeframes={"M1": rows},bid=100.5,ask=100.7,data_freshness_ms=0)
    assessment = {"evidence": ["M1 bullish FVG 100.2-100.3",
                               "M1 bearish OB 100.4-100.8"]}
    png=render_ict_chart(snap,assessment,timeframe="M1")
    with Image.open(io.BytesIO(png)) as image:
        assert image.size == (1600,900)
        assert image.format == "PNG"


def test_pro_chart_without_timestamp_still_renders():
    rows=tuple({"open":100,"high":101,"low":99,"close":100.5} for _ in range(25))
    snap=MarketSnapshot(snapshot_id="pro-chart-no-time",symbol="XAUUSD",
        as_of=datetime.now(timezone.utc),source="test",
        timeframes={"M5":rows},bid=100.4,ask=100.6,data_freshness_ms=0)
    assert render_ict_chart(snap,{"evidence":[]},timeframe="M5").startswith(b"\x89PNG\r\n\x1a\n")


def test_pro_chart_does_not_draw_full_width_yellow_quote_line():
    from PIL import Image
    rows=tuple({"time":1760000000+i*60,"open":100+i*.01,"close":100+i*.01+.03,
                "high":100+i*.01+.2,"low":100+i*.01-.2} for i in range(70))
    snap=MarketSnapshot(snapshot_id="price-badge-only",symbol="XAUUSD",
        as_of=datetime.now(timezone.utc),source="test",timeframes={"M1":rows},
        bid=100.49,ask=100.51,data_freshness_ms=0)
    with Image.open(io.BytesIO(render_ict_chart(snap,{"evidence":[]},timeframe="M1"))) as im:
        # Full-width yellow line formerly crossed the chart at x=80.
        lo,hi=100-.2,(100+69*.01+.23)
        span=hi-lo
        pad=span*.14
        y=717-round(((100.5-(lo-pad))/(span+2*pad))*(717-112))
        assert im.getpixel((78,y)) != (235,200,90)
