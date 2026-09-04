from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_legacy_market_public_runtime(request, monkeypatch):
    """Keep the legacy market-public unit tests independent of runtime install order.

    The production bootstrap intentionally installs a process-wide canonical
    PUBLIC_CONTENT route. A different test module imports that bootstrap, so a
    full-suite run can leave ``market_public_channel_runtime._public_target``
    patched before the legacy unit tests execute. Those unit tests are meant to
    validate the standalone fallback runtime itself, not the dedicated Topic 8
    adapter. Reset only that module's target resolver for test isolation.

    Canonical PUBLIC_CONTENT_CHAT_ID / PUBLIC_CONTENT_TOPIC_ID behavior remains
    covered by the dedicated public-content routing regression tests.
    """
    if request.module.__name__ != "tests.test_v065_market_public_channel_runtime":
        yield
        return

    from app.services import market_public_channel_runtime as runtime

    def _standalone_public_target(main):
        target = getattr(main.settings, "public_channel_id", None)
        if target is None or str(target).strip() in {"", "0", "None"}:
            raise RuntimeError("NEXUS public channel is not configured")
        return target

    monkeypatch.setattr(runtime, "_public_target", _standalone_public_target)
    yield
