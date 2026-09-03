from __future__ import annotations

import asyncio
import html
import logging
from collections.abc import Iterable

from . import pricing_service
from .. import db


log = logging.getLogger(__name__)
DEFAULT_REFRESH_SECONDS = 24 * 60 * 60
DEFAULT_FAILURE_ALERT_THRESHOLD = 3


async def refresh_and_maybe_alert(
    bot,
    admin_ids: Iterable[int],
    *,
    failure_alert_threshold: int = DEFAULT_FAILURE_ALERT_THRESHOLD,
) -> bool:
    """Refresh the automated USDT/IRR rate once and alert on a sustained outage.

    Alert deduplication is persisted in settings, so bot restarts do not spam
    administrators during the same failure streak. A successful refresh resets
    the streak and makes a future independent outage alertable again.
    """
    try:
        quote = await pricing_service.refresh_usdt_rial_rate()
        log.info("USDT/RIAL rate refreshed: rate=%s source=%s at=%s", quote.rate, quote.source, quote.fetched_at)
        return True
    except Exception as exc:
        health = pricing_service.rate_health()
        failures = int(health.get("consecutive_failures") or 0)
        threshold = max(1, int(failure_alert_threshold))
        already_alerted = db.get_setting("usdt_rial_failure_alerted", "0").strip() == "1"
        log.warning("USDT/RIAL refresh failed: failures=%s error=%s", failures, exc)

        if failures < threshold or already_alerted:
            return False

        text = (
            "⚠️ <b>NEXUS USDT rate provider alert</b>\n\n"
            f"Consecutive failures: <b>{failures}</b>\n"
            f"Primary: <code>{html.escape(str(health.get('primary_title') or health.get('primary') or '—'))}</code>\n"
            f"Secondary: <code>{html.escape(str(health.get('secondary_title') or health.get('secondary') or '—'))}</code>\n"
            f"Last valid rate: <code>{html.escape(str(health.get('last_rate') or '—'))}</code>\n"
            f"Last valid update: <code>{html.escape(str(health.get('last_rate_at') or '—'))}</code>\n"
            f"Error: <code>{html.escape(str(exc)[:700])}</code>"
        )
        delivered = False
        for admin_id in tuple(admin_ids):
            try:
                await bot.send_message(int(admin_id), text, parse_mode="HTML")
                delivered = True
            except Exception as notify_exc:
                log.warning("USDT/RIAL provider alert delivery failed for admin=%s: %s", admin_id, notify_exc)
        if delivered:
            db.set_setting("usdt_rial_failure_alerted", "1")
        return False


async def usdt_rate_worker(
    bot,
    admin_ids: Iterable[int],
    *,
    refresh_seconds: int = DEFAULT_REFRESH_SECONDS,
    failure_alert_threshold: int = DEFAULT_FAILURE_ALERT_THRESHOLD,
) -> None:
    """Refresh on startup and then once per day by default."""
    interval = max(3600, int(refresh_seconds))
    while True:
        try:
            await refresh_and_maybe_alert(
                bot,
                admin_ids,
                failure_alert_threshold=failure_alert_threshold,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("USDT/RIAL monitor loop failure")
        await asyncio.sleep(interval)
