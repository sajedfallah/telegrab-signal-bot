from __future__ import annotations

import asyncio
import hashlib
import logging
from pathlib import Path
from typing import Any

from .. import db
from .chart_delivery_guard import _validate_png

log = logging.getLogger("nexus.telegram_anchor")

_MISSING_ANCHOR_MARKERS = (
    "message_id_invalid",
    "message to edit not found",
    "message to copy not found",
    "message to forward not found",
)
_anchor_locks: dict[tuple[int, str], asyncio.Lock] = {}


def _required_channels(destination: str) -> list[str]:
    value = str(destination or "BOTH").strip().upper()
    if value == "FREE":
        return ["FREE"]
    if value == "VIP":
        return ["VIP"]
    return ["FREE", "VIP"]


def _message_id(row: Any, channel: str) -> int | None:
    key = "free_message_id" if channel == "FREE" else "vip_message_id"
    value = row[key]
    return int(value) if value else None


def _publication_complete(row: Any) -> bool:
    return all(_message_id(row, channel) is not None for channel in _required_channels(str(row["destination"] or "BOTH")))


def _missing_anchor_channels(errors: list[str] | tuple[str, ...] | None) -> set[str]:
    channels: set[str] = set()
    for raw in errors or []:
        text = str(raw or "")
        lowered = text.lower()
        if not any(marker in lowered for marker in _MISSING_ANCHOR_MARKERS):
            continue
        prefix = text.split(":", 1)[0].strip().upper()
        if prefix in {"FREE", "VIP"}:
            channels.add(prefix)
    return channels


def _asset_bytes(signal_id: int) -> tuple[bytes, str | None, str]:
    asset_path = db.get_mt5_signal_publication_asset(int(signal_id))
    if not asset_path:
        return b"", None, "MISSING"
    path = Path(str(asset_path))
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return b"", str(path), f"READ_FAILED:{exc}"
    ok, reason = _validate_png(raw)
    return (raw if ok else b""), str(path), reason


def _cas_replace_anchor(signal_id: int, channel: str, old_id: int, new_id: int) -> bool:
    if channel == "FREE":
        root_col = "free_message_id"
        last_col = "free_last_message_id"
    elif channel == "VIP":
        root_col = "vip_message_id"
        last_col = "vip_last_message_id"
    else:
        raise ValueError("invalid Telegram channel")

    with db.conn() as con:
        cur = con.execute(
            f"UPDATE signals SET {root_col}=?,{last_col}=? WHERE id=? AND {root_col}=?",
            (int(new_id), int(new_id), int(signal_id), int(old_id)),
        )
    return cur.rowcount == 1


def _mark_published_if_complete(signal_id: int) -> bool:
    row = db.get_signal(int(signal_id))
    if not row or not _publication_complete(row):
        return False
    with db.conn() as con:
        con.execute(
            "UPDATE signals SET status='ACTIVE',publication_stage='PUBLISHED' WHERE id=?",
            (int(signal_id),),
        )
    job = db.get_signal_chart_capture_job(int(signal_id))
    if job:
        try:
            db.mark_chart_capture_job_completed(int(job["id"]))
        except ValueError:
            pass
    return True


def _reconcile_publication_race(signal_id: int, result: dict) -> dict:
    canonical = db.get_signal(int(signal_id))
    if not canonical or not _publication_complete(canonical):
        return result

    stage = str(canonical["publication_stage"] or "").upper()
    if stage == "PUBLISH_FAILED":
        with db.conn() as con:
            cur = con.execute(
                "UPDATE signals SET status='ACTIVE',publication_stage='PUBLISHED' "
                "WHERE id=? AND publication_stage='PUBLISH_FAILED'",
                (int(signal_id),),
            )
        if cur.rowcount:
            db.add_signal_event(
                int(signal_id),
                "PUBLICATION_RACE_RECONCILED",
                actor_type="BACKEND",
                actor_id=canonical["created_by"],
                account_number=str(canonical["issuer_account"] or ""),
                correlation_id=str(canonical["code"]),
                reason="a later duplicate publication attempt observed an already-published destination",
                payload={
                    "free_message_id": canonical["free_message_id"],
                    "vip_message_id": canonical["vip_message_id"],
                    "previous_stage": stage,
                },
            )

    result["free_message_id"] = int(canonical["free_message_id"]) if canonical["free_message_id"] else None
    result["vip_message_id"] = int(canonical["vip_message_id"]) if canonical["vip_message_id"] else None
    result["published"] = True
    result["complete"] = True
    return result


