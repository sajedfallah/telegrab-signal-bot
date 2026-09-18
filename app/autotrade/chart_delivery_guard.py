from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import hmac
import logging
import time
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Callable

from fastapi import Header, HTTPException, Query
from fastapi.routing import APIRoute

from .. import db

log = logging.getLogger("nexus.chart_delivery")

_ACCEPTED = {"EXECUTED", "PENDING", "ACTIVATED"}
_TERMINAL = {"FAILED", "EXPIRED"}
_MAX_REPAIR_CYCLES = 2
_ALERT_WINDOW_MINUTES = 10
_ALERT_THROTTLE_SECONDS = 600
_alert_sent_at: dict[str, float] = {}


def _route(app, path: str, method: str) -> APIRoute:
    method = method.upper()
    for candidate in app.router.routes:
        if isinstance(candidate, APIRoute) and candidate.path == path and method in candidate.methods:
            return candidate
    raise RuntimeError(f"NEXUS chart delivery route not found: {method} {path}")


def _replace_route(app, path: str, method: str, func: Callable[..., Any]) -> Callable[..., Any]:
    route = _route(app, path, method)
    original = route.dependant.call
    route.endpoint = func
    route.dependant.call = func
    return original


def _validate_png(raw: bytes, *, max_bytes: int = 5_000_000) -> tuple[bool, str]:
    if not raw:
        return False, "EMPTY"
    if len(raw) > max_bytes:
        return False, "TOO_LARGE"
    if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return False, "BAD_SIGNATURE"
    try:
        from PIL import Image, UnidentifiedImageError
        with Image.open(BytesIO(raw)) as image:
            if image.format != "PNG":
                return False, "BAD_FORMAT"
            width, height = image.size
            image.verify()
            if width < 160 or height < 120:
                return False, "TOO_SMALL"
            if width * height > 20_000_000:
                return False, "UNSAFE_DIMENSIONS"
    except (UnidentifiedImageError, OSError, ValueError):
        return False, "DECODE_FAILED"
    return True, "OK"


def _read_publication_asset(signal_id: int) -> tuple[bytes, str | None, str]:
    asset_path = db.get_mt5_signal_publication_asset(int(signal_id))
    if not asset_path:
        return b"", None, "MISSING"
    path = Path(str(asset_path))
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return b"", str(path), f"READ_FAILED:{exc}"
    valid, reason = _validate_png(raw)
    return (raw if valid else b""), str(path), reason


def _event_count(signal_id: int, event_type: str) -> int:
    with db.conn() as con:
        row = con.execute(
            "SELECT COUNT(*) AS c FROM signal_events_v060 WHERE signal_id=? AND event_type=?",
            (int(signal_id), str(event_type).upper()),
        ).fetchone()
    return int(row["c"] if row else 0)


def _accepted_receipt(signal_id: int) -> bool:
    with db.conn() as con:
        row = con.execute(
            """SELECT status FROM autotrade_signal_receipts
               WHERE signal_id=? AND platform='MT5'
               ORDER BY COALESCE(executed_at,first_seen_at) DESC LIMIT 1""",
            (int(signal_id),),
        ).fetchone()
    return bool(row and str(row["status"] or "").strip().upper() in _ACCEPTED)


def _terminal_repair_candidates(account: str) -> list[Any]:
    with db.conn() as con:
        return list(con.execute(
            """SELECT s.id AS signal_id,s.code,s.destination,s.free_message_id,s.vip_message_id,
                      s.publication_stage,j.id AS job_id,j.status AS job_status,j.error_text,j.attempt_count
               FROM signals s
               JOIN signal_chart_capture_jobs j ON j.signal_id=s.id
               WHERE s.issuer_type='WEB_ADMIN' AND s.issuer_account=?
                 AND j.id=(SELECT MAX(j2.id) FROM signal_chart_capture_jobs j2 WHERE j2.signal_id=s.id)
                 AND UPPER(COALESCE(j.status,'')) IN ('FAILED','EXPIRED')
                 AND EXISTS (
                   SELECT 1 FROM autotrade_signal_receipts r
                   WHERE r.signal_id=s.id AND r.platform='MT5'
                     AND UPPER(COALESCE(r.status,'')) IN ('EXECUTED','PENDING','ACTIVATED')
                 )
               ORDER BY s.id DESC LIMIT 40""",
            (str(account),),
        ).fetchall())


