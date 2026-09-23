from __future__ import annotations

from pathlib import Path

from app.signals.contract import canonical_signal, to_mt5_payload


def test_combined_api_registers_admin_and_user_signal_routes():
    from app.combined_api import app

    paths = {getattr(route, "path", "") for route in app.routes}
    required = {
        "/miniapp/api/admin/health",
        "/miniapp/api/admin/bootstrap",
        "/miniapp/api/admin/signals",
        "/miniapp/api/admin/signals/calculate",
        "/miniapp/api/admin/positions",
        "/miniapp/api/signals",
        "/miniapp/api/signals/closed-calendar",
        "/miniapp/api/signals/{signal_id}",
    }
    assert required <= paths


def test_frontends_call_only_registered_relative_miniapp_namespaces():
    admin = Path("miniapp/admin-signal-v13.js").read_text(encoding="utf-8")
    user = Path("miniapp/app.js").read_text(encoding="utf-8")
    vercel = Path("miniapp/vercel.json").read_text(encoding="utf-8")

    assert "const API = '/miniapp/api/admin'" in admin
    assert "const API = '/miniapp/api'" in user
    assert "https://api.nexustrade.ir/miniapp/api/:path*" in vercel
    assert "X-NEXUS-Admin-Token" not in admin


def test_canonical_contract_does_not_invent_optional_truth():
    row = {
        "id": 154, "code": "NX-0154", "market_type": "GOLD", "symbol": "XAUUSD",
        "direction": "SELL", "timeframe": "M5", "order_type": "MARKET",
        "entry_price": 4314.0, "stop_loss": 4322.0, "volume_mode": "FIXED",
        "lot_size": 0.02, "risk_percent": 0.0, "status": "ACTIVE",
        "destination": "VIP", "created_at": "2026-09-23T00:00:00+00:00",
        "issuer_type": "MT5_ADMIN", "issuer_account": "1234",
    }
    contract = canonical_signal(row, [{"target_no": 1, "price": 4306.0}, {"target_no": 2, "price": 4300.0}])
    assert contract["signal_id"] == 154
    assert contract["code"] == "NX-0154"
    assert contract["entry_price"] == 4314.0
    assert contract["stop_loss"] == 4322.0
    assert contract["volume"] == 0.02
    assert contract["risk_percent"] is None
    assert contract["risk_reward"] is None
    assert contract["exit_price"] is None
    assert contract["realized_pnl"] is None


def test_mt5_adapter_preserves_legacy_wire_names_without_changing_values():
    row = {
        "id": 154, "code": "NX-0154", "market_type": "GOLD", "symbol": "XAUUSD",
        "direction": "SELL", "timeframe": "M5", "order_type": "MARKET",
        "entry_price": 4314.0, "stop_loss": 4322.0, "volume_mode": "FIXED",
        "lot_size": 0.02, "status": "ACTIVE", "destination": "VIP",
    }
    contract = canonical_signal(row, [{"target_no": 1, "price": 4306.0}, {"target_no": 2, "price": 4300.0}])
    payload = to_mt5_payload(contract)
    assert payload["id"] == 154
    assert payload["signal_id"] == "NX-0154"
    assert payload["entry"] == 4314.0
    assert payload["sl"] == 4322.0
    assert payload["tp1"] == 4306.0
    assert payload["tp2"] == 4300.0
    assert payload["tp3"] is None
    assert payload["timeframe"] == "M5"
    assert payload["order_type"] == "MARKET"
