from pathlib import Path

import app.autotrade_user_runtime as ux
import app.autotrade.live_event_runtime as live_bridge


ROOT = Path(__file__).resolve().parents[1]


class FakeDB:
    def mt5_account(self, user_id):
        return {"account_number": "10001"}

    def mt5_live_positions(self, account_number, nexus_only=True):
        assert account_number == "10001"
        assert nexus_only is True
        return [
            {
                "identifier": "77",
                "ticket": "9001",
                "signal_code": "NX-TEST",
                "symbol": "XAUUSD",
                "direction": "LONG",
                "volume": 0.10,
                "entry_price": 2500.0,
                "current_price": 2502.0,
                "stop_loss": 2490.0,
                "take_profit": 2520.0,
                "profit": 20.5,
                "status": "OPEN",
                "last_seen_at": "2026-09-04T12:00:00+00:00",
            }
        ]

    def get_signal_by_code(self, code):
        return {"code": code, "leverage": 100.0, "created_at": "2026-09-04T11:00:00+00:00"}

    def conn(self):
        raise RuntimeError("ledger unavailable in unit fake")


class FakeCore:
    db = FakeDB()

    @staticmethod
    def tr(lang, fa, en):
        return fa if lang == "fa" else en

    @staticmethod
    def get_lang(user_id):
        return "fa"

    @staticmethod
    def fmt_dt(raw):
        return str(raw)


def test_private_lifecycle_messages_cover_open_update_close():
    core = FakeCore()
    base = {
        "ticket": "9001",
        "signal_id": "NX-TEST",
        "symbol": "XAUUSD",
        "direction": "LONG",
        "volume": 0.10,
        "entry_price": 2500,
        "stop_loss": 2490,
        "take_profit": 2520,
        "profit": 0,
    }

    open_text, _ = ux._event_message(core, 123, {**base, "event": "OPEN", "event_id": "OPEN-1"})
    assert "معامله AutoTrade باز شد" in open_text
    assert "2490" in open_text and "2520" in open_text

    update_text, _ = ux._event_message(
        core,
        123,
        {**base, "event": "UPDATE", "event_id": "UPDATE-1", "volume": 0.05, "previous_volume": 0.10},
    )
    assert "تغییر در معامله AutoTrade" in update_text
    assert "0.1" in update_text and "0.05" in update_text

    close_text, _ = ux._event_message(
        core,
        123,
        {**base, "event": "CLOSE", "event_id": "CLOSE-1", "exit_price": 2512, "profit": 12.5, "close_reason": "CLIENT"},
    )
    assert "معامله AutoTrade بسته شد" in close_text
    assert "بستن دستی" in close_text
    assert "+12.50" in close_text


def test_open_trades_is_inline_flashcard_list_from_authoritative_live_cache():
    ux._OPEN_CACHE.clear()
    core = FakeCore()
    text, markup = ux._open_menu(core, 123, "fa", refresh=True)
    assert "تعداد پوزیشن‌های فعال" in text
    buttons = [button for row in markup.inline_keyboard for button in row]
    trade_buttons = [b for b in buttons if (b.callback_data or "").startswith("autotrade_position:")]
    assert len(trade_buttons) == 1
    assert trade_buttons[0].callback_data == "autotrade_position:9001"
    assert "XAUUSD" in trade_buttons[0].text
    assert "PnL +20.50" in trade_buttons[0].text


def test_position_flashcard_has_required_live_fields_and_account_scoped_ticket():
    ux._OPEN_CACHE.clear()
    core = FakeCore()
    card = ux._position_card(core, 123, "fa", "9001")
    assert card is not None
    text, markup = card
    for label in ("نماد", "جهت", "حجم", "لوریج", "ورود", "استاپ فعلی", "تیک‌پروفیت فعلی", "قیمت فعلی", "PnL لحظه‌ای", "مدت باز بودن", "وضعیت", "Ticket"):
        assert label in text
    assert "XAUUSD" in text and "100x" in text and "+20.50" in text
    assert ux._position_card(core, 123, "fa", "NOT-MINE") is None
    callbacks = {b.callback_data for row in markup.inline_keyboard for b in row}
    assert "autotrade_open" in callbacks


def test_partial_volume_change_is_bridged_into_durable_queue(monkeypatch):
    captured = []
    monkeypatch.setattr(live_bridge, "_customer_for_account", lambda account: 123)
    monkeypatch.setattr(live_bridge.db, "enqueue_autotrade_trade_event", lambda uid, event, payload, ticket: captured.append((uid, event, payload, ticket)))

    before = {
        "77": {
            "identifier": "77",
            "ticket": "9001",
            "signal_code": "NX-TEST",
            "symbol": "XAUUSD",
            "direction": "LONG",
            "volume": 0.10,
        }
    }
    after = [{
        "identifier": "77",
        "ticket": "9001",
        "signal_code": "NX-TEST",
        "symbol": "XAUUSD",
        "direction": "LONG",
        "volume": 0.05,
        "entry_price": 2500,
        "stop_loss": 2490,
        "take_profit": 2520,
        "profit": 7.5,
    }]
    live_bridge._emit_volume_updates("10001", before, after)
    assert len(captured) == 1
    uid, event, payload, ticket = captured[0]
    assert uid == 123 and event == "UPDATE" and ticket == "9001"
    assert payload["previous_volume"] == 0.10
    assert payload["volume"] == 0.05
    assert payload["change_source"] == "LIVE_SNAPSHOT_VOLUME"


def test_runtime_installation_and_config_contracts_are_wired():
    run_py = (ROOT / "run.py").read_text(encoding="utf-8")
    run_api = (ROOT / "run_api.py").read_text(encoding="utf-8")
    env = (ROOT / ".env.example").read_text(encoding="utf-8")
    source = (ROOT / "app" / "autotrade_user_runtime.py").read_text(encoding="utf-8")

    assert "install_autotrade_user_experience(core_main)" in run_py
    assert "install_live_snapshot_event_bridge()" in run_api
    assert "AUTOTRADE_NOTIFICATION_TTL_SECONDS" in env
    assert "AUTOTRADE_NOTIFICATION_POLL_SECONDS=0.5" in env
    assert "AUTOTRADE_OPEN_TRADES_CACHE_SECONDS=2" in env
    assert "pending_autotrade_notifications(100)" in source
    assert "mt5_live_positions(account, nexus_only=True)" in source
    assert "autotrade_user_signal_receipts" not in source
