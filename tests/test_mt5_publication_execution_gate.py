import asyncio

import pytest
from pathlib import Path

from app.autotrade import api


@pytest.mark.parametrize(
    "receipt_status",
    [
        None,
        "",
        "NOT_RECEIVED",
        "REJECTED",
        "FAILED",
        "FAILED_RETRYABLE",
        "CLOSED",
        "IGNORED",
    ],
)
def test_mt5_signal_publication_fails_closed_without_accepted_receipt(
    monkeypatch, receipt_status
):
    def fake_live_state(_signal_id):
        return {"receipt_status": receipt_status} if receipt_status is not None else {}

    monkeypatch.setattr(api.db, "mt5_signal_live_state", fake_live_state)

    result = asyncio.run(
        api._publish_mt5_admin_signal_async({"id": 999999})
    )

    assert result["published"] is False
    assert result["complete"] is False
    assert result["free_message_id"] is None
    assert result["vip_message_id"] is None
    assert result["execution_status"] not in api.PUBLISHABLE_RECEIPT_STATUSES
    assert result["errors"]
    assert result["errors"][0].startswith("EXECUTION_GATE:")


def test_mt5_signal_publication_accepts_only_execution_truth_statuses():
    assert api.PUBLISHABLE_RECEIPT_STATUSES == {
        "EXECUTED",
        "PENDING",
        "ACTIVATED",
    }


def test_publisher_source_has_no_executed_default():
    source = (
        Path(api.__file__)
        .read_text(encoding="utf-8")
        .split("async def _publish_mt5_admin_signal_async", 1)[1]
        .split("def _publish_mt5_admin_signal(", 1)[0]
    )
    assert 'or "EXECUTED"' not in source
