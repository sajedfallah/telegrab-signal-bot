from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from . import db
from .provider_lifecycle import reply_signal_event
from .provider_panel_api import _require, _tenant_context
from .provider_permissions import ProviderPermission
from .signal_domain import EVENT_TYPES

router = APIRouter(prefix="/provider/api", tags=["Provider Signal Lifecycle"])


class SignalLifecycleRequest(BaseModel):
    destination_key: str = Field(min_length=1, max_length=80)
    event_type: str = Field(min_length=1, max_length=40)
    payload: dict[str, Any] = Field(default_factory=dict)


@router.post("/signals/{signal_id}/events")
def publish_signal_event(
    signal_id: int,
    request: SignalLifecycleRequest,
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
    x_tenant_id: int | None = Header(default=None, alias="X-Tenant-Id"),
) -> dict[str, Any]:
    ctx = _tenant_context(x_telegram_init_data, x_tenant_id)
    _require(ctx, ProviderPermission.PUBLISH_SIGNAL)
    event_type = request.event_type.strip().upper()
    if event_type not in EVENT_TYPES:
        raise HTTPException(status_code=422, detail="unsupported signal event type")
    try:
        with db.conn() as con:
            receipt = reply_signal_event(
                con,
                tenant_id=ctx.tenant_id,
                signal_id=signal_id,
                destination_key=request.destination_key,
                event_type=event_type,
                payload=request.payload,
                actor_user_id=ctx.user_id,
            )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        message = str(exc)
        if "closed" in message.lower() or "route" in message.lower() or "publish-ready" in message.lower():
            raise HTTPException(status_code=409, detail=message) from exc
        raise HTTPException(status_code=502, detail="Telegram lifecycle reply failed") from exc
    return {"tenant_id": ctx.tenant_id, "event": receipt}
