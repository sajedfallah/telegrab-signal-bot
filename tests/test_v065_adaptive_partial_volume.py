from pathlib import Path
import math


ROOT = Path(__file__).resolve().parents[1]
TM = (
    ROOT
    / "mt5/NEXUS_AutoTrade/Include/TradeManager.mqh"
).read_text(encoding="utf-8")


def adapt(before: float, requested: float, minimum: float, step: float):
    eps = max(step * 0.1, 1e-8)

    if requested >= before - eps:
        return before

    max_partial = before - minimum

    if max_partial + eps < minimum:
        return None

    units = math.floor(requested / step + 0.5)
    close = round(units * step, 8)

    if close < minimum:
        close = minimum

    if close > max_partial:
        close = math.floor(max_partial / step + 1e-9) * step

    close = round(close, 8)

    if close < minimum:
        return None

    if before - close + eps < minimum:
        return None

    return close


def test_live_xau_case_002_lot_30pct_becomes_001():
    assert adapt(0.02, 0.006, 0.01, 0.01) == 0.01


def test_003_lot_30pct_becomes_001():
    assert adapt(0.03, 0.009, 0.01, 0.01) == 0.01


def test_010_lot_30pct_remains_exact():
    assert adapt(0.10, 0.03, 0.01, 0.01) == 0.03


def test_single_minimum_lot_cannot_be_partially_split():
    assert adapt(0.01, 0.003, 0.01, 0.01) is None


def test_source_no_longer_floors_requested_partial_to_zero():
    assert "double requested_close=close_volume;" in TM
    assert "MathRound(requested_close/step)" in TM
    assert "double max_partial=before-minv;" in TM
    assert "NEXUS PARTIAL ADAPTIVE VOLUME" in TM
    assert (
        "close_volume=MathFloor(close_volume/step+1e-9)*step;"
        not in TM
    )


def test_full_close_path_is_preserved():
    assert "bool full_close_requested=" in TM
    assert "close_volume=before;" in TM
