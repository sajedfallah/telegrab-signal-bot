from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from fastapi.routing import APIRoute

from .. import db
from .broker_chart_fallback import ensure_broker_chart_asset

_ACCEPTED = {"EXECUTED", "PENDING", "ACTIVATED"}
_TERMINAL_CHART = {"FAILED", "EXPIRED"}
_READY_CHART = {"UPLOADED", "COMPLETED"}
_INFLIGHT_CHART = {"PENDING", "CLAIMED", "CAPTURING"}
_PUBLICATION_CHART_GRACE_SECONDS = 20


def _route(app, path: str, method: str) -> APIRoute:
    method = method.upper()
    for candidate in app.router.routes:
        if isinstance(candidate, APIRoute) and candidate.path == path and method in candidate.methods:
            return candidate
    raise RuntimeError(f"NEXUS publication recovery route not found: {method} {path}")


def _replace_route(app, path: str, method: str, func: Callable[..., Any]) -> Callable[..., Any]:
    route = _route(app, path, method)
    original = route.dependant.call
    route.endpoint = func
    route.dependant.call = func
    return original


def _accepted_receipt(signal_id: int) -> bool:
    with db.conn() as con:
        row = con.execute(
            """SELECT status FROM autotrade_signal_receipts
               WHERE signal_id=? AND platform='MT5'
               ORDER BY COALESCE(executed_at,first_seen_at) DESC LIMIT 1""",
            (int(signal_id),),
        ).fetchone()
    return bool(row and str(row["status"] or "").strip().upper() in _ACCEPTED)


def _publication_complete(row: Any) -> bool:
    destination = str(row["destination"] or "BOTH").strip().upper()
    free_done = bool(row["free_message_id"])
    vip_done = bool(row["vip_message_id"])
    if destination == "FREE":
        return free_done
    if destination == "VIP":
        return vip_done
    return free_done and vip_done


def _publication_asset_exists(signal_id: int) -> bool:
    asset_path = db.get_mt5_signal_publication_asset(int(signal_id))
    if not asset_path:
        return False
    try:
        path = Path(str(asset_path))
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def _parse_utc(value: str | None) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _job_age_seconds(job: Any, now: datetime | None = None) -> float | None:
    if not job:
        return None
    requested_at = _parse_utc(job["requested_at"] if "requested_at" in job.keys() else None)
    if requested_at is None:
        return None
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return max(0.0, (current.astimezone(timezone.utc) - requested_at).total_seconds())


def _chart_job_overdue(job: Any, now: datetime | None = None) -> bool:
    if not job:
        return False
    status = str(job["status"] or "").strip().upper()
    if status not in _INFLIGHT_CHART:
        return False
    expires_at = _parse_utc(job["expires_at"])
    if expires_at is None:
        return False
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return expires_at <= current.astimezone(timezone.utc)


def _expire_overdue_chart_job(job: Any) -> bool:
    if not _chart_job_overdue(job):
        return False
    now = db.now_iso()
    with db.conn() as con:
        cur = con.execute(
            """UPDATE signal_chart_capture_jobs
               SET status='EXPIRED',failed_at=COALESCE(failed_at,?),
                   error_text='job expired without completed chart capture',updated_at=?
               WHERE id=? AND status IN ('PENDING','CLAIMED','CAPTURING') AND expires_at<=?""",
            (now, now, int(job["id"]), now),
        )
    return cur.rowcount > 0


def _candidate_rows(account: str) -> list[Any]:
    with db.conn() as con:
        return con.execute(
            """SELECT * FROM signals
               WHERE issuer_account=?
                 AND UPPER(COALESCE(issuer_type,'')) IN ('MT5_ADMIN','WEB_ADMIN')
                 AND UPPER(COALESCE(status,'')) NOT IN ('REJECTED','CLOSED')
                 AND UPPER(COALESCE(publication_stage,'')) NOT IN ('EXECUTION_FAILED')
                 AND (
                   (UPPER(COALESCE(destination,'BOTH'))='FREE' AND COALESCE(free_message_id,0)=0)
                   OR (UPPER(COALESCE(destination,'BOTH'))='VIP' AND COALESCE(vip_message_id,0)=0)
                   OR (
                     UPPER(COALESCE(destination,'BOTH')) NOT IN ('FREE','VIP')
                     AND (COALESCE(free_message_id,0)=0 OR COALESCE(vip_message_id,0)=0)
                   )
                 )
               ORDER BY id DESC LIMIT 40""",
            (str(account),),
        ).fetchall()


