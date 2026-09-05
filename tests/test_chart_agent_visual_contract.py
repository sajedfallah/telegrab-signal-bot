from pathlib import Path


SOURCE = Path("mt5/NEXUS_ChartAgent/NEXUS_ChartAgent.mq5")


def _src() -> str:
    return SOURCE.read_text(encoding="utf-8-sig")


def test_chart_agent_uses_approved_template_and_sync_barrier():
    src = _src()
    assert 'InpChartTemplate = "NEXUS_Screenshot.tpl"' in src
    assert "WaitChartInstanceReady" in src
    assert "ChartApplyTemplate(chart_id,InpChartTemplate)" in src
    assert "CHART_TEMPLATE_SYNC_FAILED_" in src
    assert "ChartGetInteger(chart_id,CHART_COLOR_BACKGROUND" in src
    assert "ChartGetInteger(chart_id,CHART_SHOW_GRID" in src
    assert 'NEXUS_CHART_VISUAL_PROFILE "approved-right-ray-v1"' in src


def test_trade_levels_start_at_last_candle_edge_and_extend_right_only():
    src = _src()
    assert "LastCandleRightEdge" in src
    assert "datetime level_start=LastCandleRightEdge(broker_symbol,tf);" in src
    assert "OBJ_TREND" in src
    assert "OBJPROP_RAY_LEFT,false" in src
    assert "OBJPROP_RAY_RIGHT,true" in src
    assert "OBJ_HLINE" not in src
    assert 'prefix+"ENTRY.RAY",level_start' in src
    assert 'prefix+"SL.RAY",level_start' in src
    assert 'level_start,tf,targets[i]' in src


def test_approved_visual_profile_has_compact_right_side_labels():
    src = _src()
    assert "InpLabelFontSize = 8" in src
    assert "InpLabelNameWidth = 82" in src
    assert "InpLabelPriceWidth = 64" in src
    assert "InpLabelHeight = 18" in src
    assert "InpLabelRightMargin = 72" in src
    assert "OBJ_RECTANGLE_LABEL" in src
    assert "CORNER_RIGHT_UPPER" in src
    assert '"Entry Zone"' in src
    assert '"Stop Loss"' in src
    assert '"Exit Zone "+IntegerToString(i+1)' in src
    assert "STYLE_DASH,InpExitLineWidth" in src
    assert "C'0,174,255'" in src
    assert "C'255,68,84'" in src
    assert "C'44,214,85'" in src


def test_chart_agent_remains_screenshot_only():
    src = _src()
    assert "ChartScreenShot(" in src
    assert "void OnTick()" in src
    assert "screenshot-only and never trades" in src
    for forbidden in ("OrderSend(", "PositionOpen(", "Buy(", "Sell("):
        assert forbidden not in src
