from __future__ import annotations

import json

from . import db

_INSTALLED = False


def install_web_signal_command_runtime() -> None:
    """Extend the existing command queue to WEB_ADMIN signals.

    MT5_ADMIN behavior remains delegated to the production implementation.
    WEB_ADMIN signals use the same durable autotrade_commands table and event
    ledger, so customer EAs receive identical management commands.
    """
    global _INSTALLED
    if _INSTALLED:
        return

    original = db.create_autotrade_command

    def _create(
        signal_id: int,
        command: str,
        payload: dict | None = None,
        *,
        actor_type: str = "WEB_ADMIN",
        actor_id: str | int | None = None,
        account_number: str | None = None,
    ) -> int:
        signal = db.get_signal(signal_id)
        if not signal:
            raise ValueError("signal not found")
        issuer = str(signal["issuer_type"] or "").upper() if "issuer_type" in signal.keys() else ""
        if issuer == "MT5_ADMIN":
            return original(
                signal_id,
                command,
                payload,
                actor_type=actor_type,
                actor_id=actor_id,
                account_number=account_number,
            )
        if issuer != "WEB_ADMIN":
            raise ValueError("only MT5_ADMIN/WEB_ADMIN signals accept admin commands")

        now = db.now_iso()
        with db.conn() as con:
            cur = con.execute(
                "INSERT INTO autotrade_commands(signal_id,command,payload_json,created_at) VALUES(?,?,?,?)",
                (
                    int(signal_id),
                    str(command).upper(),
                    json.dumps(payload or {}, ensure_ascii=False, separators=(",", ":")),
                    now,
                ),
            )
            command_id = int(cur.lastrowid)
        db.add_signal_event(
            int(signal_id),
            "COMMAND",
            actor_type=str(actor_type or "WEB_ADMIN").upper(),
            actor_id=actor_id,
            account_number=account_number,
            request_id=f"CMD-{command_id}",
            correlation_id=str(signal["code"]),
            payload={"command": str(command).upper(), "command_id": command_id, **(payload or {})},
        )
        return command_id

    db.create_autotrade_command = _create
    _INSTALLED = True
