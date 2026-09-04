from __future__ import annotations

"""Server-side capital protection for licensed NEXUS AutoTrade accounts.

The firewall is intentionally conservative: it controls *new* signal delivery
only. Existing positions and management commands continue to flow so a kill
switch never strands an open trade without SL/TP/close management.

Risk is normalized in R because broker balance/equity is not yet part of the
server heartbeat contract. Where MT5 supplies ``realized_r`` it is authoritative;
otherwise net P/L divided by recorded ``risk_cash`` is used as a fallback.
"""

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any

from .. import db
from . import service

DEFAULT_DAILY_LOSS_LIMIT_R = 3.0
DEFAULT_MIN_RISK_MULTIPLIER = 0.50
DEFAULT_MAX_LOSS_STREAK = 3

_INSTALLED = False


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    reason: str
    daily_realized_r: float
    loss_streak: int
    risk_multiplier: float
    daily_loss_limit_r: float
    dynamic_risk_enabled: bool
    global_kill_switch: bool
    user_kill_switch: bool

    def as_payload(self) -> dict[str, Any]:
        return asdict(self)


def _truthy(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def ensure_schema() -> None:
    with db.conn() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS autotrade_risk_profiles (
                telegram_id INTEGER PRIMARY KEY,
                daily_loss_limit_r REAL NOT NULL DEFAULT 3.0,
                dynamic_risk_enabled INTEGER NOT NULL DEFAULT 1,
                min_risk_multiplier REAL NOT NULL DEFAULT 0.50,
                max_loss_streak INTEGER NOT NULL DEFAULT 3,
                kill_switch INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
            );

            CREATE TABLE IF NOT EXISTS autotrade_risk_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                reason TEXT NOT NULL,
                daily_realized_r REAL,
                loss_streak INTEGER,
                risk_multiplier REAL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_autotrade_risk_events_user_time
                ON autotrade_risk_events(telegram_id, created_at);
            """
        )


def _profile(telegram_id: int) -> dict[str, Any]:
    ensure_schema()
    now = datetime.now(timezone.utc).isoformat()
    with db.conn() as con:
        con.execute(
            """
            INSERT OR IGNORE INTO autotrade_risk_profiles(
                telegram_id,daily_loss_limit_r,dynamic_risk_enabled,
                min_risk_multiplier,max_loss_streak,kill_switch,updated_at
            ) VALUES(?,?,?,?,?,?,?)
            """,
            (
                int(telegram_id),
                DEFAULT_DAILY_LOSS_LIMIT_R,
                1,
                DEFAULT_MIN_RISK_MULTIPLIER,
                DEFAULT_MAX_LOSS_STREAK,
                0,
                now,
            ),
        )
        row = con.execute(
            "SELECT * FROM autotrade_risk_profiles WHERE telegram_id=?",
            (int(telegram_id),),
        ).fetchone()
    return dict(row) if row else {
        "telegram_id": int(telegram_id),
        "daily_loss_limit_r": DEFAULT_DAILY_LOSS_LIMIT_R,
        "dynamic_risk_enabled": 1,
        "min_risk_multiplier": DEFAULT_MIN_RISK_MULTIPLIER,
        "max_loss_streak": DEFAULT_MAX_LOSS_STREAK,
        "kill_switch": 0,
    }


def set_user_profile(
    telegram_id: int,
    *,
    daily_loss_limit_r: float | None = None,
    dynamic_risk_enabled: bool | None = None,
    min_risk_multiplier: float | None = None,
    max_loss_streak: int | None = None,
    kill_switch: bool | None = None,
) -> dict[str, Any]:
    current = _profile(int(telegram_id))
    limit = float(current["daily_loss_limit_r"] if daily_loss_limit_r is None else daily_loss_limit_r)
    min_mult = float(current["min_risk_multiplier"] if min_risk_multiplier is None else min_risk_multiplier)
    streak = int(current["max_loss_streak"] if max_loss_streak is None else max_loss_streak)
    dynamic = bool(current["dynamic_risk_enabled"]) if dynamic_risk_enabled is None else bool(dynamic_risk_enabled)
    kill = bool(current["kill_switch"]) if kill_switch is None else bool(kill_switch)

    if not 0.25 <= limit <= 20.0:
        raise ValueError("daily_loss_limit_r must be between 0.25 and 20 R")
    if not 0.10 <= min_mult <= 1.0:
        raise ValueError("min_risk_multiplier must be between 0.10 and 1.0")
    if not 1 <= streak <= 10:
        raise ValueError("max_loss_streak must be between 1 and 10")

    with db.conn() as con:
        con.execute(
            """
            UPDATE autotrade_risk_profiles
            SET daily_loss_limit_r=?,dynamic_risk_enabled=?,min_risk_multiplier=?,
                max_loss_streak=?,kill_switch=?,updated_at=?
            WHERE telegram_id=?
            """,
            (limit, 1 if dynamic else 0, min_mult, streak, 1 if kill else 0,
             datetime.now(timezone.utc).isoformat(), int(telegram_id)),
        )
    return _profile(int(telegram_id))


def global_kill_switch() -> bool:
    try:
        return _truthy(db.get_setting("autotrade_global_kill_switch", "0"))
    except Exception:
        return False


def set_global_kill_switch(enabled: bool) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with db.conn() as con:
        con.execute(
            """
            INSERT INTO app_settings(key,value,updated_at) VALUES(?,?,?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at
            """,
            ("autotrade_global_kill_switch", "1" if enabled else "0", now),
        )


def _r_expression() -> str:
    return (
        "CASE "
        "WHEN realized_r IS NOT NULL THEN realized_r "
        "WHEN COALESCE(risk_cash,0)>0 THEN "
        "  (COALESCE(profit,0)+COALESCE(commission,0)+COALESCE(swap,0))/risk_cash "
        "ELSE 0 END"
    )


def daily_realized_r(telegram_id: int, *, now: datetime | None = None) -> float:
    now = now or datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    expr = _r_expression()
    with db.conn() as con:
        row = con.execute(
            f"""
            SELECT COALESCE(SUM({expr}),0)
            FROM autotrade_trade_executions
            WHERE telegram_id=? AND UPPER(event_type)='CLOSE' AND created_at>=?
            """,
            (int(telegram_id), start),
        ).fetchone()
    return round(float(row[0] if row else 0.0), 4)


def consecutive_losses(telegram_id: int, *, limit: int = 20) -> int:
    expr = _r_expression()
    with db.conn() as con:
        rows = con.execute(
            f"""
            SELECT {expr} AS r_value
            FROM autotrade_trade_executions
            WHERE telegram_id=? AND UPPER(event_type)='CLOSE'
            ORDER BY created_at DESC,id DESC LIMIT ?
            """,
            (int(telegram_id), int(limit)),
        ).fetchall()
    streak = 0
    for row in rows:
        value = float(row["r_value"] or 0.0)
        if value < 0:
            streak += 1
        else:
            break
    return streak


def decision_for_metrics(
    *,
    daily_r: float,
    loss_streak: int,
    daily_limit_r: float = DEFAULT_DAILY_LOSS_LIMIT_R,
    dynamic_enabled: bool = True,
    min_multiplier: float = DEFAULT_MIN_RISK_MULTIPLIER,
    max_loss_streak: int = DEFAULT_MAX_LOSS_STREAK,
    global_kill: bool = False,
    user_kill: bool = False,
) -> RiskDecision:
    limit = max(0.25, float(daily_limit_r))
    minimum = min(1.0, max(0.10, float(min_multiplier)))

    if global_kill:
        return RiskDecision(False, "GLOBAL_KILL_SWITCH", daily_r, loss_streak, 0.0, limit,
                            dynamic_enabled, True, user_kill)
    if user_kill:
        return RiskDecision(False, "USER_KILL_SWITCH", daily_r, loss_streak, 0.0, limit,
                            dynamic_enabled, False, True)
    if daily_r <= -limit:
        return RiskDecision(False, "DAILY_LOSS_LIMIT", daily_r, loss_streak, 0.0, limit,
                            dynamic_enabled, False, False)
    if loss_streak >= int(max_loss_streak):
        return RiskDecision(False, "LOSS_STREAK_LIMIT", daily_r, loss_streak, 0.0, limit,
                            dynamic_enabled, False, False)

    multiplier = 1.0
    reason = "NORMAL"
    if dynamic_enabled:
        if daily_r <= -(limit * 0.75):
            multiplier = minimum
            reason = "DEFENSIVE_HIGH_DRAWDOWN"
        elif daily_r <= -(limit * 0.50):
            multiplier = max(minimum, 0.75)
            reason = "DEFENSIVE_DRAWDOWN"
        if loss_streak >= 2:
            multiplier = min(multiplier, max(minimum, 0.50))
            reason = "DEFENSIVE_LOSS_STREAK"

    return RiskDecision(True, reason, daily_r, loss_streak, round(multiplier, 4), limit,
                        dynamic_enabled, False, False)


def evaluate_user(telegram_id: int) -> RiskDecision:
    p = _profile(int(telegram_id))
    return decision_for_metrics(
        daily_r=daily_realized_r(int(telegram_id)),
        loss_streak=consecutive_losses(int(telegram_id)),
        daily_limit_r=float(p["daily_loss_limit_r"]),
        dynamic_enabled=bool(p["dynamic_risk_enabled"]),
        min_multiplier=float(p["min_risk_multiplier"]),
        max_loss_streak=int(p["max_loss_streak"]),
        global_kill=global_kill_switch(),
        user_kill=bool(p["kill_switch"]),
    )


def apply_dynamic_risk(payload: dict[str, Any], decision: RiskDecision) -> dict[str, Any]:
    item = dict(payload)
    mult = float(decision.risk_multiplier)
    if mult < 1.0:
        if item.get("risk_percent") is not None:
            item["risk_percent"] = round(float(item["risk_percent"]) * mult, 6)
        if item.get("lot_size") is not None:
            item["lot_size"] = round(float(item["lot_size"]) * mult, 6)
    item["risk_guard"] = decision.as_payload()
    return item


def install_risk_firewall() -> None:
    """Wrap AutoTrade signal polling before ``app.autotrade.api`` imports it."""
    global _INSTALLED
    if _INSTALLED:
        return

    original = service.active_signals

    def _protected_active_signals(
        license_key: str,
        account_number: str,
        *,
        after_id: int = 0,
        limit: int = 50,
    ) -> dict[str, Any]:
        data = original(license_key, account_number, after_id=after_id, limit=limit)
        auth = service._resolve_service_ea_auth(license_key, account_number)
        uid = int(auth["telegram_id"])
        decision = evaluate_user(uid)
        result = dict(data)
        result["risk_guard"] = decision.as_payload()
        if not decision.allowed:
            result["signals"] = []
            return result
        result["signals"] = [apply_dynamic_risk(dict(item), decision) for item in data.get("signals", [])]
        return result

    service.active_signals = _protected_active_signals
    _INSTALLED = True
