from __future__ import annotations

import contextvars
import os
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import Header, HTTPException
from fastapi.routing import APIRoute

from .. import db

_test_create_account: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "nexus_test_create_account", default=None
)
_test_publish: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "nexus_test_publish", default=False
)


def _route(app, path: str, method: str) -> APIRoute:
    method = method.upper()
    for candidate in app.router.routes:
        if isinstance(candidate, APIRoute) and candidate.path == path and method in candidate.methods:
            return candidate
    raise RuntimeError(f"NEXUS Test Lab route not found: {method} {path}")


def _replace_route(app, path: str, method: str, func: Callable[..., Any]) -> Callable[..., Any]:
    route = _route(app, path, method)
    original = route.dependant.call
    route.endpoint = func
    route.dependant.call = func
    return original


def _test_account() -> str:
    return str(os.getenv("NEXUS_TEST_MT5_ACCOUNT", "")).strip()


def _test_channel() -> str | int:
    raw = str(os.getenv("NEXUS_TEST_CHANNEL_ID", "")).strip()
    if not raw:
        raise RuntimeError("NEXUS_TEST_CHANNEL_ID is not configured")
    try:
        return int(raw)
    except ValueError:
        return raw


def _status_for_account(account: str) -> dict[str, Any]:
    account = str(account or "").strip()
    if not account:
        return {
            "online": False,
            "status": "NOT_CONFIGURED",
            "account_number": None,
            "ea_version": None,
            "last_seen_at": None,
            "age_seconds": None,
        }
    with db.conn() as con:
        row = con.execute(
            "SELECT account_number,ea_version,last_seen_at FROM mt5_heartbeats_v060 "
            "WHERE role='ADMIN' AND account_number=? ORDER BY last_seen_at DESC LIMIT 1",
            (account,),
        ).fetchone()
    age = None
    if row and row["last_seen_at"]:
        try:
            seen = datetime.fromisoformat(str(row["last_seen_at"]).replace("Z", "+00:00"))
            if seen.tzinfo is None:
                seen = seen.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - seen.astimezone(timezone.utc)).total_seconds()
        except ValueError:
            age = None
    online = age is not None and -5 <= age <= 120
    return {
        "online": online,
        "status": "ONLINE" if online else "OFFLINE",
        "account_number": account,
        "ea_version": str(row["ea_version"] or "") if row else None,
        "last_seen_at": str(row["last_seen_at"]) if row else None,
        "age_seconds": round(age, 1) if age is not None else None,
    }


class _ApiSettingsProxy:
    def __init__(self, real_settings):
        object.__setattr__(self, "_real", real_settings)

    def __getattr__(self, name: str):
        if name == "free_channel_target" and _test_publish.get():
            return _test_channel()
        return getattr(object.__getattribute__(self, "_real"), name)


