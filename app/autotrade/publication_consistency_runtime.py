from __future__ import annotations

import asyncio
from typing import Any, Callable

from .. import db

_publish_locks: dict[int, asyncio.Lock] = {}


def _signal_id(row: Any) -> int:
    try:
        return int(row["id"] or 0)
    except Exception:
        if isinstance(row, dict):
            return int(row.get("id") or 0)
        return 0


def _publication_complete(row: Any) -> bool:
    destination = str(row["destination"] or "BOTH").strip().upper()
    free_done = bool(row["free_message_id"])
    vip_done = bool(row["vip_message_id"])
    if destination == "FREE":
        return free_done
    if destination == "VIP":
        return vip_done
    return free_done and vip_done


def _lock_for(signal_id: int) -> asyncio.Lock:
    lock = _publish_locks.get(int(signal_id))
    if lock is None:
        lock = asyncio.Lock()
        _publish_locks[int(signal_id)] = lock
    return lock


def install_publication_consistency(app) -> None:
    """Serialize Mini App text publication across FREE/VIP destinations.

    V45 removes the chart-restage step entirely. The lock is retained because
    concurrent recovery/live-state tasks must still produce one idempotent text
    root per destination.
    """
    if getattr(app.state, "nexus_publication_consistency_v37", False):
        return

    from . import api as api_mod

    original_publish: Callable[..., Any] = api_mod._publish_mt5_admin_signal_async

    async def consistent_publish(
        row,
        chart_base64: str | None = None,
        *,
        allow_without_chart: bool = False,
    ) -> dict:
        signal_id = _signal_id(row)
        issuer_hint = str(
            (row.get("issuer_type") if isinstance(row, dict) else row["issuer_type"])
            if (
                (isinstance(row, dict) and "issuer_type" in row)
                or (not isinstance(row, dict) and "issuer_type" in row.keys())
            )
            else ""
        ).strip().upper()

        if signal_id <= 0 or issuer_hint != "WEB_ADMIN":
            return await original_publish(
                row,
                None,
                allow_without_chart=True,
            )

        async with _lock_for(signal_id):
            canonical = db.get_signal(signal_id) or row

            if _publication_complete(canonical):
                return {
                    "free_message_id": int(canonical["free_message_id"]) if canonical["free_message_id"] else None,
                    "vip_message_id": int(canonical["vip_message_id"]) if canonical["vip_message_id"] else None,
                    "errors": [],
                    "published": True,
                    "complete": True,
                    "consistency_short_circuit": True,
                    "publication_mode": "TEXT_ONLY",
                }

            result = await original_publish(
                canonical,
                None,
                allow_without_chart=True,
            )

            latest = db.get_signal(signal_id)
            if latest and _publication_complete(latest):
                with db.conn() as con:
                    con.execute(
                        "UPDATE signals SET publication_stage='PUBLISHED' WHERE id=?",
                        (signal_id,),
                    )
                if isinstance(result, dict):
                    result["free_message_id"] = int(latest["free_message_id"]) if latest["free_message_id"] else None
                    result["vip_message_id"] = int(latest["vip_message_id"]) if latest["vip_message_id"] else None
                    result["published"] = True
                    result["complete"] = True
                    result["publication_consistent"] = True
                    result["publication_mode"] = "TEXT_ONLY"

            return result

    api_mod._publish_mt5_admin_signal_async = consistent_publish
    app.state.nexus_publication_consistency_v37 = True
