from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_topic_route_is_configurable_and_injects_message_thread_id():
    src = _text("app/telegram_topic_routing.py")
    assert 'FREE_SIGNAL_CHAT_ID' in src
    assert 'FREE_SIGNAL_TOPIC_ID' in src
    assert 'settings.free_channel_target' in src
    assert 'message_thread_id' in src


def test_bot_and_autotrade_api_install_same_topic_router_before_runtime():
    bot_runner = _text("run.py")
    api_runner = _text("run_api.py")
    assert "install_free_topic_routing()" in bot_runner

    # v0.6.5 imports the core module as `import app.main as main_module`, while
    # older releases used `from app.main import ...`. Either form is valid; the
    # invariant is that FREE topic routing is installed before app.main loads.
    core_import_positions = [
        pos
        for marker in ("import app.main as main_module", "from app.main import")
        if (pos := bot_runner.find(marker)) >= 0
    ]
    assert core_import_positions
    assert bot_runner.index("install_free_topic_routing()") < min(core_import_positions)

    assert "install_free_topic_routing()" in api_runner
    assert api_runner.index("install_free_topic_routing()") < api_runner.index('"app.autotrade.api:app"')


def test_topic_id_admin_command_is_registered():
    runner = _text("run.py")
    topic_admin = _text("app/topic_admin.py")
    assert "topic_admin_router" in runner
    assert "include_router(topic_admin_router)" in runner
    assert 'Command("topicid", "setfreetopic")' in topic_admin
    assert "message.message_thread_id" in topic_admin


def test_mt5_free_destination_contract_stays_logical_and_backend_routed():
    ea = _text("mt5/NEXUS_AutoTrade/NEXUS_AutoTrade.mq5")
    api = _text("app/autotrade/api.py")
    assert 'g_manual_destination="FREE"' in ea
    assert 'g_manual_destination!="FREE"' in ea
    assert "g_api.IssueAdminSignal" in ea
    assert "g_manual_destination,reqid" in ea
    assert 'destination: str = Field(default="BOTH", pattern="^(?:FREE|VIP|BOTH)$")' in api
    assert "settings.free_channel_target" in api


def test_env_example_documents_topic_route():
    env = _text(".env.example")
    assert "FREE_SIGNAL_CHAT_ID=" in env
    assert "FREE_SIGNAL_TOPIC_ID=" in env
