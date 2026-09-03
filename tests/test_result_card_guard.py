from app.autotrade.result_card_guard import format_result_card


def _row():
    return {
        "code": "NX-0004",
        "symbol": "XAUUSD",
        "direction": "SELL",
        "entry_price": 4384.0,
    }


def _assert_minimal_shape(card: str) -> None:
    assert "📌 Status: <b>CLOSED</b>" in card
    assert "📌 Symbol:" not in card
    assert "↕️ Direction:" not in card
    assert "📍 Entry:" not in card
    assert "📊 Performance:" not in card
    assert "🎫 Ticket:" not in card
    assert "NEXUS RESULT" not in card


def test_mt5_compact_close_becomes_canonical_minimal_result_card():
    compact = (
        "TRADE CLOSED | NX-0004 | XAUUSD | direction=SELL | exit=4383.23 | "
        "pnl=+2.61 | result=WIN | performance=+7.7 PIPS | duration=00:06:54 | "
        "reason=MANUAL CLOSE | ticket=75990511"
    )

    card = format_result_card(_row(), compact)

    assert "<b>NX-0004</b>  <b>🟢 WIN</b>" in card
    assert "🏁 Exit: <code>4383.23</code>" in card
    assert "💰 Broker P/L: <b>+2.61</b>" in card
    assert "⏱️ Duration: <b>00:06:54</b>" in card
    assert "🚪 Exit Reason: <b>MANUAL CLOSE</b>" in card
    assert "TRADE CLOSED |" not in card
    _assert_minimal_shape(card)


def test_manual_english_result_becomes_same_minimal_card_without_fake_broker_pnl():
    old = (
        "<b>📌 TRADE RESULT — NX-0004</b>\n"
        "Symbol: <b>XAUUSD</b>\n"
        "Direction: <b>SELL</b>\n\n"
        "Entry: <code>4384</code>\n"
        "Exit: <code>4383.23</code>\n\n"
        "Result: <b>WIN</b>\n"
        "P/L: <b>+7.7 PIPS</b>\n"
        "Exit type: <b>MANUAL CLOSE</b>"
    )

    card = format_result_card(_row(), old)

    assert "<b>NX-0004</b>  <b>🟢 WIN</b>" in card
    assert "🏁 Exit: <code>4383.23</code>" in card
    assert "💰 Broker P/L: <b>—</b>" in card
    assert "⏱️ Duration: <b>—</b>" in card
    assert "🚪 Exit Reason: <b>MANUAL CLOSE</b>" in card
    assert "+7.7 PIPS" not in card
    _assert_minimal_shape(card)


def test_manual_persian_result_becomes_same_minimal_card_without_fake_broker_pnl():
    old = (
        "<b>📌 نتیجه معامله — NX-0004</b>\n"
        "نماد: <b>XAUUSD</b>\n"
        "جهت: <b>فروش</b>\n\n"
        "ورود: <code>4384</code>\n"
        "خروج: <code>4383.23</code>\n\n"
        "نتیجه: <b>برد</b>\n"
        "سود/زیان: <b>+7.7 PIPS</b>\n"
        "نوع خروج: <b>بستن دستی</b>"
    )

    card = format_result_card(_row(), old)

    assert "<b>NX-0004</b>  <b>🟢 WIN</b>" in card
    assert "🏁 Exit: <code>4383.23</code>" in card
    assert "💰 Broker P/L: <b>—</b>" in card
    assert "⏱️ Duration: <b>—</b>" in card
    assert "🚪 Exit Reason: <b>بستن دستی</b>" in card
    assert "+7.7 PIPS" not in card
    _assert_minimal_shape(card)


def test_non_result_lifecycle_caption_is_unchanged():
    text = "Stop loss moved to break even"
    assert format_result_card(_row(), text) == text


def test_formatter_is_idempotent():
    compact = "TRADE CLOSED | NX-0004 | XAUUSD | direction=SELL | exit=4383.23 | pnl=+2.61 | result=WIN | performance=+7.7 PIPS | reason=MANUAL CLOSE | ticket=75990511"
    first = format_result_card(_row(), compact)
    assert format_result_card(_row(), first) == first
