from pathlib import Path


def _ea_source() -> str:
    root = Path(__file__).resolve().parents[1]
    return (root / "mt5/NEXUS_AutoTrade/NEXUS_AutoTrade.mq5").read_text(encoding="utf-8")


def _build_reconcile_block() -> str:
    ea = _ea_source()
    start = ea.index("string BuildReconcileItem(")
    end = ea.index("\nvoid ReconcileMT5History()", start)
    return ea[start:end]


def test_build_reconcile_item_serializes_risk_fields_before_identity_fields():
    block = _build_reconcile_block()

    assert '\\"risk_cash\\\":%s' in block
    assert '\\"realized_r\\\":%s' in block
    assert block.index('\\"risk_cash\\":%s') < block.index('\\"position_id\\":\\"%I64d\\"')
    assert block.index('\\"realized_r\\":%s') < block.index('\\"position_id\\":\\"%I64d\\"')


def test_build_reconcile_item_emits_real_event_time_and_epoch_milliseconds():
    block = _build_reconcile_block()

    assert "ReconcileIsoEventTime(event_time)" in block
    assert "(long)event_time*1000" in block
    assert '(long)r.identifier,(ulong)anchor,"",' not in block


def test_build_reconcile_item_keeps_placeholder_argument_alignment_contract():
    block = _build_reconcile_block()

    # Assert the exact tail of the StringFormat argument list. There are two
    # `(ulong)anchor` arguments in this call (ticket and deal_id), so generic
    # first-occurrence ordering checks are ambiguous and can false-fail.
    expected_tail = (
        "DoubleToString(r.commission,8),DoubleToString(r.swap,8),DoubleToString(r.risk_cash,8),\n"
        "      DoubleToString(r.risk_cash>0.0 ? profit/r.risk_cash : 0.0,8),(long)r.identifier,(ulong)anchor,ReconcileIsoEventTime(event_time),\n"
        "      (long)event_time*1000);"
    )
    assert expected_tail in block
