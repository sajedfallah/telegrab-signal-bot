from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta


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
            "UPDATE autotrade_user_event_deliveries SET deleted_at=? WHERE event_key=? AND deleted_at IS NULL",
            (datetime.now(timezone.utc).isoformat(), str(event_key)),
        )


async def _cleanup_loop(core, bot) -> None:
    """Durably remove expired lifecycle messages, including after bot restarts."""
    while True:
        try:
            for row in _due(core, 100):
                try:
                    await bot.delete_message(int(row["telegram_id"]), int(row["telegram_message_id"]))
                except Exception:
                    # Message already deleted / chat no longer available: either way
                    # it should not be retried forever.
                    pass
                _mark_deleted(core, str(row["event_key"]))
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
