from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MAIN=(ROOT/"app/main.py").read_text(encoding="utf-8")
EA=(ROOT/"mt5/NEXUS_AutoTrade/NEXUS_AutoTrade.mq5").read_text(encoding="utf-8")

def test_irr_invoice_is_direct_receipt_state():
    block=MAIN.split('@router.callback_query(F.data.startswith("method:"))',1)[1].split('@router.callback_query(F.data.startswith("receipt:"))',1)[0]
    assert 'await state.set_state(Flow.waiting_receipt)' in block
    assert 'payment_actions(lang, code, method)' not in block

def test_usdt_invoice_directly_waits_for_txid():
    block=MAIN.split('@router.callback_query(F.data.startswith("method:"))',1)[1].split('@router.callback_query(F.data.startswith("receipt:"))',1)[0]
    assert 'await state.set_state(Flow.waiting_usdt_txid)' in block

def test_mt5_license_edit_uses_native_edit_focus():
    assert '#property version   "1.65"' in EA
    assert 'OBJPROP_READONLY,false' in EA
    assert 'OBJPROP_SELECTABLE,false' in EA
    assert 'CHARTEVENT_OBJECT_ENDEDIT' in EA
    assert 'CHART_KEYBOARD_CONTROL,false' in EA
    assert 'type or press Ctrl+V to paste' in EA