def _queue_terminal_repairs(account: str) -> list[int]:
    repaired: list[int] = []
    for item in _terminal_repair_candidates(account):
        signal_id = int(item["signal_id"])
        cycles = _event_count(signal_id, "CHART_REPAIR_QUEUED")
        if cycles >= _MAX_REPAIR_CYCLES:
            continue
        try:
            job = db.retry_chart_capture_job(signal_id)
        except ValueError:
            continue
        db.add_signal_event(
            signal_id,
            "CHART_REPAIR_QUEUED",
            actor_type="BACKEND",
            account_number=str(account),
            correlation_id=str(item["code"]),
            reason=str(item["error_text"] or "terminal chart capture failure"),
            payload={
                "job_id": int(job["id"]),
                "repair_cycle": cycles + 1,
                "max_repair_cycles": _MAX_REPAIR_CYCLES,
                "fallback_already_published": bool(item["free_message_id"] or item["vip_message_id"]),
            },
        )
        with db.conn() as con:
            con.execute(
                "UPDATE signals SET publication_stage=CASE WHEN COALESCE(free_message_id,0)>0 OR COALESCE(vip_message_id,0)>0 "
                "THEN 'PUBLISHED_REPAIR_PENDING' ELSE 'WAITING_FOR_CHART' END WHERE id=?",
                (signal_id,),
            )
        repaired.append(signal_id)
    return repaired


def chart_delivery_health(account: str, *, minutes: int = 30) -> dict[str, Any]:
    minutes = max(5, min(int(minutes), 1440))
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
    with db.conn() as con:
        status_rows = con.execute(
            """SELECT UPPER(COALESCE(j.status,'UNKNOWN')) AS status,COUNT(*) AS c
               FROM signal_chart_capture_jobs j
               JOIN signals s ON s.id=j.signal_id
               WHERE s.issuer_account=? AND j.updated_at>=?
               GROUP BY UPPER(COALESCE(j.status,'UNKNOWN'))""",
            (str(account), cutoff),
        ).fetchall()
        recent = con.execute(
            """SELECT j.id AS job_id,j.signal_id,s.code,j.status,j.attempt_count,j.error_text,j.updated_at,
                      s.publication_stage,s.free_message_id,s.vip_message_id
               FROM signal_chart_capture_jobs j
               JOIN signals s ON s.id=j.signal_id
               WHERE s.issuer_account=?
               ORDER BY j.updated_at DESC,j.id DESC LIMIT 12""",
            (str(account),),
        ).fetchall()
        fallback_row = con.execute(
            """SELECT COUNT(*) AS c FROM signal_events_v060 e
               JOIN signals s ON s.id=e.signal_id
               WHERE s.issuer_account=? AND e.event_type='PUBLICATION_FALLBACK_QUEUED' AND e.event_time>=?""",
            (str(account), cutoff),
        ).fetchone()
        repair_row = con.execute(
            """SELECT COUNT(*) AS c FROM signal_events_v060 e
               JOIN signals s ON s.id=e.signal_id
               WHERE s.issuer_account=? AND e.event_type='CHART_REPAIR_APPLIED' AND e.event_time>=?""",
            (str(account), cutoff),
        ).fetchone()
    counts = {str(row["status"]): int(row["c"]) for row in status_rows}
    failures = int(counts.get("FAILED", 0)) + int(counts.get("EXPIRED", 0))
    fallback_count = int(fallback_row["c"] if fallback_row else 0)
    repair_count = int(repair_row["c"] if repair_row else 0)
    exhausted = [
        dict(item) for item in recent
        if str(item["status"] or "").upper() in _TERMINAL
        and _event_count(int(item["signal_id"]), "CHART_REPAIR_QUEUED") >= _MAX_REPAIR_CYCLES
    ]
    severity = "CRITICAL" if exhausted else "WARN" if failures >= 3 or fallback_count >= 2 else "OK"
    return {
        "ok": severity == "OK",
        "severity": severity,
        "window_minutes": minutes,
        "counts": counts,
        "fallback_publications": fallback_count,
        "repairs_applied": repair_count,
        "repair_exhausted": exhausted[:5],
        "recent_jobs": [dict(row) for row in recent],
    }


async def _send_admin_alert(account: str, health: dict[str, Any]) -> None:
    try:
        from aiogram import Bot
        from ..config import settings
        exhausted = health.get("repair_exhausted") or []
        detail = ""
        if exhausted:
            first = exhausted[0]
            detail = f"\nSignal: {first.get('code')}\nError: {str(first.get('error_text') or '')[:350]}"
        text = (
            "🚨 NEXUS CHART DELIVERY ALERT\n\n"
            f"MT5: {account}\n"
            f"Severity: {health.get('severity')}\n"
            f"Failed/Expired: {int(health.get('counts',{}).get('FAILED',0))+int(health.get('counts',{}).get('EXPIRED',0))}\n"
            f"Fallback: {health.get('fallback_publications',0)}\n"
            f"Repaired: {health.get('repairs_applied',0)}"
            f"{detail}"
        )
        async with Bot(settings.bot_token) as bot:
            for admin_id in settings.admin_ids:
                try:
                    await bot.send_message(int(admin_id), text)
                except Exception:
                    log.exception("chart delivery alert send failed admin_id=%s", admin_id)
    except Exception:
        log.exception("chart delivery alert initialization failed")


