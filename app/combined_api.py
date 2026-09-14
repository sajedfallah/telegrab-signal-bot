from __future__ import annotations

from pathlib import Path

from fastapi.staticfiles import StaticFiles

from .autotrade.api import app
from .miniapp_api import router as miniapp_router
from .provider_panel_api import router as provider_panel_router


# The existing AutoTrade API stays the root FastAPI application/source of truth.
# Mini App endpoints are added to the same process and therefore share the same
# SQLite database, subscription engine, pricing service and bot configuration.
app.include_router(miniapp_router)

# Provider Panel is a separate B2B surface. Its API requires tenant membership
# server-side; a client supplied tenant id is only a selector, never authorization.
app.include_router(provider_panel_router)

MINIAPP_DIR = Path(__file__).resolve().parent.parent / "miniapp"
if MINIAPP_DIR.is_dir():
    app.mount("/miniapp", StaticFiles(directory=str(MINIAPP_DIR), html=True), name="miniapp")

PROVIDER_PANEL_DIR = Path(__file__).resolve().parent.parent / "provider_panel"
if PROVIDER_PANEL_DIR.is_dir():
    app.mount(
        "/provider-panel",
        StaticFiles(directory=str(PROVIDER_PANEL_DIR), html=True),
        name="provider-panel",
    )