async def _replace_missing_anchor(signal: Any, channel: str, old_id: int, raw: bytes) -> tuple[bool, int | None, str | None]:
    signal_id = int(signal["id"])
    key = (signal_id, channel)
    lock = _anchor_locks.setdefault(key, asyncio.Lock())

    async with lock:
        canonical = db.get_signal(signal_id)
        if not canonical:
            return False, None, "signal disappeared before anchor replacement"
        current_id = _message_id(canonical, channel)
        if current_id != int(old_id):
            return True, current_id, None

        try:
            from aiogram import Bot
            from aiogram.enums import ParseMode
            from aiogram.types import BufferedInputFile
            from ..config import settings
            from ..main import _signal_caption
            from ..signals.card_generator import build_publication_signal_image, publication_card_payload

            card_signal = publication_card_payload(canonical, db.get_signal_targets(signal_id))
            chart_frame = await asyncio.to_thread(build_publication_signal_image, raw, card_signal)
            frame_ok, frame_reason = _validate_png(chart_frame, max_bytes=10_000_000)
            if not frame_ok:
                return False, None, f"rendered replacement flash-card invalid: {frame_reason}"

            caption = _signal_caption(canonical, status="ACTIVE")
            target = settings.free_channel_target if channel == "FREE" else settings.vip_channel_id

            async with Bot(settings.bot_token) as bot:
                msg = await bot.send_photo(
                    target,
                    BufferedInputFile(chart_frame, filename=f"{canonical['code']}_chart.png"),
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                )
                new_id = int(msg.message_id)

                if not _cas_replace_anchor(signal_id, channel, int(old_id), new_id):
                    latest = db.get_signal(signal_id)
                    adopted_id = _message_id(latest, channel) if latest else None
                    try:
                        await bot.delete_message(chat_id=target, message_id=new_id)
                    except Exception:
                        log.exception("failed deleting duplicate replacement signal=%s channel=%s message=%s", canonical["code"], channel, new_id)
                    if adopted_id and adopted_id != int(old_id):
                        return True, adopted_id, None
                    return False, None, "anchor compare-and-swap lost without a replacement anchor"

            db.add_signal_event(
                signal_id,
                "TELEGRAM_ANCHOR_REPLACED",
                actor_type="BACKEND",
                actor_id=canonical["created_by"],
                account_number=str(canonical["issuer_account"] or ""),
                correlation_id=str(canonical["code"]),
                reason="Telegram confirmed the stored publication anchor no longer exists",
                payload={
                    "channel": channel,
                    "old_message_id": int(old_id),
                    "new_message_id": int(new_id),
                    "asset_sha256": hashlib.sha256(raw).hexdigest(),
                },
            )
            return True, new_id, None
        except Exception as exc:
            log.exception("Telegram anchor replacement failed signal=%s channel=%s", canonical["code"], channel)
            return False, None, str(exc)


