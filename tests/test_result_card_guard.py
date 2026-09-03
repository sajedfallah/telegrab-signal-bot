from app.autotrade.result_card_guard import format_result_card


def _row():
    return {
        "code": "NX-0004",
        "symbol": "XAUUSD",
        "direction": "SELL",
        "entry_price": 4384.0,
    }


def test_mt5_compact_close_becomes_canonical_result_card():
    compact = (
        "TRADE CLOSED | NX-0004 | XAUUSD | direction=SELL | exit=4383.23 | "
        "pnl=+2.61 | result=WIN | performance=+7.7 PIPS | duration=00:06:54 | "
        "reason=MANUAL CLOSE | ticket=75990511"
    )

    card = format_result_card(_row(), compact)

    assert "━━━━━━━━ NEXUS RESULT ━━━━━━━━" in card
    assert "<b>NX-0004</b>" in card
    assert "🟢 WIN" in card
    assert "📌 Symbol: <b>XAUUSD</b>" in card
    assert "↕️ Direction: <b>SELL</b>" in card
    assert "📍 Entry: <code>4384</code>" in card
    assert "🏁 Exit: <code>4383.23</code>" in card
    assert "💰 Broker P/L: <b>+2.61</b>" in card
    assert "📊 Performance: <b>+7.7 PIPS</b>" in card
    assert "⏱ Duration: <b>00:06:54</b>" in card
    assert "🚪 Exit Reason: <b>MANUAL CLOSE</b>" in card
    assert "🎫 Ticket: <code>75990511</code>" in card
    assert "📌 Status: <b>CLOSED</b>" in card
    assert "TRADE CLOSED |" not in card


def test_manual_english_result_becomes_same_canonical_card():
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

    assert "━━━━━━━━ NEXUS RESULT ━━━━━━━━" in card
    assert "🟢 WIN" in card
    assert "🏁 Exit: <code>4383.23</code>" in card
    assert "📊 Performance: <b>+7.7 PIPS</b>" in card
    assert "🚪 Exit Reason: <b>MANUAL CLOSE</b>" in card
    assert "Broker P/L" not in card


def test_manual_persian_result_becomes_same_ltr_canonical_card():
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

    assert "━━━━━━━━ NEXUS RESULT ━━━━━━━━" in card
    assert "🟢 WIN" in card
    assert "📌 Symbol: <b>XAUUSD</b>" in card
    assert "↕️ Direction: <b>SELL</b>" in card
    assert "🏁 Exit: <code>4383.23</code>" in card
    assert "📊 Performance: <b>+7.7 PIPS</b>" in card
    assert "🚪 Exit Reason: <b>بستن دستی</b>" in card


def test_non_result_lifecycle_caption_is_unchanged():
    text = "Stop loss moved to break even"
    assert format_result_card(_row(), text) == text


def test_formatter_is_idempotent():
    compact = "TRADE CLOSED | NX-0004 | XAUUSD | direction=SELL | exit=4383.23 | pnl=+2.61 | result=WIN | performance=+7.7 PIPS | reason=MANUAL CLOSE | ticket=75990511"
    first = format_result_card(_row(), compact)
    assert format_result_card(_row(), first) == first
