from __future__ import annotations

import asyncio
from types import SimpleNamespace

from aiogram import Router

from app.services.open_access_runtime import install


class _DB:
    def __init__(self):
        self.upserts = []
        self.joined = []

    def upsert_user(self, user_id, username, first_name):
        self.upserts.append((user_id, username, first_name))

    def mark_public_joined(self, user_id, value):
        self.joined.append((user_id, value))


class _Log:
    def info(self, *args, **kwargs):
        pass

    def exception(self, *args, **kwargs):
        pass


def test_open_access_bypasses_deleted_public_channel_and_preserves_onboarding():
    db = _DB()
    calls = {"reward": 0, "home": 0}

    async def maybe_reward_referral(_bot, _user_id):
        calls["reward"] += 1

    async def show_main(_bot, _user_id, _chat_id):
        calls["home"] += 1

    main = SimpleNamespace(
        router=Router(),
        db=db,
        log=_Log(),
        maybe_reward_referral=maybe_reward_referral,
        show_main=show_main,
        get_lang=lambda _uid: "fa",
        tr=lambda _lang, fa, _en: fa,
    )

    install(main)

    user = SimpleNamespace(id=123, username="tester", first_name="Test")
    event = SimpleNamespace(from_user=user)

    assert asyncio.run(main.ensure_user(event, object())) is True
    assert asyncio.run(main.gated(event, object())) is True
    assert asyncio.run(main.check_public_member(object(), 123)) is True

    asyncio.run(main.show_gate(object(), 123, 123))

    assert db.upserts == [(123, "tester", "Test"), (123, "tester", "Test")]
    assert db.joined == [(123, True), (123, True)]
    assert calls["reward"] == 2
    assert calls["home"] == 1
    assert main._NEXUS_OPEN_ACCESS_INSTALLED is True


def test_install_is_idempotent():
    main = SimpleNamespace(
        router=Router(),
        db=_DB(),
        log=_Log(),
        maybe_reward_referral=lambda *_args: None,
        show_main=lambda *_args: None,
        get_lang=lambda _uid: "fa",
        tr=lambda _lang, fa, _en: fa,
    )
    install(main)
    handler_count = len(main.router.callback_query.handlers)
    install(main)
    assert len(main.router.callback_query.handlers) == handler_count
