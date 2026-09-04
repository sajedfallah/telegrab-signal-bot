from __future__ import annotations

"""Open-access runtime after retirement of the mandatory public channel.

The former Telegram join gate was a customer-onboarding requirement. The public
channel has now been retired, so bot access must no longer depend on
``get_chat_member`` or on ``PUBLIC_CHANNEL_ID``. This runtime keeps legacy paths
safe: stale membership callbacks and join-gate screens return users to the
current NEXUS access center instead of referencing the deleted channel.
"""

from typing import Any

from aiogram import F
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def _remove_named_handler(observer: Any, name: str) -> None:
    observer.handlers[:] = [
        handler
        for handler in observer.handlers
        if getattr(handler.callback, "__name__", "") != name
    ]


def install(main: Any) -> None:
    if getattr(main, "_NEXUS_OPEN_ACCESS_INSTALLED", False):
        return

    async def ensure_user_open(message_or_cb: Any, bot: Any) -> bool:
        """Create/update the user without checking membership in any channel."""
        user = message_or_cb.from_user
        main.db.upsert_user(user.id, user.username, user.first_name)

        # Keep the legacy DB onboarding flag satisfied for referral/account
        # compatibility. It no longer means Telegram-channel membership.
        try:
            main.db.mark_public_joined(user.id, True)
        except Exception:
            main.log.exception("could not mark open-access onboarding for %s", user.id)

        # Referrals used to be rewarded after the public membership check. With
        # the gate retired, successful bot onboarding is the equivalent event.
        try:
            await main.maybe_reward_referral(bot, int(user.id))
        except Exception:
            main.log.exception("open-access referral reward failed for %s", user.id)

        return True

    async def check_public_member_retired(_bot: Any, _user_id: int) -> bool:
        """Compatibility shim for old call sites; there is no membership gate."""
        return True

    async def gated_open(cb: Any, bot: Any) -> bool:
        await ensure_user_open(cb, bot)
        return True

    def retired_join_gate(lang: str) -> InlineKeyboardMarkup:
        """Never expose the deleted public-channel URL from a stale gate path."""
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=("🏠 ورود به NEXUS" if lang == "fa" else "🏠 Enter NEXUS"),
                        callback_data="main",
                    )
                ]
            ]
        )

    async def show_gate_retired(bot: Any, user_id: int, chat_id: int) -> None:
        # Any stale code path that still asks for the old gate is redirected to
        # the entitlement-aware NEXUS home screen.
        await main.show_main(bot, user_id, chat_id)

    # Replace module-level functions used dynamically by existing handlers.
    main.check_public_member = check_public_member_retired
    main.ensure_user = ensure_user_open
    main.gated = gated_open
    main.join_gate = retired_join_gate
    main.show_gate = show_gate_retired

    # Old Telegram messages may still have the historical "check membership"
    # callback. Remove the legacy handler so it cannot call the deleted channel.
    _remove_named_handler(main.router.callback_query, "check_public")

    async def retired_check_public(cb: Any, bot: Any) -> None:
        await ensure_user_open(cb, bot)
        lang = main.get_lang(cb.from_user.id)
        try:
            await cb.answer(
                main.tr(
                    lang,
                    "✅ دسترسی مستقیم NEXUS فعال است؛ عضویت اجباری حذف شده است.",
                    "✅ Direct NEXUS access is active; mandatory membership has been removed.",
                )
            )
        except Exception:
            pass
        await main.show_main(bot, cb.from_user.id, cb.message.chat.id)

    main.router.callback_query.register(retired_check_public, F.data == "check_public")
    main._NEXUS_OPEN_ACCESS_INSTALLED = True
    main.log.info(
        "[NEXUS][OPEN_ACCESS][INSTALLED] mandatory-public-membership=false legacy-gate=retired legacy-check-public=redirect"
    )
