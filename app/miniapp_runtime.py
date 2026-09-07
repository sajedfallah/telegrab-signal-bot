from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl

from fastapi import FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
MINIAPP_DIR = ROOT / "miniapp"


def _telegram_user(init_data: str, bot_token: str, max_age_seconds: int = 86400) -> dict[str, Any] | None:
    if not init_data or not bot_token:
        return None
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", "")
    if not received_hash:
        return None
    data_check_string = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    expected = hmac.new(secret, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received_hash):
        return None
    try:
        auth_date = int(pairs.get("auth_date", "0"))
    except ValueError:
        return None
    if auth_date <= 0 or abs(int(time.time()) - auth_date) > max_age_seconds:
        return None
    try:
        user = json.loads(pairs.get("user", "{}"))
    except json.JSONDecodeError:
        return None
    return user if isinstance(user, dict) else None


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _plans() -> list[dict[str, str]]:
    return [
        {"code": "30", "title": "VIP 30 روزه", "period": "30 روز", "price": _env("PLAN_30_PRICE", "—")},
        {"code": "90", "title": "VIP 90 روزه", "period": "90 روز", "price": _env("PLAN_90_PRICE", "—")},
        {"code": "180", "title": "VIP 180 روزه", "period": "180 روز", "price": _env("PLAN_180_PRICE", "—")},
    ]


def install_miniapp(app: FastAPI) -> None:
    if getattr(app.state, "nexus_miniapp_installed", False):
        return

    @app.get("/api/miniapp/health")
    async def miniapp_health() -> dict[str, Any]:
        return {"ok": True, "service": "nexus-miniapp", "version": "v1-v4"}

    @app.get("/api/miniapp/bootstrap")
    async def miniapp_bootstrap(x_telegram_init_data: str | None = Header(default=None)) -> dict[str, Any]:
        init_data = x_telegram_init_data or ""
        user = None
        if init_data:
            user = _telegram_user(init_data, _env("BOT_TOKEN"))
            if user is None:
                raise HTTPException(status_code=401, detail="invalid Telegram Mini App session")

        public_url = _env("NEXUS_FOLDER_URL", _env("PUBLIC_CHANNEL_URL", "https://t.me/nexus_publicc"))
        free_url = _env("FREE_CHANNEL_URL", public_url)
        support_raw = _env("SUPPORT_USERNAME", "")
        support_url = support_raw if support_raw.startswith("http") else (f"https://t.me/{support_raw.lstrip('@')}" if support_raw else public_url)

        return {
            "version": "v1-v4",
            "account": {"is_authenticated": bool(user), "user": user or {}},
            "links": {
                "public_channel": public_url,
                "free_channel": free_url,
                "support": support_url,
            },
            "plans": _plans(),
            "products": [
                {"code": "autotrade", "title": "NEXUS AutoTrade", "description": "اجرای خودکار سیگنال‌های NEXUS روی MetaTrader 5"},
            ],
            "ui": {
                "home_show_products": False,
                "home_show_ea_status": False,
                "home_show_today_status": False,
                "signals": ["free", "vip"],
            },
        }

    if MINIAPP_DIR.exists():
        app.mount("/miniapp", StaticFiles(directory=str(MINIAPP_DIR), html=True), name="nexus-miniapp")

    app.state.nexus_miniapp_installed = True
