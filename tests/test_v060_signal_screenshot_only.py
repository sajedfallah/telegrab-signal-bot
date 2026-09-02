from pathlib import Path


def test_ea_screenshot_only_at_signal_issue():
    p = Path(__file__).resolve().parents[1] / "mt5" / "NEXUS_AutoTrade" / "NEXUS_AutoTrade.mq5"
    s = p.read_text(encoding="utf-8")
    assert s.count("CaptureChartBase64(") == 2  # declaration + signal issuance call
    assert 'CaptureChartBase64(symbol,"SIGNAL")' in s
    assert 'CaptureChartBase64(symbol,"PENDING")' not in s
    assert 'CaptureChartBase64(symbol,event_name)' not in s


def test_backend_lifecycle_has_no_chart_pipeline():
    p = Path(__file__).resolve().parents[1] / "app" / "main.py"
    s = p.read_text(encoding="utf-8")
    fn = s[s.index('async def _process_mt5_trade_event'):s.index('async def autotrade_notification_worker')]
    assert 'build_chart_frame' not in fn
    assert 'send_photo' not in fn
    assert 'payload.get("chart_path")' not in fn
