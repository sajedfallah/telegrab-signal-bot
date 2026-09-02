import pytest
from pydantic import ValidationError

from app.autotrade.api import MT5AdminSignalRequest


def _base_kwargs(**overrides):
    kwargs = dict(
        symbol="XAUUSD.ec",
        direction="BUY",
        order_type="MARKET",
        entry_price=4356.0,
        stop_loss=4346.0,
        targets=[4366.0],
        risk_percent=1.0,
        volume_mode="RISK",
    )
    kwargs.update(overrides)
    return kwargs


def test_market_signal_rejects_literal_zero_max_entry_deviation_pct():
    with pytest.raises(ValidationError):
        MT5AdminSignalRequest(**_base_kwargs(max_entry_deviation_pct=0))


def test_market_signal_rejects_literal_zero_max_entry_deviation_abs():
    with pytest.raises(ValidationError):
        MT5AdminSignalRequest(**_base_kwargs(max_entry_deviation_abs=0))


def test_market_signal_omitted_deviation_is_none_not_zero():
    req = MT5AdminSignalRequest(**_base_kwargs())
    assert req.max_entry_deviation_pct is None
    assert req.max_entry_deviation_abs is None


def test_market_signal_accepts_a_real_positive_deviation_threshold():
    req = MT5AdminSignalRequest(**_base_kwargs(max_entry_deviation_pct=0.5))
    assert req.max_entry_deviation_pct == 0.5
