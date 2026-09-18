from __future__ import annotations

import json
import uuid
from typing import Any, Callable

from fastapi import HTTPException
from fastapi.routing import APIRoute

from .. import db
from ..autotrade.symbol_registry import infer_category
from ..autotrade.trailing_profiles import profile_snapshot


_ACCEPTED_EXECUTION_STATUSES = {"EXECUTED", "PENDING", "ACTIVATED"}
_TERMINAL_FAILURE_STATUSES = {"REJECTED", "FAILED", "FAILED_RETRYABLE"}


def _route(app, path: str, method: str) -> APIRoute:
    method = method.upper()
    for candidate in app.router.routes:
        if isinstance(candidate, APIRoute) and candidate.path == path and method in candidate.methods:
            return candidate
    raise RuntimeError(f"NEXUS runtime route not found: {method} {path}")


def _replace_route(app, path: str, method: str, func: Callable[..., Any]) -> Callable[..., Any]:
    route = _route(app, path, method)
    original = route.dependant.call
    route.endpoint = func
    route.dependant.call = func
    return original


def _receipt_row(signal_id: int, telegram_id: int):
    with db.conn() as con:
        return con.execute(
            "SELECT status,ticket,error_text,first_seen_at,executed_at "
            "FROM autotrade_signal_receipts "
            "WHERE signal_id=? AND telegram_id=? AND platform='MT5'",
            (int(signal_id), int(telegram_id)),
        ).fetchone()


def _set_request_state(signal_id: int, status: str, error: str | None = None) -> None:
    with db.conn() as con:
        con.execute(
            "UPDATE miniapp_admin_signal_requests "
            "SET status=?,error_message=?,updated_at=? WHERE signal_id=?",
            (str(status), error, db.now_iso(), int(signal_id)),
        )


def _record_web_admin_receipt(
    api_mod,
    row,
    auth: dict[str, Any],
    account: str,
    status: str,
    ticket: str | None,
    error: str | None,
) -> dict[str, Any]:
    if not row or str(row["issuer_type"] or "").upper() != "WEB_ADMIN":
        raise ValueError("signal is not a WEB_ADMIN signal")
    if str(row["issuer_account"] or "") != str(account):
        raise HTTPException(status_code=403, detail="admin account does not own this WEB_ADMIN signal")

    status_u = str(status or "").strip().upper()
    uid = int(auth["telegram_id"])
    signal_id = int(row["id"])
    now = db.now_iso()

    if status_u in _ACCEPTED_EXECUTION_STATUSES:
        api_mod._require_broker_confirmed_receipt(row, account, status_u.lower(), ticket)

    db.ensure_admin_identity(uid)
    db.record_signal_delivery(
        signal_id,
        str(account),
        status=status_u,
        ticket=ticket,
        error_text=error,
    )

    executed_at = now if status_u in (_ACCEPTED_EXECUTION_STATUSES | _TERMINAL_FAILURE_STATUSES) else None
    with db.conn() as con:
        con.execute(
            """INSERT INTO autotrade_signal_receipts
               (signal_id,telegram_id,platform,status,first_seen_at,executed_at,ticket,error_text)
               VALUES(?,?, 'MT5', ?,?,?,?,?)
               ON CONFLICT(signal_id,telegram_id,platform) DO UPDATE SET
                 status=excluded.status,
                 executed_at=COALESCE(excluded.executed_at,autotrade_signal_receipts.executed_at),
                 ticket=COALESCE(excluded.ticket,autotrade_signal_receipts.ticket),
                 error_text=excluded.error_text""",
            (signal_id, uid, status_u.lower(), now, executed_at, ticket, error),
        )
        event_key = f"signal:{signal_id}:{uid}:MT5:{status_u.lower()}"
        payload = json.dumps({"status": status_u.lower(), "ticket": ticket, "error": error}, ensure_ascii=False)
        con.execute(
            "INSERT OR IGNORE INTO autotrade_notifications"
            "(telegram_id,event_key,event_type,signal_id,payload_json,created_at) VALUES(?,?,?,?,?,?)",
            (uid, event_key, "SIGNAL_RECEIPT", signal_id, payload, now),
        )

    db.add_signal_event(
        signal_id,
        "EXECUTION_RECEIPT",
        actor_type="MT5_ADMIN",
        actor_id=uid,
        account_number=str(account),
        result="SUCCESS" if status_u in _ACCEPTED_EXECUTION_STATUSES else status_u,
        reason=error,
        correlation_id=str(row["code"]),
        payload={"status": status_u, "ticket": ticket},
    )

    if status_u in _ACCEPTED_EXECUTION_STATUSES:
        # V37: broker execution unlocks canonical visual generation directly.
        # No screenshot job is required for Telegram publication.
        with db.conn() as con:
            con.execute(
                "UPDATE signals SET publication_stage='WAITING_FOR_VISUAL' WHERE id=?",
                (signal_id,),
            )
        _set_request_state(signal_id, "WAITING_VISUAL", None)
        return {"ok": True, "publication": "WAITING_VISUAL"}

    if status_u in _TERMINAL_FAILURE_STATUSES:
        final_status = "REJECTED" if status_u == "REJECTED" else "FAILED"
        with db.conn() as con:
            con.execute(
                "UPDATE signals SET status='REJECTED',publication_stage='EXECUTION_FAILED' WHERE id=?",
                (signal_id,),
            )
            con.execute(
                "UPDATE signal_chart_capture_jobs SET status='FAILED',error_text=?,failed_at=?,updated_at=? "
                "WHERE signal_id=? AND status IN ('PENDING','CLAIMED','CAPTURING')",
                (error or f"execution {status_u.lower()}", now, now, signal_id),
            )
        _set_request_state(signal_id, final_status, error or f"MT5 execution {status_u.lower()}")
        return {"ok": True, "publication": "BLOCKED_EXECUTION_FAILED"}

    return {"ok": True, "publication": "NOT_APPLICABLE"}


