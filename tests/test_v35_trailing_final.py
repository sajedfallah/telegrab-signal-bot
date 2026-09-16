from pathlib import Path
import math

ROOT = Path(__file__).resolve().parents[1]
TRAIL = (ROOT / "mt5/NEXUS_AutoTrade_UI65/Core/Include/TrailingEngine.mqh").read_text(encoding="utf-8")
PROFILES = (ROOT / "app/autotrade/trailing_profiles.py").read_text(encoding="utf-8")


def target_close_pct(n: int, count: int, first: float = 30.0, second: float = 30.0, runner: float = 40.0) -> float:
    if count <= 0 or n < 1:
        return 0.0
    if n >= count:
        return 100.0
    runner = max(0.0, min(100.0, runner))
    first = max(0.0, min(100.0 - runner, first))
    if n == 1:
        return first
    if n == 2 and count >= 3:
        return max(0.0, min(100.0 - runner - first, second))
    return 0.0


def executable_partial(before: float, requested: float, reserve: float, minimum: float = 0.01, step: float = 0.01) -> float:
    if minimum <= 0 or before <= 0:
        return -1.0
    if requested <= 0:
        return 0.0
    if step <= 0:
        step = minimum
    eps = max(step * 0.1, 1e-8)
    max_partial = before - max(minimum, reserve)
    if max_partial + eps < minimum:
        return 0.0
    volume = round(round(requested / step) * step, 8)
    if volume < minimum:
        volume = minimum
    if volume > max_partial:
        volume = math.floor(max_partial / step + 1e-9) * step
    volume = round(volume, 8)
    if volume < minimum or before - volume + eps < minimum:
        return 0.0
    return volume


def test_four_target_trail07_is_30_30_milestone_final_runner():
    assert [target_close_pct(i, 4) for i in range(1, 5)] == [30.0, 30.0, 0.0, 100.0]


def test_three_target_trail07_is_30_30_40_remainder():
    assert [target_close_pct(i, 3) for i in range(1, 4)] == [30.0, 30.0, 100.0]


def test_two_target_ladder_closes_30_then_final_remainder():
    assert [target_close_pct(i, 2) for i in range(1, 3)] == [30.0, 100.0]


def test_002_lot_min_001_closes_001_at_tp1_then_preserves_runner():
    initial = 0.02
    reserve = math.ceil((initial * 0.40) / 0.01 - 1e-9) * 0.01
    first = executable_partial(initial, initial * 0.30, reserve)
    assert first == 0.01
    remaining = round(initial - first, 8)
    assert remaining == 0.01
    second = executable_partial(remaining, initial * 0.30, reserve)
    assert second == 0.0


def test_003_lot_min_001_executes_one_001_partial_and_never_invents_volume():
    initial = 0.03
    reserve = math.ceil((initial * 0.40) / 0.01 - 1e-9) * 0.01
    first = executable_partial(initial, initial * 0.30, reserve)
    assert first == 0.01
    assert round(initial - first, 8) == 0.02


def test_runner_is_structure_first_with_atr_only_as_fallback():
    runner = TRAIL.split("void RunnerTrail", 1)[1].split("double Target", 1)[0]
    assert "if(!StructureTrail(ticket,sig,pt,symbol,pr))" in runner
    assert runner.index("StructureTrail") < runner.index("ATRTrail")


def test_step_profiles_do_not_jump_past_be_at_activation():
    step = TRAIL.split("void Step", 1)[1].split("void ATRTrail", 1)[0]
    assert "MathFloor((pr-trigger)/step);" in step
    assert "if(levels<=0)return;" in step
    assert "MathFloor((pr-trigger)/step)+1" not in step


def test_profile_contract_still_declares_30_30_40_for_t05_and_t07():
    for code in ("NEXUS_TRAIL_05", "NEXUS_TRAIL_07"):
        block = PROFILES.split(f'"{code}"', 1)[1].split("},", 1)[0]
        assert '"tp1_close_pct": 30.0' in block
        assert '"tp2_close_pct": 30.0' in block
        assert '"runner_pct": 40.0' in block
        assert '"runner_mode": "MARKET_STRUCTURE_ATR_FALLBACK"' in block


def test_broker_tick_claim_and_actual_partial_truth_are_present():
    assert "NexusTrailClaimManageTick" in TRAIL
    assert "SavePartialTruth" in TRAIL
    assert 'field+"_volume_skipped"' in TRAIL
    assert 'field+"_milestone_only"' in TRAIL
