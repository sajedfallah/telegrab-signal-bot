from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest
from fastapi import HTTPException

from app.config import settings
from app.miniapp_api import _validate_init_data


def _signed_init_data(user_id: int = 123456789) -> str:
    values = {
        "auth_date": str(int(time.time())),
        "query_id": "AAE-test-query",
        "user": json.dumps({"id": user_id, "first_name": "NEXUS", "username": "nexus_test"}, separators=(",", ":")),
    }
    check = "\n".join(f"{k}={values[k]}" for k in sorted(values))
    secret = hmac.new(b"WebAppData", settings.bot_token.encode("utf-8"), hashlib.sha256).digest()
    values["hash"] = hmac.new(secret, check.encode("utf-8"), hashlib.sha256).hexdigest()
    return urlencode(values)


def test_miniapp_init_data_signature_accepts_valid_user():
    user = _validate_init_data(_signed_init_data())
    assert int(user["id"]) == 123456789
    assert user["username"] == "nexus_test"


def test_miniapp_init_data_signature_rejects_tampering():
    raw = _signed_init_data().replace("nexus_test", "attacker")
    with pytest.raises(HTTPException) as exc:
        _validate_init_data(raw)
    assert exc.value.status_code == 401


def test_combined_api_exposes_miniapp_routes_and_static_mount():
    from app.combined_api import app

    paths = {getattr(route, "path", "") for route in app.routes}
    assert "/miniapp/api/health" in paths
    assert "/miniapp/api/bootstrap" in paths
    assert "/miniapp/api/invoices" in paths
    assert "/miniapp/api/receipts" in paths
    assert "/miniapp" in paths
