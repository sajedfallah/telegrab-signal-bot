from __future__ import annotations

from pathlib import Path

from fastapi.staticfiles import StaticFiles

from .autotrade.api import app
from .miniapp_api import router as miniapp_router
from .miniapp_experience import router as miniapp_experience_router
from .miniapp_home import router as miniapp_home_router
from .miniapp_signals import router as miniapp_signals_router
from .miniapp_performance import router as miniapp_performance_router
from .miniapp_trades import router as miniapp_trades_router
from .miniapp_checkout import router as miniapp_checkout_router
from .miniapp_account import router as miniapp_account_router


# The existing AutoTrade API stays the root FastAPI application/source of truth.
# Mini App endpoints are added to the same process and therefore share the same
# SQLite database, subscription engine, pricing service and bot configuration.
app.include_router(miniapp_router)
app.include_router(miniapp_experience_router)
app.include_router(miniapp_home_router)
app.include_router(miniapp_signals_router)
app.include_router(miniapp_performance_router)
app.include_router(miniapp_trades_router)
app.include_router(miniapp_checkout_router)
app.include_router(miniapp_account_router)

MINIAPP_DIR = Path(__file__).resolve().parent.parent / "miniapp"
if MINIAPP_DIR.is_dir():
    app.mount("/miniapp", StaticFiles(directory=str(MINIAPP_DIR), html=True), name="miniapp")
