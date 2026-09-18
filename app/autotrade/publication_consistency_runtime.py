from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

from .. import db
from .broker_chart_fallback import ensure_broker_chart_asset

log = logging.getLogger("nexus.publication_consistency")

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


def _restore_canonical_web_visual(signal: Any) -> dict[str, Any] | None:
    """Rebuild WEB_ADMIN artwork from canonical signal + MT5 MarketFeed.

    Completed ChartAgent screenshots remain diagnostic evidence only. They are
    never re-staged into the Telegram publication slot because their chart
    objects may be stale or belong to a previous UI state.
    """
    signal_id = _signal_id(signal)
    if signal_id <= 0:
        return None
    if str(signal["issuer_type"] or "").strip().upper() != "WEB_ADMIN":
        return None

    result = ensure_broker_chart_asset(signal)
    if not result.get("ok"):
        return result

    with db.conn() as con:
        con.execute(
            "UPDATE signals SET publication_stage='CANONICAL_VISUAL_READY' "
            "WHERE id=? AND UPPER(COALESCE(publication_stage,''))!='PUBLISHED'",
            (signal_id,),
        )
    return result


def install_publication_consistency(app) -> None:
    """Serialize publication and pin Mini App signals to one canonical render.

    FREE/VIP publication for one signal is serialized under a per-signal lock.
    For WEB_ADMIN, the canonical broker renderer is rebuilt under that same
    lock before every incomplete publication attempt. This prevents concurrent
    recovery jobs, late ChartAgent screenshots, or stale staged assets from
    making the two channels receive different images.
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
            if ((isinstance(row, dict) and "issuer_type" in row) or (not isinstance(row, dict) and "issuer_type" in row.keys()))
            else ""
        ).strip().upper()
        if signal_id <= 0 or issuer_hint != "WEB_ADMIN":
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

            visual = _restore_canonical_web_visual(canonical)
            if visual is not None:
                if not visual.get("ok"):
                    reason = str(visual.get("reason") or "canonical visual unavailable")
                    try:
                        db.add_signal_event(
                            signal_id,
                            "PUBLICATION_CANONICAL_VISUAL_WAIT",
                            actor_type="BACKEND",
                            actor_id=canonical["created_by"],
                            account_number=str(canonical["issuer_account"] or ""),
                            correlation_id=str(canonical["code"] or ""),
                            result="FAILED",
                            reason=reason[:1000],
                            payload={"source": "MT5_MARKET_FEED_CANONICAL", "visual": visual},
                        )
                    except Exception:
                        log.exception("failed recording canonical visual wait signal_id=%s", signal_id)
                    return {
                        "free_message_id": None,
                        "vip_message_id": None,
                        "errors": [f"VISUAL_GATE: {reason}"],
                        "published": False,
                        "complete": False,
                        "visual_retryable": True,
                    }

                canonical = db.get_signal(signal_id) or canonical
                try:
                    db.add_signal_event(
                        signal_id,
                        "PUBLICATION_CANONICAL_VISUAL_RESTAGED",
                        actor_type="BACKEND",
                        actor_id=canonical["created_by"],
                        account_number=str(canonical["issuer_account"] or ""),
                        correlation_id=str(canonical["code"] or ""),
                        payload={
                            "file_path": visual.get("file_path"),
                            "source": "MT5_MARKET_FEED_CANONICAL",
                            "signal_visual_fingerprint": visual.get("fingerprint"),
                            "image_sha256": visual.get("image_sha256"),
                        },
                    )
                except Exception:
                    log.exception("failed recording canonical visual restage signal_id=%s", signal_id)

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
    app.state.nexus_publication_consistency_v37 = True