def _alert_due(account: str, health: dict[str, Any]) -> bool:
    if str(health.get("severity")) not in {"WARN", "CRITICAL"}:
        return False
    now = time.monotonic()
    last = _alert_sent_at.get(str(account), 0.0)
    if now - last < _ALERT_THROTTLE_SECONDS:
        return False
    _alert_sent_at[str(account)] = now
    return True


def install_chart_delivery_guard(app) -> None:
    """Install additive reliability guards for WEB_ADMIN chart publication.

    This layer intentionally leaves trading/execution logic untouched. It:
    * isolates ChartAgent poll/result/fail rate-limit buckets;
    * retries terminal capture jobs with a bounded repair budget;
    * replaces an already-published fallback image when a late MT5 chart arrives;
    * exposes authenticated health telemetry and throttled admin alerts.
    """
    if getattr(app.state, "nexus_chart_delivery_guard_v24", False):
        return

    from . import api as api_mod

    # Mirror the production emergency fix in source control. Poll uses limit=60,
    # result/fail use limit=30; they must never consume the same minute bucket.
    api_mod._chart_rate_windows.clear()

    def isolated_chart_rate_limit(account: str, limit: int = 60) -> None:
        now = time.monotonic()
        bucket = f"{str(account).strip()}:{int(limit)}"
        recent = [stamp for stamp in api_mod._chart_rate_windows.get(bucket, []) if now - stamp < 60]
        if len(recent) >= int(limit):
            raise HTTPException(status_code=429, detail="chart capture rate limit exceeded")
        recent.append(now)
        api_mod._chart_rate_windows[bucket] = recent

    api_mod._chart_rate_limit = isolated_chart_rate_limit

    original_publish = api_mod._publish_mt5_admin_signal_async

    async def durable_publish(row, chart_base64: str | None = None, *, allow_without_chart: bool = False) -> dict:
        issuer_hint = (
            str(row.get("issuer_type") or "").upper()
            if isinstance(row, dict)
            else str(row["issuer_type"] or "").upper() if "issuer_type" in row.keys() else ""
        )
        # This repair layer is WEB_ADMIN-only. Do not perform any DB lookup
        # ahead of the MT5_ADMIN publisher's execution-receipt gate.
        if issuer_hint != "WEB_ADMIN":
            return await original_publish(row, chart_base64, allow_without_chart=allow_without_chart)

        canonical = db.get_signal(int(row["id"])) or row
        issuer_type = str(canonical["issuer_type"] or "").upper()

        raw, asset_path, asset_state = _read_publication_asset(int(canonical["id"]))
        existing = {
            "FREE": int(canonical["free_message_id"]) if canonical["free_message_id"] else None,
            "VIP": int(canonical["vip_message_id"]) if canonical["vip_message_id"] else None,
        }
        destination = str(canonical["destination"] or "BOTH").upper()
        required_channels = ["FREE"] if destination == "FREE" else ["VIP"] if destination == "VIP" else ["FREE", "VIP"]
        repair_channels = [channel for channel in required_channels if existing[channel] is not None]

        # First publication or fallback publication keeps the canonical publisher.
        if not raw or not repair_channels:
            return await original_publish(canonical, chart_base64, allow_without_chart=allow_without_chart)

        try:
            from aiogram import Bot
            from aiogram.enums import ParseMode
            from aiogram.types import BufferedInputFile, InputMediaPhoto
            from ..config import settings
            from ..main import _signal_caption
            from ..signals.card_generator import build_publication_signal_image, publication_card_payload

            card_signal = publication_card_payload(canonical, db.get_signal_targets(int(canonical["id"])))
            chart_frame = await asyncio.to_thread(build_publication_signal_image, raw, card_signal)
            frame_ok, frame_reason = _validate_png(chart_frame, max_bytes=10_000_000)
            if not frame_ok:
                raise ValueError(f"rendered flash-card validation failed: {frame_reason}")
            caption = _signal_caption(canonical, status="ACTIVE")
            targets = {"FREE": settings.free_channel_target, "VIP": settings.vip_channel_id}
            repaired: list[str] = []
            errors: list[str] = []
            async with Bot(settings.bot_token) as bot:
                for channel in repair_channels:
                    try:
                        media = InputMediaPhoto(
                            media=BufferedInputFile(chart_frame, filename=f"{canonical['code']}_chart.png"),
                            caption=caption,
                            parse_mode=ParseMode.HTML,
                        )
                        await bot.edit_message_media(
                            chat_id=targets[channel],
                            message_id=int(existing[channel]),
                            media=media,
                        )
                        repaired.append(channel)
                    except Exception as exc:
                        message = str(exc)
                        if "message is not modified" in message.lower():
                            repaired.append(channel)
                        else:
                            errors.append(f"{channel}: {message}")

            if repaired:
                db.add_signal_event(
                    int(canonical["id"]),
                    "CHART_REPAIR_APPLIED",
                    actor_type="BACKEND",
                    actor_id=canonical["created_by"],
                    account_number=str(canonical["issuer_account"] or ""),
                    correlation_id=str(canonical["code"]),
                    payload={"channels": repaired, "sha256": hashlib.sha256(raw).hexdigest(), "asset_state": asset_state},
                )

            missing_channels = [channel for channel in required_channels if existing[channel] is None]
            if missing_channels:
                result = await original_publish(canonical, chart_base64, allow_without_chart=allow_without_chart)
                if errors and asset_path:
                    # The canonical publisher may clear the file after finishing the
                    # missing destination. Recreate it so the failed repair can retry.
                    path = Path(asset_path)
                    if not path.exists():
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(raw)
                        db.save_mt5_signal_publication_asset(int(canonical["id"]), str(path))
                result.setdefault("errors", []).extend(errors)
                result["repaired_channels"] = repaired
                result["repair_pending"] = bool(errors)
                return result

            complete_repair = len(repaired) == len(repair_channels) and not errors
            if complete_repair:
                db.clear_mt5_signal_publication_asset(int(canonical["id"]))
                job = db.get_signal_chart_capture_job(int(canonical["id"]))
                if job:
                    db.mark_chart_capture_job_completed(int(job["id"]))
                with db.conn() as con:
                    con.execute("UPDATE signals SET status='ACTIVE',publication_stage='PUBLISHED' WHERE id=?", (int(canonical["id"]),))
            return {
                "free_message_id": existing["FREE"],
                "vip_message_id": existing["VIP"],
                "errors": errors,
                "published": True,
                "complete": complete_repair,
                "repaired_channels": repaired,
                "repair_pending": not complete_repair,
            }
        except Exception as exc:
            log.exception("late chart repair failed signal=%s", canonical["code"])
            db.add_signal_event(
                int(canonical["id"]),
                "CHART_REPAIR_FAILED",
                actor_type="BACKEND",
                actor_id=canonical["created_by"],
                account_number=str(canonical["issuer_account"] or ""),
                correlation_id=str(canonical["code"]),
                result="FAILED",
                reason=str(exc)[:1000],
                payload={"asset_state": asset_state},
            )
            return {"free_message_id": existing["FREE"], "vip_message_id": existing["VIP"],
                    "errors": [f"CHART_REPAIR: {exc}"], "published": bool(repair_channels),
                    "complete": False, "repair_pending": True}

    api_mod._publish_mt5_admin_signal_async = durable_publish

    original_live_state = _route(app, "/api/v1/autotrade/live-state", "POST").dependant.call

    def guarded_live_state(**kwargs):
        result = original_live_state(**kwargs)
        req = kwargs.get("req")
        account = str(kwargs.get("x_mt5_account") or getattr(req, "account_number", "") or "").strip()
        if not account:
            return result
        admin = api_mod._admin_auth(kwargs.get("x_admin_mode"), kwargs.get("x_admin_token"), account)
        if not admin:
            return result

        repaired = _queue_terminal_repairs(account)
        health = chart_delivery_health(account, minutes=_ALERT_WINDOW_MINUTES)
        background_tasks = kwargs.get("background_tasks")
        if background_tasks is not None and _alert_due(account, health):
            background_tasks.add_task(_send_admin_alert, account, health)

        if isinstance(result, dict):
            result["chart_repair_queued_signal_ids"] = repaired
            result["chart_delivery_health"] = {
                "severity": health["severity"],
                "fallback_publications": health["fallback_publications"],
                "repairs_applied": health["repairs_applied"],
                "counts": health["counts"],
            }
        return result

    _replace_route(app, "/api/v1/autotrade/live-state", "POST", guarded_live_state)

    @app.get("/api/v1/autotrade/admin/chart-capture/health")
    def chart_capture_health(
        minutes: int = Query(30, ge=5, le=1440),
        x_mt5_account: str | None = Header(None),
        x_admin_token: str | None = Header(None, alias="X-NEXUS-Admin-Token"),
    ):
        account = str(x_mt5_account or "").strip()
        api_mod.authorize_admin_mt5(account, x_admin_token)
        return {"ok": True, "account": account, **chart_delivery_health(account, minutes=minutes)}

    app.state.nexus_chart_delivery_guard_v24 = True
