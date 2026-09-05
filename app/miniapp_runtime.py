from __future__ import annotations

from pathlib import Path

from fastapi.staticfiles import StaticFiles

_INSTALLED = False


def install_miniapp_runtime() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from .miniapp_api import ensure_schema, router
    from .autotrade.api import app

    ensure_schema()

    if not any(getattr(route, "path", "").startswith("/api/v1/miniapp") for route in app.routes):
        app.include_router(router)

    @app.middleware("http")
    async def _miniapp_security_headers(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/miniapp") or request.url.path.startswith("/api/v1/miniapp"):
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
            response.headers["Cache-Control"] = "no-store"
            if request.url.path.startswith("/miniapp"):
                response.headers["Content-Security-Policy"] = (
                    "default-src 'self'; script-src 'self' https://telegram.org; "
                    "style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; "
                    "connect-src 'self' https: wss:; "
                    "frame-ancestors https://web.telegram.org https://*.telegram.org"
                )
        return response

    dist = Path(__file__).resolve().parent.parent / "telegram-miniapp" / "dist"
    if dist.exists() and not any(getattr(route, "path", "") == "/miniapp" for route in app.routes):
        app.mount("/miniapp", StaticFiles(directory=dist, html=True), name="telegram-miniapp")

    _INSTALLED = True