def install_telegram_anchor_guard(app) -> None:
    """Self-heal deleted/stale Telegram roots without touching trade execution.

    The guard is deliberately narrow: it only sends a replacement when the
    existing WEB_ADMIN repair attempt receives an explicit Telegram missing-
    message error and a validated chart asset is already staged. Normal retries
    remain idempotent and keep the existing root message ids.
    """
    if getattr(app.state, "nexus_telegram_anchor_guard_v27", False):
        return

    from . import api as api_mod

    original_publish = api_mod._publish_mt5_admin_signal_async

    async def anchor_guarded_publish(row, chart_base64: str | None = None, *, allow_without_chart: bool = False) -> dict:
        result = await original_publish(row, chart_base64, allow_without_chart=allow_without_chart)
        if not isinstance(result, dict):
            return result

        issuer_hint = (
            str(row.get("issuer_type") or "").upper()
            if isinstance(row, dict)
            else str(row["issuer_type"] or "").upper() if "issuer_type" in row.keys() else ""
        )
        # Anchor repair is WEB_ADMIN-only. An MT5_ADMIN execution-gate rejection
        # must return without any later DB read.
        if issuer_hint != "WEB_ADMIN":
            return result

        canonical = db.get_signal(int(row["id"])) or row

        stale_channels = _missing_anchor_channels(result.get("errors"))
        required = set(_required_channels(str(canonical["destination"] or "BOTH")))
        stale_channels &= required

        if stale_channels:
            raw, asset_path, asset_state = _asset_bytes(int(canonical["id"]))
            if not raw:
                result["anchor_guard_state"] = f"STALE_ANCHOR_WITHOUT_VALID_ASSET:{asset_state}"
                result["repair_pending"] = True
                return result

            replaced: list[str] = []
            replacement_errors: list[str] = []
            new_ids: dict[str, int] = {}

            for channel in sorted(stale_channels):
                fresh = db.get_signal(int(canonical["id"])) or canonical
                old_id = _message_id(fresh, channel)
                if old_id is None:
                    continue
                ok, new_id, error = await _replace_missing_anchor(fresh, channel, old_id, raw)
                if ok:
                    replaced.append(channel)
                    if new_id is not None:
                        new_ids[channel] = int(new_id)
                elif error:
                    replacement_errors.append(f"{channel}: {error}")

            if replaced:
                db.add_signal_event(
                    int(canonical["id"]),
                    "CHART_REPAIR_APPLIED",
                    actor_type="BACKEND",
                    actor_id=canonical["created_by"],
                    account_number=str(canonical["issuer_account"] or ""),
                    correlation_id=str(canonical["code"]),
                    payload={
                        "channels": replaced,
                        "anchor_replaced": True,
                        "new_message_ids": new_ids,
                        "asset_state": asset_state,
                        "asset_path": asset_path,
                    },
                )

            latest = db.get_signal(int(canonical["id"])) or canonical
            complete = (
                _publication_complete(latest)
                and not replacement_errors
                and stale_channels.issubset(set(replaced))
            )
            if complete:
                _mark_published_if_complete(int(canonical["id"]))
                db.clear_mt5_signal_publication_asset(int(canonical["id"]))

            filtered_errors = []
            for error in result.get("errors") or []:
                prefix = str(error).split(":", 1)[0].strip().upper()
                if prefix in replaced and prefix in stale_channels:
                    continue
                filtered_errors.append(error)
            filtered_errors.extend(replacement_errors)

            latest = db.get_signal(int(canonical["id"])) or latest
            result.update({
                "free_message_id": _message_id(latest, "FREE"),
                "vip_message_id": _message_id(latest, "VIP"),
                "errors": filtered_errors,
                "published": bool(_message_id(latest, "FREE") or _message_id(latest, "VIP")),
                "complete": complete,
                "repaired_channels": sorted(set((result.get("repaired_channels") or []) + replaced)),
                "anchor_replaced_channels": replaced,
                "repair_pending": not complete,
            })
            # A stale anchor is authoritative negative evidence. Never let the
            # generic publication-race reconciler mark it PUBLISHED unless the
            # replacement itself succeeded.
            return result

        return _reconcile_publication_race(int(canonical["id"]), result)

    api_mod._publish_mt5_admin_signal_async = anchor_guarded_publish
    app.state.nexus_telegram_anchor_guard_v27 = True
