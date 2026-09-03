from __future__ import annotations

import asyncio
from pathlib import Path

from app.services.autotrade_delivery_service import AutoTradeDeliveryError, deliver_mt5_package


class FakeBot:
    def __init__(self, *, fail_document: int = 0, fail_video: int = 0):
        self.fail_document = fail_document
        self.fail_video = fail_video
        self.calls: list[tuple[str, dict]] = []

    async def send_document(self, chat_id, **kwargs):
        self.calls.append(("document", {"chat_id": chat_id, **kwargs}))
        if self.fail_document > 0:
            self.fail_document -= 1
            raise RuntimeError("document transport failure")
        return object()

    async def send_video(self, chat_id, **kwargs):
        self.calls.append(("video", {"chat_id": chat_id, **kwargs}))
        if self.fail_video > 0:
            self.fail_video -= 1
            raise RuntimeError("video transport failure")
        return object()

    async def send_message(self, chat_id, text, **kwargs):
        self.calls.append(("message", {"chat_id": chat_id, "text": text, **kwargs}))
        return object()


def _assets(tmp_path: Path) -> tuple[Path, Path]:
    ex5 = tmp_path / "NEXUS_AutoTrade.ex5"
    guide = tmp_path / "NEXUS_AutoTrade_MT5_Guide.mp4"
    ex5.write_bytes(b"ex5")
    guide.write_bytes(b"video")
    return ex5, guide


def test_delivery_order_and_protection(tmp_path):
    ex5, guide = _assets(tmp_path)
    bot = FakeBot()

    report = asyncio.run(
        deliver_mt5_package(
            bot,
            123,
            ex5_path=ex5,
            guide_video_path=guide,
            admin_ids=(999,),
            attempts=1,
            base_delay_seconds=0,
        )
    )

    assert report.ex5_sent is True
    assert report.video_sent is True
    assert [name for name, _ in bot.calls] == ["document", "video"]
    assert bot.calls[0][1]["protect_content"] is True
    assert bot.calls[1][1]["protect_content"] is True
    assert bot.calls[1][1]["supports_streaming"] is True


def test_transient_document_failure_is_retried_before_video(tmp_path):
    ex5, guide = _assets(tmp_path)
    bot = FakeBot(fail_document=2)

    asyncio.run(
        deliver_mt5_package(
            bot,
            123,
            ex5_path=ex5,
            guide_video_path=guide,
            attempts=3,
            base_delay_seconds=0,
        )
    )

    assert [name for name, _ in bot.calls] == ["document", "document", "document", "video"]


def test_final_video_failure_alerts_admin_after_ex5_was_sent(tmp_path):
    ex5, guide = _assets(tmp_path)
    bot = FakeBot(fail_video=3)

    try:
        asyncio.run(
            deliver_mt5_package(
                bot,
                123,
                ex5_path=ex5,
                guide_video_path=guide,
                admin_ids=(999,),
                attempts=3,
                base_delay_seconds=0,
            )
        )
    except AutoTradeDeliveryError as exc:
        assert exc.stage == "guide_video"
        assert exc.ex5_sent is True
        assert exc.video_sent is False
    else:
        raise AssertionError("expected AutoTradeDeliveryError")

    assert [name for name, _ in bot.calls[:4]] == ["document", "video", "video", "video"]
    assert bot.calls[-1][0] == "message"
    assert bot.calls[-1][1]["chat_id"] == 999


def test_missing_video_does_not_undo_successful_ex5_delivery(tmp_path):
    ex5 = tmp_path / "NEXUS_AutoTrade.ex5"
    ex5.write_bytes(b"ex5")
    missing_guide = tmp_path / "missing.mp4"
    bot = FakeBot()

    try:
        asyncio.run(
            deliver_mt5_package(
                bot,
                123,
                ex5_path=ex5,
                guide_video_path=missing_guide,
                admin_ids=(999,),
                attempts=1,
                base_delay_seconds=0,
            )
        )
    except AutoTradeDeliveryError as exc:
        assert exc.stage == "guide_video_missing"
        assert exc.ex5_sent is True
    else:
        raise AssertionError("expected AutoTradeDeliveryError")

    assert bot.calls[0][0] == "document"
    assert bot.calls[-1][0] == "message"
