from __future__ import annotations

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


def _candidate_rows(account: str) -> list[Any]:
    with db.conn() as con:
        return con.execute(
            """SELECT * FROM signals
               WHERE issuer_account=?
                 AND UPPER(COALESCE(issuer_type,'')) IN ('MT5_ADMIN','WEB_ADMIN')
                 AND COALESCE(free_message_id,0)=0
                 AND COALESCE(vip_message_id,0)=0
                 AND UPPER(COALESCE(status,'')) NOT IN ('REJECTED','CLOSED')
                 AND UPPER(COALESCE(publication_stage,'')) NOT IN ('EXECUTION_FAILED')
               ORDER BY id DESC LIMIT 40""",
            (str(account),),
        ).fetchall()


def install_publication_recovery(app) -> None:
    """Make Telegram publication self-healing after broker execution.

    Every Admin EA live-state sync is already a durable heartbeat. Re-use that
    heartbeat to retry unpublished authority signals. A real chart remains the
    preferred path. If chart capture reaches a terminal FAILED/EXPIRED state,
    publication falls back to the existing text/card publisher only after a
    broker-confirmed execution receipt, preventing an executed position from
    remaining invisible in Telegram forever.
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
        for row in _candidate_rows(account):
            signal_id = int(row["id"])
            if not _accepted_receipt(signal_id):
                continue
            job = db.get_signal_chart_capture_job(signal_id)
            job_status = str(job["status"] or "").upper() if job else ""
            stage = str(row["publication_stage"] or "").upper()

            if job_status in _READY_CHART:
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
                    reason=str(job["error_text"] or "chart capture terminal failure") if job else "chart capture terminal failure",
                    payload={"chart_status": job_status, "publication_stage": stage, "fallback": True},
                )

        if isinstance(result, dict):
            result["publication_recovery_signal_ids"] = sorted(set(queued))
            result["publication_fallback_signal_ids"] = sorted(set(fallback))
        return result

    _replace_route(app, "/api/v1/autotrade/live-state", "POST", live_state)
    app.state.nexus_publication_recovery_v1 = True