def _stage_broker_chart(signal: Any) -> dict[str, Any]:
    """Best-effort broker-truth chart generation from the existing MT5 feed."""
    try:
        return ensure_broker_chart_asset(signal)
    except Exception as exc:
        return {"ok": False, "reason": f"BROKER_FALLBACK_EXCEPTION:{exc}"}


def install_publication_recovery(app) -> None:
    """Make text-only Telegram publication self-healing after broker execution.

    V45 removes every visual dependency from signal publication. Broker receipt
    truth remains mandatory, while chart jobs, MarketFeed candles and image
    assets are irrelevant to the Telegram root message.
    """
    if getattr(app.state, "nexus_publication_recovery_v1", False):
        return

    from . import api as api_mod

    original_live_state = _route(app, "/api/v1/autotrade/live-state", "POST").dependant.call

    def live_state(**kwargs):
        result = original_live_state(**kwargs)
        req = kwargs.get("req")
        if req is None:
            return result
        account = str(kwargs.get("x_mt5_account") or getattr(req, "account_number", "") or "").strip()
        if not account:
            return result
        admin = api_mod._admin_auth(kwargs.get("x_admin_mode"), kwargs.get("x_admin_token"), account)
        if not admin:
            return result

        background_tasks = kwargs.get("background_tasks")
        if background_tasks is None:
            return result

        queued: list[int] = []
        fallback: list[int] = []
        chart_repaired: list[int] = []
        chart_expired: list[int] = []
        broker_chart: list[int] = []

        for row in _candidate_rows(account):
            signal_id = int(row["id"])
            if _publication_complete(row) or not _accepted_receipt(signal_id):
                continue

            issuer_type = str(row["issuer_type"] or "").strip().upper()
            stage = str(row["publication_stage"] or "").upper()

            if issuer_type == "MT5_ADMIN":
                background_tasks.add_task(api_mod._publish_mt5_admin_signal_async, row, None)
                queued.append(signal_id)
                db.add_signal_event(
                    signal_id,
                    "PUBLICATION_RECOVERY_QUEUED",
                    actor_type="BACKEND",
                    account_number=account,
                    correlation_id=str(row["code"]),
                    payload={"chart_status": None, "publication_stage": stage, "fallback": False},
                )
                continue

            # V45 WEB_ADMIN rule: publication is text-only and has no chart,
            # MarketFeed, ChartAgent, image asset, or visual-fingerprint gate.
            if issuer_type == "WEB_ADMIN":
                background_tasks.add_task(
                    api_mod._publish_mt5_admin_signal_async,
                    row,
                    None,
                    allow_without_chart=True,
                )
                queued.append(signal_id)
                db.add_signal_event(
                    signal_id,
                    "PUBLICATION_TEXT_QUEUED",
                    actor_type="BACKEND",
                    account_number=account,
                    correlation_id=str(row["code"]),
                    payload={
                        "publication_stage": stage,
                        "publication_mode": "TEXT_ONLY",
                    },
                )
                continue

            job = db.get_signal_chart_capture_job(signal_id)
            if not job:
                try:
                    job = db.create_chart_capture_job(signal_id, "PUBLICATION_RECOVERY")
                    chart_repaired.append(signal_id)
                    db.add_signal_event(
                        signal_id,
                        "CHART_JOB_RECOVERED",
                        actor_type="BACKEND",
                        account_number=account,
                        correlation_id=str(row["code"]),
                        payload={"job_id": int(job["id"]), "publication_stage": stage},
                    )
                except ValueError:
                    job = db.get_signal_chart_capture_job(signal_id)
                if not job:
                    continue

            job_status = str(job["status"] or "").upper()

            if _expire_overdue_chart_job(job):
                job_status = "EXPIRED"
                chart_expired.append(signal_id)
                db.add_signal_event(
                    signal_id,
                    "CHART_JOB_EXPIRED_RECOVERY",
                    actor_type="BACKEND",
                    account_number=account,
                    correlation_id=str(row["code"]),
                    reason="chart capture TTL elapsed without completed chart capture",
                    payload={"job_id": int(job["id"]), "publication_stage": stage},
                )

            if job_status in _INFLIGHT_CHART:
                chart_age = _job_age_seconds(job)
                if chart_age is not None and chart_age >= _PUBLICATION_CHART_GRACE_SECONDS:
                    broker = _stage_broker_chart(row)
                    broker_ok = bool(broker.get("ok"))
                    if broker_ok:
                        broker_chart.append(signal_id)
                    background_tasks.add_task(
                        api_mod._publish_mt5_admin_signal_async,
                        row,
                        None,
                        allow_without_chart=True,
                    )
                    queued.append(signal_id)
                    fallback.append(signal_id)
                    db.add_signal_event(
                        signal_id,
                        "PUBLICATION_FALLBACK_QUEUED",
                        actor_type="BACKEND",
                        account_number=account,
                        correlation_id=str(row["code"]),
                        reason=(
                            "fresh MT5 MarketFeed chart staged after ChartAgent grace timeout; "
                            "publishing fallback while capture remains repairable"
                            if broker_ok
                            else (
                                f"real MT5 chart not ready within {_PUBLICATION_CHART_GRACE_SECONDS}s; "
                                "publishing fallback while capture remains repairable"
                            )
                        ),
                        payload={
                            "chart_status": job_status,
                            "publication_stage": stage,
                            "fallback": True,
                            "fallback_mode": "CHART_GRACE_TIMEOUT",
                            "fallback_asset_mode": "MT5_MARKET_FEED" if broker_ok else "CHART_PLACEHOLDER",
                            "broker_chart": broker,
                            "chart_age_seconds": round(chart_age, 3),
                            "chart_grace_seconds": _PUBLICATION_CHART_GRACE_SECONDS,
                            "job_id": int(job["id"]),
                        },
                    )
                    continue

            if job_status in _READY_CHART:
                if _publication_asset_exists(signal_id):
                    background_tasks.add_task(api_mod._publish_mt5_admin_signal_async, row, None)
                    queued.append(signal_id)
                    db.add_signal_event(
                        signal_id,
                        "PUBLICATION_RECOVERY_QUEUED",
                        actor_type="BACKEND",
                        account_number=account,
                        correlation_id=str(row["code"]),
                        payload={"chart_status": job_status, "publication_stage": stage, "fallback": False},
                    )
                else:
                    broker = _stage_broker_chart(row)
                    broker_ok = bool(broker.get("ok"))
                    if broker_ok:
                        broker_chart.append(signal_id)
                    background_tasks.add_task(
                        api_mod._publish_mt5_admin_signal_async,
                        row,
                        None,
                        allow_without_chart=True,
                    )
                    queued.append(signal_id)
                    fallback.append(signal_id)
                    db.add_signal_event(
                        signal_id,
                        "PUBLICATION_FALLBACK_QUEUED",
                        actor_type="BACKEND",
                        account_number=account,
                        correlation_id=str(row["code"]),
                        reason=(
                            "chart capture asset missing; fresh MT5 MarketFeed chart staged"
                            if broker_ok
                            else "chart capture is READY but publication asset is missing"
                        ),
                        payload={
                            "chart_status": job_status,
                            "publication_stage": stage,
                            "fallback": True,
                            "fallback_mode": "MT5_MARKET_FEED" if broker_ok else "CHART_PLACEHOLDER",
                            "broker_chart": broker,
                        },
                    )
                continue

            if job_status in _TERMINAL_CHART:
                broker = _stage_broker_chart(row)
                broker_ok = bool(broker.get("ok"))
                if broker_ok:
                    broker_chart.append(signal_id)
                background_tasks.add_task(
                    api_mod._publish_mt5_admin_signal_async,
                    row,
                    None,
                    allow_without_chart=True,
                )
                queued.append(signal_id)
                fallback.append(signal_id)
                db.add_signal_event(
                    signal_id,
                    "PUBLICATION_FALLBACK_QUEUED",
                    actor_type="BACKEND",
                    account_number=account,
                    correlation_id=str(row["code"]),
                    reason=(
                        "terminal ChartAgent failure; fresh MT5 MarketFeed chart staged"
                        if broker_ok
                        else (
                            "chart capture TTL elapsed without completed capture"
                            if signal_id in chart_expired
                            else str(job["error_text"] or "chart capture terminal failure")
                        )
                    ),
                    payload={
                        "chart_status": job_status,
                        "publication_stage": stage,
                        "fallback": True,
                        "fallback_mode": "MT5_MARKET_FEED" if broker_ok else "CHART_PLACEHOLDER",
                        "broker_chart": broker,
                    },
                )

        if isinstance(result, dict):
            result["publication_recovery_signal_ids"] = sorted(set(queued))
            result["publication_fallback_signal_ids"] = sorted(set(fallback))
            result["publication_chart_repaired_signal_ids"] = sorted(set(chart_repaired))
            result["publication_chart_expired_signal_ids"] = sorted(set(chart_expired))
            result["publication_broker_chart_signal_ids"] = sorted(set(broker_chart))
        return result

    _replace_route(app, "/api/v1/autotrade/live-state", "POST", live_state)
    app.state.nexus_publication_recovery_v1 = True
