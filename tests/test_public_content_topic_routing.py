from types import SimpleNamespace

from app.content.routing import resolve_channel_destination
from app.services import market_content_route_runtime
from app.services import market_public_channel_runtime


def test_public_daily_content_resolves_to_configured_forum_topic(monkeypatch):
    monkeypatch.setenv("PUBLIC_CONTENT_CHAT_ID", "-1003982028478")
    monkeypatch.setenv("PUBLIC_CONTENT_TOPIC_ID", "8")
    monkeypatch.setenv("PUBLIC_CONTENT_URL", "https://t.me/nexus_publik")

    settings = SimpleNamespace(
        public_channel_id=-1001111111111,
        public_channel_url="https://t.me/legacy_public",
    )
    destination = resolve_channel_destination(settings, "daily_analysis")

    assert destination.chat_id == -1003982028478
    assert destination.message_thread_id == 8
    assert destination.channel_url == "https://t.me/nexus_publik"


def test_market_runtime_uses_same_public_content_chat(monkeypatch):
    monkeypatch.setenv("PUBLIC_CONTENT_CHAT_ID", "-1003982028478")
    monkeypatch.setenv("PUBLIC_CONTENT_TOPIC_ID", "8")

    messages = []
    fake_main = SimpleNamespace(
        settings=SimpleNamespace(public_channel_id=-1001111111111),
        log=SimpleNamespace(info=lambda *args, **kwargs: messages.append(args)),
    )

    market_content_route_runtime.install(fake_main)

    assert market_public_channel_runtime._public_target(fake_main) == -1003982028478
    assert market_content_route_runtime._configured_topic_id() == 8
