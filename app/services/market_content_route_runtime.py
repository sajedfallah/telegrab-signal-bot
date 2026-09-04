from __future__ import annotations

"""Route NEXUS market editorial to a dedicated Telegram destination/topic.

This override intentionally does not modify ``PUBLIC_CHANNEL_ID`` because that
setting is also referenced by legacy customer-gate code. Market/news delivery
can move to a forum topic without changing customer access behavior.

Preferred production variables:
  * PUBLIC_CONTENT_CHAT_ID
  * PUBLIC_CONTENT_TOPIC_ID

Legacy ``MARKET_CONTENT_CHANNEL_ID`` / ``MARKET_CONTENT_TOPIC_ID`` remain
supported as fallbacks for existing v0.6.5 deployments.
"""

import os
from typing import Any

from app.services import market_public_channel_runtime as market_public


def _parse_target(raw: str) -> int | str:
    value = str(raw or "").strip()
    if not value:
        raise ValueError("empty market content target")
    try:
        return int(value)
    except ValueError:
        return value


def _configured_topic_id() -> int | None:
    raw = (
        os.getenv("PUBLIC_CONTENT_TOPIC_ID", "").strip()
        or os.getenv("MARKET_CONTENT_TOPIC_ID", "").strip()
    )
    if not raw:
        return None
    try:
        topic_id = int(raw)
    except ValueError as exc:
        raise RuntimeError("PUBLIC_CONTENT_TOPIC_ID must be an integer") from exc
    if topic_id <= 0:
        raise RuntimeError("PUBLIC_CONTENT_TOPIC_ID must be greater than zero")
    return topic_id


def install(main: Any) -> None:
    """Override focused market editorial delivery for the configured forum route."""
    raw = (
        os.getenv("PUBLIC_CONTENT_CHAT_ID", "").strip()
        or os.getenv("MARKET_CONTENT_CHANNEL_ID", "").strip()
    )
    if not raw:
        main.log.info(
            "[NEXUS][MARKET_CONTENT_ROUTE] dedicated target not configured; fallback=%s",
            getattr(main.settings, "public_channel_id", None),
        )
        return

    target = _parse_target(raw)
    topic_id = _configured_topic_id()

    def _market_content_target(_main: Any) -> int | str:
        return target

    # The focused market runtime resolves its target at send time.
    market_public._public_target = _market_content_target

    # If a forum topic is configured, replace only the final Telegram delivery
    # helper. This preserves all existing editorial/news/ICT logic while making
    # every public market article land in the requested topic.
    if topic_id is not None and not getattr(market_public, "__nexus_public_topic_send_installed__", False):
        async def _send_public_to_topic(
            runtime_main: Any,
            bot: Any,
            text: str,
            *,
            reason: str,
            image_url: str = "",
        ) -> bool:
            physical_target = market_public._public_target(runtime_main)
            if image_url:
                try:
                    await bot.send_photo(
                        physical_target,
                        photo=image_url,
                        caption=text,
                        parse_mode="HTML",
                        message_thread_id=topic_id,
                    )
                    market_public.log.info(
                        "market public-topic delivery: reason=%s target=%s topic=%s status=sent_with_image",
                        reason,
                        physical_target,
                        topic_id,
                    )
                    return True
                except Exception as exc:
                    market_public.log.info(
                        "market public-topic image unavailable; falling back to text: reason=%s target=%s topic=%s error=%s",
                        reason,
                        physical_target,
                        topic_id,
                        exc,
                    )

            try:
                await bot.send_message(
                    physical_target,
                    text,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                    message_thread_id=topic_id,
                )
                market_public.log.info(
                    "market public-topic delivery: reason=%s target=%s topic=%s status=sent",
                    reason,
                    physical_target,
                    topic_id,
                )
                return True
            except Exception as exc:
                market_public.log.warning(
                    "market public-topic delivery failed: reason=%s target=%s topic=%s error=%s",
                    reason,
                    physical_target,
                    topic_id,
                    exc,
                )
                return False

        market_public._send_public = _send_public_to_topic
        market_public.__nexus_public_topic_send_installed__ = True

    source = "PUBLIC_CONTENT_CHAT_ID" if os.getenv("PUBLIC_CONTENT_CHAT_ID", "").strip() else "MARKET_CONTENT_CHANNEL_ID"
    main.log.info(
        "[NEXUS][MARKET_CONTENT_ROUTE][INSTALLED] target=%s topic=%s source=%s",
        target,
        topic_id or "none",
        source,
    )
