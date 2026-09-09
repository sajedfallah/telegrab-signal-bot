from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import pytest
from fastapi import HTTPException

from app.config import settings
from app.miniapp_api import _validate_init_data
from app.miniapp_experience import build_experience_context
from app.miniapp_home import _autotrade_health, _safe_signal, _section_order
from app.services import analytics_service


def _signed_init_data(user_id: int = 123456789) -> str:
    values = {
        "auth_date": str(int(time.time())),
        "query_id": "AAE-test-query",
        "user": json.dumps({"id": user_id, "first_name": "NEXUS", "username": "nexus_test"}, separators=(",", ":")),
    }
    check = "\n".join(f"{k}={values[k]}" for k in sorted(values))
    secret = hmac.new(b"WebAppData", settings.bot_token.encode("utf-8"), hashlib.sha256).digest()
    values["hash"] = hmac.new(secret, check.encode("utf-8"), hashlib.sha256).hexdigest()
    return urlencode(values)


def _entitlements(*, vip: bool = False, autotrade: bool = False, vip_expiry: str | None = None, auto_expiry: str | None = None):
    return {
        "active": vip or autotrade,
        "vip": vip,
        "autotrade": autotrade,
        "plan_code": None,
        "vip_expires_at": vip_expiry,
        "autotrade_expires_at": auto_expiry,
    }


def _third_route(ctx: dict) -> str:
    return str(ctx["navigation"][2]["route"])


def test_miniapp_init_data_signature_accepts_valid_user():
    user = _validate_init_data(_signed_init_data())
    assert int(user["id"]) == 123456789
    assert user["username"] == "nexus_test"


def test_miniapp_init_data_signature_rejects_tampering():
    raw = _signed_init_data().replace("nexus_test", "attacker")
    with pytest.raises(HTTPException) as exc:
        _validate_init_data(raw)
    assert exc.value.status_code == 401


def test_experience_guest_gets_plans_navigation():
    now = datetime(2026, 9, 10, tzinfo=timezone.utc)
    ctx = build_experience_context(_entitlements(), now=now)
    assert ctx["segment"] == "GUEST"
    assert ctx["lifecycle"] == "GUEST"
    assert _third_route(ctx) == "subscriptions"
    assert ctx["features"]["trades"] is False


def test_experience_vip_gets_upgrade_navigation():
    now = datetime(2026, 9, 10, tzinfo=timezone.utc)
    ctx = build_experience_context(
        _entitlements(vip=True, vip_expiry=(now + timedelta(days=30)).isoformat()),
        now=now,
    )
    assert ctx["segment"] == "VIP"
    assert ctx["lifecycle"] == "ACTIVE"
    assert ctx["navigation"][2]["label_en"] == "Upgrade"
    assert _third_route(ctx) == "subscriptions"


def test_experience_autotrade_gets_trades_navigation():
    now = datetime(2026, 9, 10, tzinfo=timezone.utc)
    ctx = build_experience_context(
        _entitlements(autotrade=True, auto_expiry=(now + timedelta(days=30)).isoformat()),
        now=now,
    )
    assert ctx["segment"] == "AUTOTRADE"
    assert ctx["lifecycle"] == "ACTIVE"
    assert _third_route(ctx) == "trades"
    assert ctx["features"]["trades"] is True


def test_experience_bundle_can_be_expiring_without_losing_trades():
    now = datetime(2026, 9, 10, tzinfo=timezone.utc)
    ctx = build_experience_context(
        _entitlements(
            vip=True,
            autotrade=True,
            vip_expiry=(now + timedelta(days=2)).isoformat(),
            auto_expiry=(now + timedelta(days=20)).isoformat(),
        ),
        now=now,
    )
    assert ctx["segment"] == "BUNDLE"
    assert ctx["lifecycle"] == "EXPIRING"
    assert ctx["expiring"] is True
    assert _third_route(ctx) == "trades"


def test_experience_expired_customer_returns_to_plans():
    now = datetime(2026, 9, 10, tzinfo=timezone.utc)
    latest = {
        "vip_access": 0,
        "autotrade_access": 1,
        "autotrade_expires_at": (now - timedelta(days=1)).isoformat(),
        "expires_at": (now - timedelta(days=1)).isoformat(),
    }
    ctx = build_experience_context(_entitlements(), latest, now=now)
    assert ctx["segment"] == "AUTOTRADE"
    assert ctx["lifecycle"] == "EXPIRED"
    assert _third_route(ctx) == "subscriptions"
    assert ctx["features"]["trades"] is False


def test_active_vip_home_preview_masks_direction_for_unauthorized_user():
    row = {
        "id": 42,
        "code": "42",
        "symbol": "XAUUSD",
        "direction": "BUY",
        "destination": "VIP",
        "status": "ACTIVE",
        "created_at": "2026-09-10T00:00:00+00:00",
        "closed_at": None,
        "result_value": None,
        "result_unit": None,
    }
    item = _safe_signal(row, has_vip=False)
    assert item["locked"] is True
    assert item["direction"] is None
    assert "entry_price" not in item


def test_closed_vip_home_preview_can_show_result_metadata_without_actionable_fields():
    row = {
        "id": 43,
        "code": "43",
        "symbol": "XAUUSD",
        "direction": "SELL",
        "destination": "VIP",
        "status": "CLOSED",
        "created_at": "2026-09-09T10:00:00+00:00",
        "closed_at": "2026-09-09T11:00:00+00:00",
        "result_value": 25,
        "result_unit": "PIPS",
    }
    item = _safe_signal(row, has_vip=False)
    assert item["locked"] is False
    assert item["direction"] == "SELL"
    assert item["result"] == "WIN"
    assert "entry_price" not in item
    assert "stop_loss" not in item


def test_autotrade_health_requires_meaningful_heartbeat_staleness():
    now = datetime(2026, 9, 10, 0, 10, tzinfo=timezone.utc)
    fresh = {
        "entitled": True,
        "mt5": {"account_number": "1234", "status": "ACTIVE", "last_seen_at": (now - timedelta(seconds=30)).isoformat()},
        "open_positions": [],
        "pending_orders": [],
    }
    stale = {
        **fresh,
        "mt5": {"account_number": "1234", "status": "ACTIVE", "last_seen_at": (now - timedelta(hours=1)).isoformat()},
    }
    assert _autotrade_health(fresh, now=now)["state"] == "HEALTHY"
    assert _autotrade_health(stale, now=now)["state"] == "DISCONNECTED"


def test_guest_home_order_prioritizes_trust_and_does_not_include_autotrade_widgets():
    experience = build_experience_context(_entitlements(), now=datetime(2026, 9, 10, tzinfo=timezone.utc))
    order = _section_order(experience, [])
    assert order[:3] == ["spotlight", "performance", "recent_signals"]
    assert "autotrade_health" not in order
    assert "trades_preview" not in order


def test_analytics_supports_90_day_period_for_track_record_filters():
    p = analytics_service.period("90")
    assert p.key == "90"
    assert p.label_en == "Last 90 days"


def test_combined_api_exposes_miniapp_routes_and_static_mount():
    from app.combined_api import app

    paths = {getattr(route, "path", "") for route in app.routes}
    assert "/miniapp/api/health" in paths
    assert "/miniapp/api/bootstrap" in paths
    assert "/miniapp/api/experience" in paths
    assert "/miniapp/api/home" in paths
    assert "/miniapp/api/performance" in paths
    assert "/miniapp/api/invoices" in paths
    assert "/miniapp/api/receipts" in paths
    assert "/miniapp" in paths