def install_miniapp_execution_gate(app) -> None:
    """Install an additive execution-truth bridge for MiniApp WEB_ADMIN signals.

    The patch intentionally leaves customer AutoTrade, MT5_ADMIN issuance and
    T05/T07 trailing code untouched.  WEB_ADMIN candidates are exposed only to
    the authenticated Admin EA; Telegram publication remains blocked until a
    broker-confirmed receipt exists. The final image is rendered from fresh
    MT5 MarketFeed candles and the canonical stored signal snapshot.
    """
    from . import api as api_mod
    from .. import miniapp_admin_api as mini_mod
    from .service import signal_to_payload

    if getattr(app.state, "nexus_miniapp_execution_gate_v1", False):
        return

    original_sync_request = mini_mod._sync_request

    def sync_request(row) -> dict[str, Any]:
        item = dict(row)
        signal = db.get_signal(int(item["signal_id"])) if item.get("signal_id") else None
        if not signal or str(signal["issuer_type"] or "").upper() != "WEB_ADMIN":
            return original_sync_request(row)

        signal_id = int(signal["id"])
        receipt = _receipt_row(signal_id, int(signal["created_by"]))
        receipt_status = str(receipt["status"] or "").upper() if receipt else "NOT_RECEIVED"
        job = db.get_signal_chart_capture_job(signal_id)
        status = str(item.get("status") or "WAITING_EXECUTION")
        error = item.get("error_message")

        if signal["free_message_id"] or signal["vip_message_id"]:
            status, error = "PUBLISHED", None
        elif receipt_status in _TERMINAL_FAILURE_STATUSES:
            status = "REJECTED" if receipt_status == "REJECTED" else "FAILED"
            error = str(receipt["error_text"] or f"MT5 execution {receipt_status.lower()}")
        elif receipt_status in _ACCEPTED_EXECUTION_STATUSES:
            stage = str(signal["publication_stage"] or "").upper()
            if stage in {"CANONICAL_VISUAL_READY", "FLASHCARD_READY"}:
                status = "PROCESSING_VISUAL"
            elif stage == "PUBLISH_FAILED":
                status, error = "FAILED", "Telegram publication failed"
            else:
                status = "WAITING_VISUAL"
        else:
            mt5 = mini_mod._admin_mt5_status()
            status = "WAITING_EXECUTION" if mt5["online"] else "WAITING_FOR_MT5"
            error = None

        if str(signal["publication_stage"] or "").upper() == "PUBLISH_FAILED":
            status, error = "FAILED", "Telegram publication failed"

        if status != item.get("status") or error != item.get("error_message"):
            _set_request_state(signal_id, status, error)

        item.update(
            {
                "status": status,
                "error_message": error,
                "signal": dict(signal),
                "chart_job": dict(job) if job else None,
                "live": mini_mod._admin_live_signal(signal),
                "execution_status": receipt_status,
                "targets": [float(target["price"]) for target in db.get_signal_targets(signal_id)],
            }
        )
        return item

    mini_mod._sync_request = sync_request

    def create_miniapp_signal(req, x_telegram_init_data=None):
        user = mini_mod._admin(x_telegram_init_data)
        mini_mod.init_miniapp_admin_schema()
        with db.conn() as con:
            existing = con.execute(
                "SELECT * FROM miniapp_admin_signal_requests WHERE request_id=?",
                (req.request_id,),
            ).fetchone()
        if existing:
            result = sync_request(existing)
            result["idempotent"] = True
            return result

        try:
            calc = mini_mod.calculate_auto_targets(req.symbol, req.direction, req.entry, req.stop_loss, req.digits)
            mt5 = mini_mod._admin_mt5_status()
            account = str(mt5.get("account_number") or "").strip()
            if not account:
                raise ValueError("NEXUS_ADMIN_MT5_ACCOUNTS is not configured")
            trail = profile_snapshot(req.trailing_code)
            token = f"MINIAPP:{int(user['id'])}:{req.request_id}"
            created = db.create_signal(
                market_type=infer_category(calc["symbol"]),
                symbol=calc["symbol"],
                direction=calc["direction"],
                entry_price=calc["entry"],
                stop_loss=calc["stop_loss"],
                targets=calc["targets"],
                risk_percent=req.risk_percent if req.volume_mode == "RISK" else 0,
                rr_ratio=3.0,
                destination=req.destination,
                chart_file_id=None,
                created_by=int(user["id"]),
                timeframe=req.timeframe,
                order_type="MARKET",
                volume_mode=req.volume_mode,
                lot_size=req.lot_size,
                trailing_code=req.trailing_code,
                trailing_name=str(trail.get("name") or req.trailing_code),
                trailing_config=trail,
                publish_token=token,
            )
            now = db.now_iso()
            with db.conn() as con:
                con.execute(
                    "UPDATE signals SET signal_uuid=COALESCE(signal_uuid,?),issuer_type='WEB_ADMIN',issuer_account=?,"
                    "issued_at=COALESCE(issued_at,?),status='DRAFT',publication_stage='WAITING_EXECUTION' WHERE id=?",
                    (str(uuid.uuid4()), account, now, int(created["id"])),
                )

            payload = {
                **calc,
                "setup_mode": req.setup_mode,
                "destination": req.destination,
                "timeframe": req.timeframe,
                "trailing_code": req.trailing_code,
                "trailing_name": str(trail.get("name") or req.trailing_code),
                "trailing_config": trail,
                "volume_mode": req.volume_mode,
                "lot_size": req.lot_size,
                "risk_percent": req.risk_percent,
                "mt5_account": account,
            }
            request_status = "WAITING_EXECUTION" if mt5["online"] else "WAITING_FOR_MT5"
            with db.conn() as con:
                con.execute(
                    "INSERT OR IGNORE INTO miniapp_admin_signal_requests"
                    "(request_id,admin_telegram_id,signal_id,status,error_message,payload_json,created_at,updated_at) "
                    "VALUES(?,?,?,?,NULL,?,?,?)",
                    (
                        req.request_id,
                        int(user["id"]),
                        int(created["id"]),
                        request_status,
                        json.dumps(payload, ensure_ascii=False),
                        now,
                        now,
                    ),
                )
                request_row = con.execute(
                    "SELECT * FROM miniapp_admin_signal_requests WHERE request_id=?",
                    (req.request_id,),
                ).fetchone()

            db.add_signal_event(
                int(created["id"]),
                "MINIAPP_SIGNAL_CREATED",
                actor_type="MINIAPP_ADMIN",
                actor_id=int(user["id"]),
                request_id=req.request_id,
                correlation_id=str(created["code"]),
                payload=payload,
            )
            db.add_signal_event(
                int(created["id"]),
                "EXECUTION_QUEUED",
                actor_type="MINIAPP_ADMIN",
                actor_id=int(user["id"]),
                account_number=account,
                request_id=req.request_id,
                correlation_id=str(created["code"]),
                payload={"account": account, "execution_scope": "ADMIN_EA_ONLY"},
            )
            result = sync_request(request_row)
            result["idempotent"] = False
            result["mt5_admin"] = mt5
            return result
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    _replace_route(app, "/miniapp/api/admin/signals", "POST", create_miniapp_signal)

    original_get_signals = _route(app, "/api/v1/autotrade/signals", "GET").dependant.call

    def get_signals(**kwargs):
        key, account, _, _, _ = api_mod._ea_auth_headers(
            kwargs.get("x_license_key"), kwargs.get("x_mt5_account")
        )
        admin = api_mod._admin_auth(kwargs.get("x_admin_mode"), kwargs.get("x_admin_token"), account)
        if not admin:
            return original_get_signals(**kwargs)

        after_id = int(kwargs.get("after_id") or 0)
        limit = max(1, min(int(kwargs.get("limit") or 50), 100))
        with db.conn() as con:
            rows = con.execute(
                """SELECT s.* FROM signals s
                   WHERE s.id>? AND (
                     (s.status='ACTIVE' AND s.issuer_type IN ('MT5_ADMIN','WEB_ADMIN'))
                     OR (
                       s.issuer_type='WEB_ADMIN'
                       AND s.issuer_account=?
                       AND s.status='DRAFT'
                       AND UPPER(COALESCE(s.publication_stage,'')) IN ('WAITING_EXECUTION','WAITING_FOR_VISUAL','CANONICAL_VISUAL_READY')
                       AND NOT EXISTS (
                         SELECT 1 FROM autotrade_signal_receipts r
                         WHERE r.signal_id=s.id AND r.platform='MT5'
                           AND UPPER(COALESCE(r.status,'')) IN ('EXECUTED','PENDING','ACTIVATED','REJECTED','FAILED','FAILED_RETRYABLE')
                       )
                     )
                   )
                   ORDER BY s.id ASC LIMIT ?""",
                (after_id, str(account), limit),
            ).fetchall()
        return {"license_status": "ADMIN", "signals": [signal_to_payload(row) for row in rows]}

    _replace_route(app, "/api/v1/autotrade/signals", "GET", get_signals)

    original_get_receipt = _route(app, "/api/v1/autotrade/signal-receipt", "GET").dependant.call

    def signal_receipt_get(**kwargs):
        row = db.get_signal(int(kwargs["signal_db_id"]))
        if not row or str(row["issuer_type"] or "").upper() != "WEB_ADMIN":
            return original_get_receipt(**kwargs)
        key, account, _, _, _ = api_mod._ea_auth_headers(
            kwargs.get("x_license_key"), kwargs.get("x_mt5_account")
        )
        admin = api_mod._admin_auth(kwargs.get("x_admin_mode"), kwargs.get("x_admin_token"), account)
        auth = api_mod._resolve_ea_auth(key, account, admin=admin)
        return _record_web_admin_receipt(
            api_mod,
            row,
            auth,
            account,
            kwargs["status"],
            kwargs.get("ticket"),
            kwargs.get("error"),
        )

    _replace_route(app, "/api/v1/autotrade/signal-receipt", "GET", signal_receipt_get)

    original_post_receipt = _route(app, "/api/v1/autotrade/signal-receipt", "POST").dependant.call

    def signal_receipt_post(**kwargs):
        req = kwargs["req"]
        row = db.get_signal(int(req.signal_db_id))
        if not row or str(row["issuer_type"] or "").upper() != "WEB_ADMIN":
            return original_post_receipt(**kwargs)
        key = kwargs.get("x_license_key") or req.license_key
        account = kwargs.get("x_mt5_account") or req.account_number
        admin = api_mod._admin_auth(kwargs.get("x_admin_mode"), kwargs.get("x_admin_token"), account)
        auth = api_mod._resolve_ea_auth(key, account, admin=admin)
        return _record_web_admin_receipt(
            api_mod, row, auth, str(account), req.status, req.ticket, req.error
        )

    _replace_route(app, "/api/v1/autotrade/signal-receipt", "POST", signal_receipt_post)

    original_live_state = _route(app, "/api/v1/autotrade/live-state", "POST").dependant.call

    def live_state(**kwargs):
        result = original_live_state(**kwargs)
        req = kwargs["req"]
        account = str(kwargs.get("x_mt5_account") or req.account_number or "").strip()
        admin = api_mod._admin_auth(kwargs.get("x_admin_mode"), kwargs.get("x_admin_token"), account)
        if not admin:
            return result
        auth = api_mod._resolve_ea_auth(
            kwargs.get("x_license_key") or req.license_key,
            account,
            admin=admin,
            broker=kwargs.get("x_broker") or req.broker,
            server=kwargs.get("x_server") or req.server,
            ea_version=kwargs.get("x_ea_version") or req.ea_version,
        )
        repaired: list[int] = []
        items = [(item, "executed") for item in req.positions] + [(item, "pending") for item in req.orders]
        for item, receipt_status in items:
            code = str(item.signal_code or "").strip()
            if not code.startswith("NX-") or not bool(item.nexus_managed):
                continue
            row = db.get_signal_by_code(code)
            if not row or str(row["issuer_type"] or "").upper() != "WEB_ADMIN":
                continue
            if str(row["issuer_account"] or "") != account:
                continue
            existing = _receipt_row(int(row["id"]), int(auth["telegram_id"]))
            if existing and str(existing["status"] or "").upper() in _ACCEPTED_EXECUTION_STATUSES:
                continue
            try:
                _record_web_admin_receipt(
                    api_mod,
                    row,
                    auth,
                    account,
                    receipt_status,
                    str(item.ticket),
                    None,
                )
                repaired.append(int(row["id"]))
            except (HTTPException, ValueError):
                continue
        if isinstance(result, dict):
            result["web_admin_reconciled_signal_ids"] = sorted(set(repaired))
        return result

    _replace_route(app, "/api/v1/autotrade/live-state", "POST", live_state)

    original_publisher = api_mod._publish_mt5_admin_signal_async

    async def execution_gated_publisher(row, chart_base64=None, *, allow_without_chart=False):
        issuer_type = (
            str(row.get("issuer_type") or "").upper()
            if isinstance(row, dict)
            else str(row["issuer_type"] or "").upper()
        )
        if issuer_type == "WEB_ADMIN":
            signal_id = int(row.get("id") if isinstance(row, dict) else row["id"])
            receipt = db.mt5_signal_live_state(signal_id) or {}
            exec_status = str(receipt.get("receipt_status") or "NOT_RECEIVED").upper()
            if exec_status not in _ACCEPTED_EXECUTION_STATUSES:
                return {
                    "free_message_id": None,
                    "vip_message_id": None,
                    "errors": [f"EXECUTION_GATE: WEB_ADMIN receipt status {exec_status} is not publishable"],
                    "published": False,
                    "complete": False,
                    "execution_status": exec_status,
                }
            # V37: ChartAgent screenshots are diagnostic-only for WEB_ADMIN.
            # Publication artwork is built from the canonical stored signal and
            # fresh MT5 MarketFeed candles by the outer visual wrapper.
        result = await original_publisher(row, chart_base64, allow_without_chart=allow_without_chart)
        if issuer_type == "WEB_ADMIN" and isinstance(result, dict):
            receipt = db.mt5_signal_live_state(int(row.get("id") if isinstance(row, dict) else row["id"])) or {}
            result["execution_status"] = str(receipt.get("receipt_status") or "NOT_RECEIVED").upper()
        return result

    api_mod._publish_mt5_admin_signal_async = execution_gated_publisher

    app.state.nexus_miniapp_execution_gate_v1 = True
