from __future__ import annotations


def risk_reward(entry: float, stop_loss: float, target: float, direction: str) -> float | None:
    risk = abs(entry - stop_loss)
    if risk <= 0:
        return None
    direction = direction.upper()
    reward = (target - entry) if direction in {"BUY", "LONG"} else (entry - target)
    if reward <= 0:
        return None
    return round(reward / risk, 2)


def forex_pip_size(symbol: str) -> float:
    """Canonical pip size for broker/MT5 reporting.

    XAUUSD is intentionally 0.1 (not 0.01); all close reporting paths use
    this single definition. XAGUSD remains 0.01 and JPY pairs remain 0.01.
    """
    normalized = symbol.upper().replace("/", "").replace("-", "")
    if normalized.startswith("XAUUSD"):
        return 0.1
    if normalized.startswith("XAGUSD") or "JPY" in normalized:
        return 0.01
    return 0.0001


def result_metric(market_type: str, symbol: str, direction: str, entry: float, exit_price: float, *, pip_size: float | None = None) -> tuple[float, str, str]:
    direction = direction.upper()
    delta = (exit_price - entry) if direction in {"BUY", "LONG"} else (entry - exit_price)
    if market_type.upper() in {"FOREX", "GOLD"}:
        size = float(pip_size) if pip_size is not None else forex_pip_size(symbol)
        if size <= 0:
            raise ValueError("pip_size must be positive")
        value = round(delta / size, 1)
        return value, "PIPS", f"{value:+g} Pips"
    value = round((delta / entry) * 100, 2) if entry else 0.0
    return value, "PERCENT", f"{value:+g}%"
