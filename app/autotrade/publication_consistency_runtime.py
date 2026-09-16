from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Callable

from .. import db

log = logging.getLogger("nexus.publication_consistency")

_publish_locks: dict[int, asyncio.Lock] = {}
_READY_CHART = {"UPLOADED", "COMPLETED"}


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


def _real_chart_path(signal_id: int) -> str | None:
    job = db.get_signal_chart_capture_job(int(signal_id))
    if not job:
        return None
    if str(job["status"] or "").strip().upper() not in _READY_CHART:
        return None
    path_text = str(job["image_path"] or "").strip()
    if not path_text:
        return None
    path = Path(path_text)
    try:
        if not path.is_file() or path.stat().st_size < 512:
            return None
        with path.open("rb") as handle:
            magic = handle.read(8)
    except OSError:
        return None
    if not magic.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    return str(path)


def _lock_for(signal_id: int) -> asyncio.Lock:
    lock = _publish_locks.get(int(signal_id))
    if lock is None:
        lock = asyncio.Lock()
        _publish_locks[int(signal_id)] = lock
    return lock


def _restore_real_chart(signal: Any) -> str | None:
    signal_id = _signal_id(signal)
    if signal_id <= 0:
        return None
    if str(signal["issuer_type"] or "").strip().upper() != "WEB_ADMIN":
        return None

    path = _real_chart_path(signal_id)
    if not path:
        return None

    current_asset = db.get_mt5_signal_publication_asset(signal_id)
    if str(current_asset or "") != path:
        db.save_mt5_signal_publication_asset(signal_id, path)

    # V28 recognizes CHART_RECEIVED as the authoritative ChartAgent source.
    # FLASHCARD_READY/PUBLISH_FAILED are publication-progress states and must not
    # demote an already-uploaded real MT5 screenshot to MarketFeed fallback.
    with db.conn() as con:
        con.execute(
            "UPDATE signals SET publication_stage='CHART_RECEIVED' "
            "WHERE id=? AND UPPER(COALESCE(publication_stage,''))!='PUBLISHED'",
            (signal_id,),
        )

    return path


def install_publication_consistency(app) -> None:
    """Serialize BOTH-channel publication and pin it to one real MT5 image.

    Multiple background recovery tasks can race while Telegram publication is in
    progress. The base publisher changes publication_stage to FLASHCARD_READY
    before both channels have been sent, which previously allowed a concurrent
    V28 invocation to treat the real ChartAgent image as non-authoritative,
    generate a MarketFeed fallback, and send FREE/VIP with different images.

    This outermost wrapper serializes publication per signal, restores the real
    ChartAgent asset from the completed capture job before each attempt, and
    short-circuits duplicate attempts after all requested channels are present.
    """
    if getattr(app.state, "nexus_publication_consistency_v34", False):
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
        if signal_id <= 0:
            return await original_publish(
                row,
                chart_base64,
                allow_without_chart=allow_without_chart,
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
                }

            real_chart = _restore_real_chart(canonical)
            if real_chart:
                canonical = db.get_signal(signal_id) or canonical
                try:
                    db.add_signal_event(
                        signal_id,
                        "PUBLICATION_CANONICAL_MT5_RESTAGED",
                        actor_type="BACKEND",
                        actor_id=canonical["created_by"],
                        account_number=str(canonical["issuer_account"] or ""),
                        correlation_id=str(canonical["code"] or ""),
                        payload={"file_path": real_chart, "source": "MT5_CHART_AGENT"},
                    )
                except Exception:
                    log.exception("failed recording canonical restage signal_id=%s", signal_id)

            result = await original_publish(
                canonical,
                chart_base64,
                allow_without_chart=allow_without_chart,
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

            return result

    api_mod._publish_mt5_admin_signal_async = consistent_publish
    app.state.nexus_publication_consistency_v34 = True
