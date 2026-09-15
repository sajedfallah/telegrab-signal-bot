from __future__ import annotations

from pathlib import Path

from app.autotrade.web_admin_market_entry_guard import _entry_truth_check


ROOT = Path(__file__).resolve().parents[1]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8-sig")


def test_v31_rejects_nx55_scale_market_entry_drift():
    # Diagnostic evidence for NX-55: stored SELL entry 4291 while the broker
    # candles around issue time were ~4283-4285. A fresh quote in that region
    # must not be accepted as the same MARKET entry.
    check = _entry_truth_check(
        entry=4291.0,
        direction="SELL",
        bid=4283.50,
        ask=4283.70,
        digits=2,
    )
    assert check["market_price"] == 4283.50
    assert check["deviation"] > 7.0
    assert check["ok"] is False


def test_v31_accepts_recent_market_entry_within_broker_tolerance():
    check = _entry_truth_check(
        entry=4283.55,
        direction="SELL",
        bid=4283.50,
        ask=4283.70,
        digits=2,
    )
    assert check["ok"] is True
    assert check["deviation"] <= check["tolerance"]


def test_v31_uses_correct_side_of_bid_ask():
    sell = _entry_truth_check(entry=100.0, direction="SELL", bid=100.0, ask=100.2, digits=2)
    buy = _entry_truth_check(entry=100.2, direction="BUY", bid=100.0, ask=100.2, digits=2)
    assert sell["market_price"] == 100.0
    assert buy["market_price"] == 100.2
    assert sell["ok"] is True
    assert buy["ok"] is True


def test_v31_guard_reuses_authenticated_fresh_quote_contract_and_defers_only_503():
    src = _text("app/autotrade/web_admin_market_entry_guard.py")
    assert '"/miniapp/api/admin/signals"' in src
    assert "market_quote" in src
    assert "quote_age_seconds" in src
    assert "DEFERRED_NO_FRESH_QUOTE" in src
    assert "int(exc.status_code) != 503" in src
    assert "Refresh Market Price and publish again" in src
    assert "status_code=409" in src
    assert "target_route.dependant.call = guarded_create_signal" in src
    assert 'result["entry_truth"] = check' in src


def test_v31_wraps_final_route_after_web_admin_execution_bridge():
    src = _text("app/combined_api.py")
    assert "install_web_admin_market_entry_guard(app)" in src
    assert src.index("install_miniapp_execution_gate(app)") < src.index("install_web_admin_market_entry_guard(app)")


def test_v31_has_no_execution_or_market_data_side_effects():
    src = _text("app/autotrade/web_admin_market_entry_guard.py")
    forbidden = (
        "order_send",
        "place_order",
        "send_order",
        "MetaTrader5",
        "UPDATE signals",
        "INSERT INTO signals",
        "mt5_market_candles",
        "random",
    )
    for marker in forbidden:
        assert marker not in src
