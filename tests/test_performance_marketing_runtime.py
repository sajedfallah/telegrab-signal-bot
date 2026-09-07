from app.services.performance_marketing_runtime import ChannelMetrics, score_advantage, render_public_message


def _m(channel: str, **overrides):
    data = dict(
        channel=channel,
        trades=6,
        wins=3,
        losses=3,
        be=0,
        win_rate=50.0,
        net_r=1.0,
        avg_r=0.17,
        r_coverage=1.0,
        net_usd=100.0,
        gross_profit_usd=200.0,
        gross_loss_usd=100.0,
        usd_coverage=1.0,
        profit_factor=1.2,
        winning_streak=2,
        max_drawdown_r=2.0,
    )
    data.update(overrides)
    return ChannelMetrics(**data)


def test_strong_vip_advantage_uses_r_usd_pf_and_win_rate():
    free = _m("FREE")
    vip = _m(
        "VIP",
        wins=5,
        losses=1,
        win_rate=83.3,
        net_r=5.2,
        avg_r=0.87,
        net_usd=420.0,
        gross_profit_usd=470.0,
        gross_loss_usd=50.0,
        profit_factor=3.5,
        winning_streak=4,
        max_drawdown_r=0.5,
    )
    decision = score_advantage(vip, free, usd_threshold=150.0)
    assert decision.qualifies is True
    assert decision.strong is True
    assert decision.score >= 85
    assert decision.hard_conditions >= 2


def test_usd_is_not_used_when_coverage_is_too_low():
    free = _m("FREE", usd_coverage=0.4, net_usd=-500.0)
    vip = _m("VIP", usd_coverage=0.4, net_usd=5000.0, net_r=1.1)
    decision = score_advantage(vip, free, usd_threshold=150.0)
    assert all("USD" not in reason for reason in decision.reasons)


def test_small_sample_does_not_promote_even_with_large_numbers():
    free = _m("FREE", trades=2)
    vip = _m(
        "VIP",
        trades=4,
        win_rate=100.0,
        net_r=10.0,
        avg_r=2.5,
        net_usd=1000.0,
        profit_factor=10.0,
        winning_streak=4,
    )
    decision = score_advantage(vip, free, usd_threshold=150.0)
    assert decision.qualifies is False


def test_public_copy_is_transparent_and_contains_no_guarantee_claim():
    free = _m("FREE")
    vip = _m("VIP", net_r=5.0, net_usd=400.0, win_rate=80.0, profit_factor=2.5)
    decision = score_advantage(vip, free, usd_threshold=150.0)
    text = render_public_message(vip, free, decision, discount_code="NXVIP1234", discount_expires_local="1405/06/16 23:59")
    assert "معاملات <b>بسته‌شده</b>" in text
    assert "PnL ثبت‌شده" in text
    assert "تضمینی برای نتایج آینده نیست" in text
    assert "NXVIP1234" in text
