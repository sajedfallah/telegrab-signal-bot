import importlib.util
import io
import json
from pathlib import Path


SCRIPT = Path("scripts/staging_preflight.py")


def _module():
    spec = importlib.util.spec_from_file_location("staging_preflight", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def test_preflight_is_read_only_and_checks_integrated_routes(monkeypatch):
    module = _module()
    calls = []

    def fake_open(url, timeout):
        calls.append((url, timeout))
        if url.endswith("/health"):
            return _Response({"ok": True, "service": "nexus-autotrade", "version": "0.6.5"})
        return _Response({"paths": {path: {} for path in module.REQUIRED_PATHS}})

    monkeypatch.setattr(module, "urlopen", fake_open)
    report = module.preflight("http://127.0.0.1:18080")
    assert report["ok"] is True
    assert report["missing_required_paths"] == []
    assert len(calls) == 2
    assert all("chart-capture/next" not in url for url, _ in calls)
    assert "read-only" in report["note"]
