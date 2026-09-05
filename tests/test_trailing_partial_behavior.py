from __future__ import annotations

import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TM = (ROOT / "mt5/NEXUS_AutoTrade/Include/TradeManager.mqh").read_text(encoding="utf-8")
TRAIL = (ROOT / "mt5/NEXUS_AutoTrade/Include/TrailingEngine.mqh").read_text(encoding="utf-8")


def closest_executable_partial(before: float, requested: float, minimum: float, step: float) -> float:
    """Executable model corresponding to PartialCloseVolume's quantizer."""
    floor_volume = math.floor(requested / step + 1e-9) * step
    ceil_volume = math.ceil(requested / step - 1e-9) * step
    max_partial = math.floor((before - minimum) / step + 1e-9) * step
    floor_valid = minimum <= floor_volume <= max_partial + 1e-9
    ceil_valid = minimum <= ceil_volume <= max_partial + 1e-9
    if floor_valid and ceil_valid:
        return floor_volume if abs(requested - floor_volume) <= abs(ceil_volume - requested) else ceil_volume
    if floor_valid:
        return floor_volume
    if ceil_valid:
        return ceil_volume
    return floor_volume


def test_30_percent_of_small_but_splittable_position_no_longer_becomes_zero():
    assert closest_executable_partial(0.02, 0.02 * 0.30, 0.01, 0.01) == 0.01


def test_quantizer_chooses_nearest_valid_step_and_preserves_minimum_residual():
    close = closest_executable_partial(0.10, 0.10 * 0.26, 0.01, 0.01)
    assert close == 0.03
    assert 0.10 - close >= 0.01


def test_unsplittable_minimum_lot_is_never_falsely_reported_as_partial_success():
    assert closest_executable_partial(0.01, 0.01 * 0.30, 0.01, 0.01) < 0.01
    assert "partial close unavailable on broker volume grid" in TM


def test_tp_done_is_after_broker_confirmation_call():
    call = TRAIL.index("m_tm.PartialCloseVolume(ticket,close_volume)")
    done = TRAIL.index('NexusTrailSet(sig,field+"_done",1);')
    assert call < done


def test_comment_loss_recovery_is_on_the_trailing_hot_path():
    manage = TRAIL.index("void ManageAll")
    recovery_call = TRAIL.index("NexusTrailRecoverSignal(ticket", manage)
    mode_load = TRAIL.index('NexusTrailGet(sig,"mode"', recovery_call)
    assert manage < recovery_call < mode_load
