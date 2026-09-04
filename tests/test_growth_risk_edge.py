from app.autotrade.risk_firewall import decision_for_metrics
from app.edge_analytics_runtime import aggregate_r_values
from app.growth_conversion_runtime import pending_referral_milestones, referral_tier_for_count


def test_referral_three_successes_unlocks_seven_day_vip_milestone():
    pending = pending_referral_milestones(3, set())
    assert pending == [(3, 7, "BRONZE")]
    assert referral_tier_for_count(3) == "BRONZE"


def test_referral_ladder_is_idempotent_and_scales():
    assert pending_referral_milestones(10, {3}) == [(10, 15, "SILVER")]
    assert referral_tier_for_count(25) == "GOLD"


def test_daily_loss_limit_blocks_new_trades():
    decision = decision_for_metrics(daily_r=-3.0, loss_streak=1, daily_limit_r=3.0)
    assert decision.allowed is False
    assert decision.reason == "DAILY_LOSS_LIMIT"
    assert decision.risk_multiplier == 0.0


def test_dynamic_risk_reduces_size_before_daily_stop():
    decision = decision_for_metrics(daily_r=-1.6, loss_streak=1, daily_limit_r=3.0)
    assert decision.allowed is True
    assert decision.reason == "DEFENSIVE_DRAWDOWN"
    assert decision.risk_multiplier == 0.75


def test_kill_switch_is_fail_closed_for_new_trades():
    decision = decision_for_metrics(daily_r=2.0, loss_streak=0, global_kill=True)
    assert decision.allowed is False
    assert decision.reason == "GLOBAL_KILL_SWITCH"


def test_edge_metric_uses_r_expectancy_and_profit_factor():
    metric = aggregate_r_values("XAUUSD", [2.0, -1.0, 1.5, -0.5, 0.0])
    assert metric.trades == 5
    assert metric.wins == 2
    assert metric.losses == 2
    assert metric.breakeven == 1
    assert metric.win_rate == 40.0
    assert metric.total_r == 2.0
    assert metric.avg_r == 0.4
    assert metric.profit_factor == 2.33
