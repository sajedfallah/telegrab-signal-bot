from __future__ import annotations

from pathlib import Path

from fastapi.staticfiles import StaticFiles

from .autotrade.api import app
from .miniapp_api import router as miniapp_router


# The existing AutoTrade API stays the root FastAPI application/source of truth.
# Mini App endpoints are added to the same process and therefore share the same
# SQLite database, subscription engine, pricing service and bot configuration.
app.include_router(miniapp_router)

MINIAPP_DIR = Path(__file__).resolve().parent.parent / "miniapp"
if MINIAPP_DIR.is_dir():
    app.mount("/miniapp", StaticFiles(directory=str(MINIAPP_DIR), html=True), name="miniapp")
