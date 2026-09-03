from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from aiogram.enums import ChatType
from aiogram.types import Chat, Message, User

from app.services import chat_hygiene_runtime as svc


class _FakeDB:
    def __init__(self, last_menu_message_id=9):
        self.last_menu_message_id = last_menu_message_id
        self.saved = []

    def get_user(self, _user_id):
        return {"last_menu_message_id": self.last_menu_message_id}

    def set_last_menu_message(self, user_id, message_id):
        self.last_menu_message_id = message_id
        self.saved.append((int(user_id), int(message_id)))


class _FakeBot:
    def __init__(self):
        self.deleted = []
        self.sent = []
        self.next_message_id = 100

    async def delete_message(self, chat_id, message_id):
        self.deleted.append((int(chat_id), int(message_id)))
        return True

    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append((int(chat_id), text, kwargs))
        return SimpleNamespace(message_id=self.next_message_id)


def test_private_tracking_never_tracks_channels_or_non_numeric_targets():
    svc._TRACKED_PRIVATE_MESSAGES.clear()
    svc._remember_private_message(12345, 10)
    svc._remember_private_message(-1004480289757, 11)
    svc._remember_private_message("@nexus_public", 12)

    assert svc._TRACKED_PRIVATE_MESSAGES == {12345: {10}}


def test_new_dashboard_removes_all_known_prior_private_text_and_keeps_current():
    svc._TRACKED_PRIVATE_MESSAGES.clear()
    svc._remember_private_message(12345, 10)
    svc._remember_private_message(12345, 11)

    main = SimpleNamespace(db=_FakeDB(last_menu_message_id=9))
    bot = _FakeBot()

    asyncio.run(svc._screen(main, bot, 12345, 12345, "dashboard", markup="kb"))

    assert set(bot.deleted) == {(12345, 9), (12345, 10), (12345, 11)}
    assert main.db.saved == [(12345, 100)]
    assert svc._TRACKED_PRIVATE_MESSAGES[12345] == {100}
    assert bot.sent[0][1] == "dashboard"


def test_processed_private_user_text_is_deleted_after_successful_handler():
    bot = _FakeBot()
    middleware = svc._ProcessedPrivateTextCleanupMiddleware()
    event = Message(
        message_id=77,
        date=datetime.now(timezone.utc),
        chat=Chat(id=12345, type=ChatType.PRIVATE),
        from_user=User(id=12345, is_bot=False, first_name="Test"),
        text="hello",
    )

    async def handler(_event, _data):
        return "handled"

    result = asyncio.run(middleware(handler, event, {"bot": bot}))

    assert result == "handled"
    assert bot.deleted == [(12345, 77)]


def test_processed_private_media_is_preserved():
    bot = _FakeBot()
    middleware = svc._ProcessedPrivateTextCleanupMiddleware()
    event = Message(
        message_id=78,
        date=datetime.now(timezone.utc),
        chat=Chat(id=12345, type=ChatType.PRIVATE),
        from_user=User(id=12345, is_bot=False, first_name="Test"),
    )

    async def handler(_event, _data):
        return "handled"

    result = asyncio.run(middleware(handler, event, {"bot": bot}))

    assert result == "handled"
    assert bot.deleted == []
