from __future__ import annotations

from typing import Any, Callable

from fastapi import Header, HTTPException
from fastapi.routing import APIRoute

from .. import db

_ACCEPTED = {"EXECUTED", "PENDING", "ACTIVATED"}


def _route(app, path: str, method: str) -> APIRoute:
    method = method.upper()
    for candidate in app.router.routes:
        if isinstance(candidate, APIRoute) and candidate.path == path and method in candidate.methods:
            return candidate
    raise RuntimeError(f"NEXUS chart repair claim route not found: {method} {path}")


def _replace_route(app, path: str, method: str, func: Callable[..., Any]) -> None:
    route = _route(app, path, method)
    route.endpoint = func
    route.dependant.call = func


def _accepted_receipt(signal_id: int) -> bool:
    with db.conn() as con:
        row = con.execute(
            """SELECT status FROM autotrade_signal_receipts
               WHERE signal_id=? AND platform='MT5'
               ORDER BY COALESCE(executed_at,first_seen_at) DESC LIMIT 1""",
            (int(signal_id),),
        ).fetchone()
    return bool(row and str(row["status"] or "").strip().upper() in _ACCEPTED)


def _repair_eligible(signal, account: str) -> bool:
    if not signal or str(signal["issuer_type"] or "").upper() != "WEB_ADMIN":
        return False
    if str(signal["issuer_account"] or "") != str(account):
        return False
    status = str(signal["status"] or "").upper()
    if status == "DRAFT":
        return True
    # A fallback publication changes the signal to ACTIVE. A bounded V24 repair
    # job must still be claimable so a late real MT5 chart can replace the
    # already-published placeholder. Require both broker execution truth and an
    # existing Telegram anchor before allowing this repair-only ACTIVE case.
    if status == "ACTIVE" and (signal["free_message_id"] or signal["vip_message_id"]):
        return _accepted_receipt(int(signal["id"]))
    return False


def install_chart_repair_claim_runtime(app) -> None:
    """Permit ChartAgent to claim bounded repair jobs after fallback publication.

    The original claim route correctly accepted only DRAFT WEB_ADMIN signals for
    first publication. Once a fallback image is published, the signal becomes
    ACTIVE, so a later repair job would otherwise be rejected before capture.
    This additive wrapper preserves the DRAFT rule and opens only the narrow
    ACTIVE+published+broker-confirmed repair case.
    """
    if getattr(app.state, "nexus_chart_repair_claim_v24", False):
        return

    from . import api as api_mod

    def claim_chart_capture_job(
        x_mt5_account: str | None = Header(None),
        x_admin_token: str | None = Header(None, alias="X-NEXUS-Admin-Token"),
    ):
        account = str(x_mt5_account or "").strip()
        try:
            auth = api_mod.authorize_admin_mt5(account, x_admin_token)
            api_mod._chart_rate_limit(account)
            job = db.claim_next_chart_capture_job(account)
            if not job:
                return {"ok": True, "job": None, "poll_after_seconds": 2}

            signal = db.get_signal(int(job["signal_id"]))
            if not _repair_eligible(signal, account):
                db.fail_chart_capture_job(
                    int(job["id"]), account,
                    "signal is not eligible for initial or repair chart capture",
                )
                raise HTTPException(status_code=409, detail="signal is not eligible for chart capture")

            repair_mode = str(signal["status"] or "").upper() == "ACTIVE"
            targets = [float(t["price"]) for t in db.get_signal_targets(int(signal["id"]))]
            db.add_signal_event(
                int(signal["id"]),
                "CHART_JOB_CLAIMED",
                actor_type="MT5_ADMIN",
                actor_id=auth["telegram_id"],
                account_number=account,
                request_id=f"chart-job:{job['id']}",
                payload={
                    "attempt": int(job["attempt_count"]),
                    "repair_mode": repair_mode,
                    "publication_stage": str(signal["publication_stage"] or ""),
                },
            )
            return {
                "ok": True,
                "job": {
                    "job_id": int(job["id"]),
                    "signal_db_id": int(signal["id"]),
                    "signal_code": str(signal["code"]),
                    "symbol": str(signal["symbol"]),
                    "timeframe": str(signal["timeframe"] or "M5"),
                    "direction": str(signal["direction"]),
                    "entry": float(signal["entry_price"]),
                    "sl": float(signal["stop_loss"]),
                    "targets": targets,
                    "repair_mode": repair_mode,
                },
            }
        except api_mod.AutoTradeError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    _replace_route(app, "/api/v1/autotrade/admin/chart-capture/next", "GET", claim_chart_capture_job)
    _replace_route(app, "/api/v1/autotrade/admin/chart-capture/jobs/next", "GET", claim_chart_capture_job)
    app.state.nexus_chart_repair_claim_v24 = True