def install_test_lab_runtime(app) -> None:
    """Install an isolated Demo/Test Lab without changing production routing.

    A Test Lab request is identified by request_id prefix ``TEST:``. It is
    forced to one dedicated demo MT5 account and one dedicated Telegram test
    channel. Production FREE/VIP destinations are never selected by this path.

    Required environment values:
      NEXUS_TEST_MT5_ACCOUNT=<demo account>
      NEXUS_TEST_CHANNEL_ID=<telegram test channel id>

    The demo account must also be present in the existing server-side Admin MT5
    allow-list, so the normal admin-token authorization remains authoritative.
    """
    if getattr(app.state, "nexus_test_lab_v36", False):
        return

    from . import api as api_mod
    from .. import miniapp_admin_api as mini_mod

    original_admin_status = mini_mod._admin_mt5_status

    def routed_admin_status() -> dict[str, Any]:
        account = _test_create_account.get()
        if account:
            return _status_for_account(account)
        return original_admin_status()

    mini_mod._admin_mt5_status = routed_admin_status

    original_create = _route(app, "/miniapp/api/admin/signals", "POST").dependant.call

    def create_signal_test_aware(**kwargs):
        req = kwargs.get("req")
        request_id = str(getattr(req, "request_id", "") or "")
        if not request_id.upper().startswith("TEST:"):
            return original_create(**kwargs)

        account = _test_account()
        if not account:
            raise HTTPException(status_code=503, detail="NEXUS_TEST_MT5_ACCOUNT is not configured")
        try:
            _test_channel()
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        # A test signal is a single-channel logical FREE publication whose
        # physical target is replaced by the Test Lab publisher below.
        req.destination = "FREE"
        token = _test_create_account.set(account)
        try:
            result = original_create(**kwargs)
        finally:
            _test_create_account.reset(token)
        if isinstance(result, dict):
            result["test_lab"] = True
            result["test_mt5_account"] = account
            result["test_channel_configured"] = True
        return result

    _replace_route(app, "/miniapp/api/admin/signals", "POST", create_signal_test_aware)

    @app.get("/miniapp/api/admin/test/bootstrap")
    def test_bootstrap(
        x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
    ):
        user = mini_mod._admin(x_telegram_init_data)
        account = _test_account()
        channel_ok = bool(str(os.getenv("NEXUS_TEST_CHANNEL_ID", "")).strip())
        allowed = account in {str(value) for value in api_mod.settings.nexus_admin_mt5_accounts}
        return {
            "ok": bool(account and channel_ok and allowed),
            "user": user,
            "mode": "TEST_LAB",
            "mt5": _status_for_account(account),
            "test_channel_configured": channel_ok,
            "account_allowlisted": allowed,
            "publish_request_prefix": "TEST:",
            "forced_destination": "TEST",
        }

    real_api_settings = api_mod.settings
    if not isinstance(real_api_settings, _ApiSettingsProxy):
        api_mod.settings = _ApiSettingsProxy(real_api_settings)

    original_publisher = api_mod._publish_mt5_admin_signal_async

    async def test_channel_publisher(row, chart_base64=None, *, allow_without_chart=False):
        canonical = db.get_signal(int(row["id"])) or row
        account = str(canonical["issuer_account"] or "").strip()
        test_account = _test_account()
        if not test_account or account != test_account:
            return await original_publisher(canonical, chart_base64, allow_without_chart=allow_without_chart)

        # Once the test root exists, never enter production repair wrappers.
        # Test Lab prioritizes isolation over media-repair retries.
        if canonical["free_message_id"] and str(canonical["publication_stage"] or "").upper() == "PUBLISHED":
            return {
                "free_message_id": int(canonical["free_message_id"]),
                "vip_message_id": None,
                "errors": [],
                "published": True,
                "complete": True,
                "test_lab": True,
            }

        token = _test_publish.set(True)
        try:
            result = await original_publisher(canonical, chart_base64, allow_without_chart=allow_without_chart)
        finally:
            _test_publish.reset(token)

        # After the root Test Channel message is safely published, prevent the
        # production lifecycle worker from interpreting this as FREE/VIP work.
        if isinstance(result, dict) and result.get("complete"):
            with db.conn() as con:
                con.execute("UPDATE signals SET destination='NONE' WHERE id=?", (int(canonical["id"]),))
            result["test_lab"] = True
            result["test_channel_only"] = True
        return result

    api_mod._publish_mt5_admin_signal_async = test_channel_publisher

    # Test trade events remain broker-truth records, but are explicitly marked
    # destination NONE so production channel lifecycle cannot be triggered.
    original_trade_event = _route(app, "/api/v1/autotrade/trade-event", "POST").dependant.call

    def isolated_trade_event(**kwargs):
        req = kwargs.get("req")
        account = str(kwargs.get("x_mt5_account") or getattr(req, "account_number", "") or "").strip()
        if _test_account() and account == _test_account() and req is not None:
            req.destination = "NONE"
        return original_trade_event(**kwargs)

    _replace_route(app, "/api/v1/autotrade/trade-event", "POST", isolated_trade_event)

    app.state.nexus_test_lab_v36 = True
