from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta

from aiogram.exceptions import TelegramBadRequest


def _ensure_deleted_column(core) -> None:
    with core.db.conn() as con:
        cols = {str(r[1]) for r in con.execute("PRAGMA table_info(autotrade_user_event_deliveries)").fetchall()}
        if "deleted_at" not in cols:
            con.execute("ALTER TABLE autotrade_user_event_deliveries ADD COLUMN deleted_at TEXT")
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_autotrade_user_event_cleanup "
            "ON autotrade_user_event_deliveries(sent_at,deleted_at)"
        )


def _due(core, limit: int = 100):
    ttl = max(3, int(core.settings.autotrade_notification_ttl_seconds))
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=ttl)).isoformat()
    with core.db.conn() as con:
        return list(
            con.execute(
                "SELECT event_key,telegram_id,telegram_message_id FROM autotrade_user_event_deliveries "
                "WHERE sent_at IS NOT NULL AND deleted_at IS NULL "
                "AND telegram_message_id IS NOT NULL AND telegram_message_id>0 AND sent_at<=? "
                "ORDER BY sent_at LIMIT ?",
                (cutoff, max(1, min(int(limit), 500))),
            ).fetchall()
        )


def _mark_deleted(core, event_key: str) -> None:
    with core.db.conn() as con:
        con.execute(
            "UPDATE autotrade_user_event_deliveries "
            "SET deleted_at=?, error_text=NULL "
            "WHERE event_key=? AND deleted_at IS NULL",
            (datetime.now(timezone.utc).isoformat(), str(event_key)),
        )


def _record_cleanup_error(core, event_key: str, error: Exception) -> None:
    try:
        with core.db.conn() as con:
            con.execute(
                "UPDATE autotrade_user_event_deliveries SET error_text=? "
                "WHERE event_key=? AND deleted_at IS NULL",
                (f"cleanup: {str(error)[:900]}", str(event_key)),
            )
    except Exception:
        core.log.exception("could not persist AutoTrade cleanup error event=%s", event_key)


def _already_gone(exc: Exception) -> bool:
    text = str(exc or "").lower()
    return any(
        marker in text
        for marker in (
            "message to delete not found",
            "message can't be deleted",
            "message cannot be deleted",
        )
    )


async def _delete_transient_with_retry_fallback(core, bot, chat_id: int, message_id: int, delay: int):
    """Best-effort immediate delete; durable cleanup owns retries on failure."""
    await asyncio.sleep(max(3, int(delay)))
    try:
        await bot.delete_message(int(chat_id), int(message_id))
    except TelegramBadRequest as exc:
        if not _already_gone(exc):
            core.log.warning(
                "AutoTrade immediate notification delete failed; durable cleanup will retry: chat=%s message=%s error=%s",
                chat_id,
                message_id,
                exc,
            )
    except Exception as exc:
        core.log.warning(
            "AutoTrade immediate notification delete failed; durable cleanup will retry: chat=%s message=%s error=%s",
            chat_id,
            message_id,
            exc,
        )


async def _cleanup_loop(core, bot) -> None:
    """Durably remove expired lifecycle messages, including after bot restarts."""
    while True:
        try:
            for row in _due(core, 100):
                event_key = str(row["event_key"])
                chat_id = int(row["telegram_id"])
                message_id = int(row["telegram_message_id"])
                try:
                    await bot.delete_message(chat_id, message_id)
                except TelegramBadRequest as exc:
                    if _already_gone(exc):
                        _mark_deleted(core, event_key)
                    else:
                        _record_cleanup_error(core, event_key, exc)
                        core.log.warning(
                            "AutoTrade durable delete rejected; will retry: event=%s chat=%s message=%s error=%s",
                            event_key,
                            chat_id,
                            message_id,
                            exc,
                        )
                        await asyncio.sleep(0.10)
                        continue
                except Exception as exc:
                    # Network/Telegram outages must not turn into a false
                    # "deleted" ledger state. Keep the row due for retry.
                    _record_cleanup_error(core, event_key, exc)
                    core.log.warning(
                        "AutoTrade durable delete failed; will retry: event=%s chat=%s message=%s error=%s",
                        event_key,
                        chat_id,
                        message_id,
                        exc,
                    )
                    await asyncio.sleep(0.10)
                    continue
                else:
                    _mark_deleted(core, event_key)
                await asyncio.sleep(0.02)
        except Exception:
            core.log.exception("AutoTrade durable notification cleanup error")
        await asyncio.sleep(1.0)


def install_autotrade_durable_cleanup(core) -> None:
    """Run durable cleanup alongside the enhanced AutoTrade notification worker."""
    if getattr(core, "_NEXUS_AUTOTRADE_CLEANUP_INSTALLED", False):
        return
    _ensure_deleted_column(core)
    original_worker = core.autotrade_notification_worker

    async def robust_transient_delete(bot, chat_id: int, message_id: int, delay: int):
        await _delete_transient_with_retry_fallback(core, bot, chat_id, message_id, delay)

    # The enhanced lifecycle sender resolves this attribute at send time.
    # Replacing the legacy silent-deletion helper gives us observability while
    # the durable ledger remains the authoritative retry mechanism.
    core._delete_transient_notification = robust_transient_delete

    async def worker_with_cleanup(bot):
        notify_task = asyncio.create_task(original_worker(bot), name="autotrade-notification-queue")
        cleanup_task = asyncio.create_task(_cleanup_loop(core, bot), name="autotrade-notification-cleanup")
        try:
            await asyncio.gather(notify_task, cleanup_task)
        finally:
            for task in (notify_task, cleanup_task):
                if not task.done():
                    task.cancel()
            await asyncio.gather(notify_task, cleanup_task, return_exceptions=True)

    core.autotrade_notification_worker = worker_with_cleanup
    core._NEXUS_AUTOTRADE_CLEANUP_INSTALLED = True
