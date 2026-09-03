from app.autotrade.result_card_guard import format_result_card


def test_broker_close_result_card_contains_only_required_fields():
    row = {
        "code": "NX-0001",
        "symbol": "XAUUSD",
        "direction": "BUY",
        "entry_price": 4493,
    }
    legacy = (
        "TRADE CLOSED | NX-0001 | XAUUSD | direction=BUY | exit=4481.66 | "
        "pnl=-10.64 | result=LOSS | performance=-113.4 PIPS | "
        "duration=00:46:16 | reason=STOP LOSS | ticket=76393505"
    )

    card = format_result_card(row, legacy)

    assert "<b>NX-0001</b>  <b>🔴 LOSS</b>" in card
    assert "🏁 Exit: <code>4481.66</code>" in card
    assert "💰 Broker P/L: <b>-10.64</b>" in card
    assert "⏱️ Duration: <b>00:46:16</b>" in card
    assert "🚪 Exit Reason: <b>STOP LOSS</b>" in card
    assert "📌 Status: <b>CLOSED</b>" in card

    # Explicit product rule: these details belong to the original signal or
    # internal execution history, not the final result flash card.
    assert "Symbol:" not in card
    assert "Direction:" not in card
    assert "Entry:" not in card
    assert "Performance:" not in card
    assert "Ticket:" not in card
    assert "NEXUS RESULT" not in card


def test_manual_result_keeps_required_shape_without_fake_broker_pnl():
    row = {"code": "NX-0002", "entry_price": 100}
    legacy = (
        "TRADE RESULT — NX-0002\n"
        "Entry: 100\n"
        "Exit: 101\n"
        "Result: WIN\n"
        "P/L: +10 PIPS\n"
        "Exit type: MANUAL CLOSE"
    )

    card = format_result_card(row, legacy)

    assert "<b>NX-0002</b>  <b>🟢 WIN</b>" in card
    assert "🏁 Exit: <code>101</code>" in card
    assert "💰 Broker P/L: <b>—</b>" in card
    assert "⏱️ Duration: <b>—</b>" in card
    assert "🚪 Exit Reason: <b>MANUAL CLOSE</b>" in card
    assert "📌 Status: <b>CLOSED</b>" in card
    assert "+10 PIPS" not in card
