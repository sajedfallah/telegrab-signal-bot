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
    assert 'NEXUS_CHART_VISUAL_PROFILE "approved-inline-level-v2"' in src


def test_trade_levels_start_at_last_candle_edge_and_extend_right_only():
    src = _src()
    assert "LastCandleRightEdge" in src
    assert "datetime level_start=LastCandleRightEdge(broker_symbol,tf);" in src
    assert "datetime label_reference=level_start;" in src
    assert "OBJ_TREND" in src
    assert "OBJPROP_RAY_LEFT,false" in src
    assert "OBJPROP_RAY_RIGHT,true" in src
    assert "OBJ_HLINE" not in src
    assert 'prefix+"ENTRY.RAY",level_start' in src
    assert 'prefix+"SL.RAY",level_start' in src
    assert 'level_start,tf,targets[i]' in src


def test_approved_visual_profile_has_compact_inline_labels():
    src = _src()
    assert "InpLabelFontSize = 8" in src
    assert "InpLabelNameWidth = 46" in src
    assert "InpLabelPriceWidth = 64" in src
    assert "InpLabelHeight = 18" in src
    assert "InpLabelRightMargin = 72" in src
    assert "OBJ_RECTANGLE_LABEL" in src
    assert "CORNER_RIGHT_UPPER" in src
    assert 'entry_color,"Entry",digits' in src
    assert 'sl_color,"SL",digits' in src
    assert 'string caption="TP"+IntegerToString(i+1);' in src
    assert '"Entry Zone"' not in src
    assert '"Stop Loss"' not in src
    assert '"Exit Zone "' not in src
    assert "STYLE_DASH,InpExitLineWidth" in src
    assert "C'0,174,255'" in src
    assert "C'255,68,84'" in src
    assert "C'44,214,85'" in src


def test_inline_tags_are_pixel_centered_on_their_price_lines():
    src = _src()
    assert "int center_y=y;" in src
    assert "int top=center_y-height/2;" in src
    assert "if(top<1 || top+height>(int)chart_height-1)" in src
    assert src.count("OBJPROP_ANCHOR,ANCHOR_CENTER") >= 2
    assert src.count("OBJPROP_YDISTANCE,center_y") >= 2
    assert "OBJPROP_YDISTANCE,top+1" not in src
    assert "ANCHOR_RIGHT_UPPER" not in src
    assert "OBJPROP_COLOR,tag_background" in src


def test_chart_agent_remains_screenshot_only():
    src = _src()
    assert "ChartScreenShot(" in src
    assert "void OnTick()" in src
    assert "screenshot-only and never trades" in src
    for forbidden in ("OrderSend(", "PositionOpen(", "Buy(", "Sell("):
        assert forbidden not in src


def test_trade_level_scale_is_fixed_and_does_not_reject_transient_visible_zeroes():
    """MT5 may return CHART_PRICE_MIN/MAX=0 while a template redraws.

    The capture must validate the fixed-scale properties it explicitly set,
    rather than making a false-negative decision from that transient state.
    """
    src = _src()
    assert "ConfigureTradeLevelScale" in src
    assert "CHART_SCALEFIX" in src
    assert "CHART_FIXED_MIN" in src
    assert "CHART_FIXED_MAX" in src
    assert "TRADE_LEVEL_SCALE_VERIFY_FAILED" in src
    assert "visible_range_valid" in src
    assert "RANGE_VERIFY_FAILED" not in src
    assert "ConfigureTradeLevelScale(chart_id,broker_symbol,entry,sl,targets,scale_error)" in src
