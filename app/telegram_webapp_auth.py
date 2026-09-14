from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any
from urllib.parse import parse_qsl

from fastapi import HTTPException


def validate_init_data(
    raw: str,
    *,
    bot_token: str,
    max_age_seconds: int = 86400,
    now: int | None = None,
) -> dict[str, Any]:
    """Validate Telegram WebApp initData without importing NEXUS application config.

    The caller owns secret selection. This keeps authentication reusable for the
    provider surface while preserving Telegram's HMAC verification contract.
    """
    if not raw:
        raise HTTPException(status_code=401, detail="missing Telegram init data")
    if not bot_token:
        raise HTTPException(status_code=500, detail="Telegram bot token is not configured")

    values = dict(parse_qsl(raw, keep_blank_values=True))
    received_hash = values.pop("hash", "")
    if not received_hash:
        raise HTTPException(status_code=401, detail="invalid Telegram init data")

    data_check_string = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_hash, received_hash):
        raise HTTPException(status_code=401, detail="invalid Telegram init data")

    try:
        auth_date = int(values.get("auth_date", "0"))
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="invalid Telegram auth date") from exc
    current = int(time.time()) if now is None else int(now)
    if auth_date <= 0 or current - auth_date > max_age_seconds or auth_date - current > 60:
        raise HTTPException(status_code=401, detail="expired Telegram init data")

    try:
        user = json.loads(values.get("user", "{}"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=401, detail="invalid Telegram user payload") from exc
    if not isinstance(user, dict) or not user.get("id"):
        raise HTTPException(status_code=401, detail="missing Telegram user")
    return user
