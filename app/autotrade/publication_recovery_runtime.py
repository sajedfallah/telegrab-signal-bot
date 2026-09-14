from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from fastapi.routing import APIRoute

from .. import db

_ACCEPTED = {"EXECUTED", "PENDING", "ACTIVATED"}
_TERMINAL_CHART = {"FAILED", "EXPIRED"}
_READY_CHART = {"UPLOADED", "COMPLETED"}


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


def install_publication_recovery(app) -> None:
    """Make Telegram publication self-healing after broker execution.

    Every Admin EA live-state sync is already a durable heartbeat. Re-use that
    heartbeat to retry incomplete authority-signal publication. Recovery is
    destination-aware, so a partial BOTH publication retries only the missing
    channel through the publisher's existing channel claims/idempotency.

    WEB_ADMIN keeps the real-chart-first policy. If chart capture reaches a
    terminal FAILED/EXPIRED state, or a READY job has lost its durable asset,
    publication falls back to the existing generated card only after a
    broker-confirmed execution receipt. MT5_ADMIN signals do not depend on a
    chart-capture job and are retried directly after the same broker receipt.
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

        for row in _candidate_rows(account):
            signal_id = int(row["id"])
            if _publication_complete(row) or not _accepted_receipt(signal_id):
                continue

            issuer_type = str(row["issuer_type"] or "").strip().upper()
            stage = str(row["publication_stage"] or "").upper()

            # Native MT5_ADMIN publication has no chart-capture job dependency.
            # A lost background task must therefore be retried directly from the
            # next authenticated Admin live-state heartbeat.
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

            job = db.get_signal_chart_capture_job(signal_id)
            if not job:
                # Accepted WEB_ADMIN execution without a chart job is an
                # inconsistent but recoverable state. Recreate the job instead
                # of leaving a live broker position permanently silent.
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
                    # READY without a durable file can otherwise loop forever.
                    # Broker execution truth wins: publish the generated card and
                    # keep an explicit audit event explaining the degraded asset.
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
                        reason="chart capture is READY but publication asset is missing",
                        payload={"chart_status": job_status, "publication_stage": stage, "fallback": True},
                    )
                continue

            if job_status in _TERMINAL_CHART:
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
                    reason=str(job["error_text"] or "chart capture terminal failure"),
                    payload={"chart_status": job_status, "publication_stage": stage, "fallback": True},
                )

        if isinstance(result, dict):
            result["publication_recovery_signal_ids"] = sorted(set(queued))
            result["publication_fallback_signal_ids"] = sorted(set(fallback))
            result["publication_chart_repaired_signal_ids"] = sorted(set(chart_repaired))
        return result

    _replace_route(app, "/api/v1/autotrade/live-state", "POST", live_state)
    app.state.nexus_publication_recovery_v1 = True
