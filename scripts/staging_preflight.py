"""Read-only preflight for the NEXUS v0.6.5 staging API.

This deliberately does not authenticate, create a signal, claim a job, or
call Telegram.  It proves that the staging runtime exposes the canonical
health endpoint and the routes required before a human-approved E2E run.
"""

from __future__ import annotations

import argparse
import json
from typing import Any
from urllib.request import urlopen


REQUIRED_PATHS = {
    "/api/v1/autotrade/admin/chart-capture/next",
    "/api/v1/admin-web/signals/issue",
    "/api/v1/miniapp/session",
}


def _get_json(url: str, timeout: float) -> dict[str, Any]:
    with urlopen(url, timeout=timeout) as response:  # noqa: S310 - explicit operator supplied staging URL
        return json.loads(response.read().decode("utf-8"))


def preflight(base_url: str, *, timeout: float = 5.0) -> dict[str, Any]:
    base = base_url.rstrip("/")
    health = _get_json(f"{base}/api/v1/autotrade/health", timeout)
    schema = _get_json(f"{base}/openapi.json", timeout)
    paths = set((schema.get("paths") or {}).keys())
    missing = sorted(REQUIRED_PATHS - paths)
    return {
        "ok": bool(health.get("ok")) and not missing,
        "service": health.get("service"),
        "version": health.get("version"),
        "missing_required_paths": missing,
        "note": "read-only preflight; no signal, job, or Telegram call was made",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only NEXUS staging preflight")
    parser.add_argument("--base-url", default="http://127.0.0.1:18080")
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args()
    try:
        report = preflight(args.base_url, timeout=args.timeout)
    except Exception as exc:  # pragma: no cover - exercised on the target host
        print(json.dumps({"ok": False, "error": type(exc).__name__, "detail": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
