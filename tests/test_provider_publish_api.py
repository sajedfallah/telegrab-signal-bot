from __future__ import annotations

import sqlite3

import pytest
from fastapi import HTTPException

from app.provider_panel_api import SignalPublishRequest, publish_signal
from app.tenancy import TenantContext, TenantRole


class _Conn:
    def __enter__(self):
        con = sqlite3.connect(":memory:")
        con.row_factory = sqlite3.Row
        self.con = con
        return con

    def __exit__(self, *_):
        self.con.close()


def test_publisher_role_can_publish(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.provider_panel_api._tenant_context",
        lambda *_: TenantContext(tenant_id=7, user_id=1001, role=TenantRole.PUBLISHER),
    )
    monkeypatch.setattr("app.provider_panel_api.db.conn", lambda: _Conn())
    calls = []

    def fake_publish(con, **kwargs):
        calls.append(kwargs)
        return {
            "ok": True,
            "publication_id": 1,
            "signal_id": kwargs["signal_id"],
            "destination_key": kwargs["destination_key"],
            "chat_id": "-100111",
            "message_id": 901,
        }

    monkeypatch.setattr("app.provider_panel_api.publish_signal_text", fake_publish)
    result = publish_signal(
        44,
        SignalPublishRequest(destination_key="VIP", text="signal text"),
        "signed",
        7,
    )
    assert result["tenant_id"] == 7
    assert result["publication"]["message_id"] == 901
    assert calls == [{"tenant_id": 7, "signal_id": 44, "destination_key": "VIP", "text": "signal text"}]


def test_viewer_cannot_publish(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.provider_panel_api._tenant_context",
        lambda *_: TenantContext(tenant_id=7, user_id=1001, role=TenantRole.VIEWER),
    )
    monkeypatch.setattr(
        "app.provider_panel_api.publish_signal_text",
        lambda *_args, **_kwargs: pytest.fail("publish service must not be called"),
    )
    with pytest.raises(HTTPException) as exc:
        publish_signal(
            44,
            SignalPublishRequest(destination_key="VIP", text="signal text"),
            "signed",
            7,
        )
    assert exc.value.status_code == 403


def test_cross_tenant_or_missing_signal_is_404(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.provider_panel_api._tenant_context",
        lambda *_: TenantContext(tenant_id=7, user_id=1001, role=TenantRole.OWNER),
    )
    monkeypatch.setattr("app.provider_panel_api.db.conn", lambda: _Conn())

    def fake_publish(*_args, **_kwargs):
        raise LookupError("signal not found")

    monkeypatch.setattr("app.provider_panel_api.publish_signal_text", fake_publish)
    with pytest.raises(HTTPException) as exc:
        publish_signal(
            999,
            SignalPublishRequest(destination_key="VIP", text="signal text"),
            "signed",
            7,
        )
    assert exc.value.status_code == 404
