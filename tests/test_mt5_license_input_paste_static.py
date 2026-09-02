from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EA = (ROOT / "mt5" / "NEXUS_AutoTrade" / "NEXUS_AutoTrade.mq5").read_text(encoding="utf-8")

def test_license_edit_box_is_explicitly_editable_and_focusable():
    assert '#property version   "1.65"' in EA
    assert 'OBJPROP_READONLY,false' in EA
    assert 'OBJPROP_ALIGN,ALIGN_LEFT' in EA
    assert 'OBJPROP_SELECTABLE,false' in EA
    assert 'OBJPROP_ZORDER,100' in EA
    assert 'Click License box, then type or press Ctrl+V to paste.' in EA
