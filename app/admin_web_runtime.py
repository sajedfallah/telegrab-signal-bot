from __future__ import annotations

import os
from pathlib import Path

from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

_INSTALLED = False


def install_admin_web_runtime() -> None:
    """Attach the Admin/User web control plane to the existing AutoTrade app.

    This is intentionally a runtime extension so the production AutoTrade API,
    risk firewall, signal numbering and live-event bridge remain authoritative.
    """
    global _INSTALLED
    if _INSTALLED:
        return

    from .admin_api import init_admin_schema, router
    from .admin_signal_runtime import router as signal_router
    from .autotrade.api import app

    init_admin_schema()

    if not any(getattr(route, "path", "").startswith("/api/v1/admin-web/auth") for route in app.routes):
        app.include_router(router)
    if not any(getattr(route, "path", "").startswith("/api/v1/admin-web/signals/issue") for route in app.routes):
        app.include_router(signal_router)

    origins = [
        item.strip()
        for item in os.getenv(
            "ADMIN_WEB_ORIGINS",
            "http://127.0.0.1:5173,http://localhost:5173",
        ).split(",")
        if item.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def _admin_web_security_headers(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/admin") or request.url.path.startswith("/api/v1/admin-web"):
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
            response.headers["Cache-Control"] = "no-store"
            if request.url.path.startswith("/admin"):
                response.headers["Content-Security-Policy"] = (
                    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                    "img-src 'self' data:; connect-src 'self' ws: wss:; frame-ancestors 'none'"
                )
        return response

    dist = Path(__file__).resolve().parent.parent / "admin-web" / "dist"
    if dist.exists() and not any(getattr(route, "path", "") == "/admin" for route in app.routes):
        app.mount("/admin", StaticFiles(directory=dist, html=True), name="admin-web")

    _INSTALLED = True
