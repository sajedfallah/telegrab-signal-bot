from __future__ import annotations

from typing import Any, Iterable


def _keys(row: Any) -> set[str]:
    try:
        return set(row.keys())
    except Exception:
        return set(row) if isinstance(row, dict) else set()


def _get(row: Any, key: str, default: Any = None) -> Any:
    if key not in _keys(row):
        return default
    try:
        value = row[key]
    except Exception:
        return default
    return default if value is None else value


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def canonical_signal(row: Any, targets: Iterable[Any] = ()) -> dict[str, Any]:
    """Build the presentation-neutral NEXUS signal contract from persisted truth.

    No value is inferred from market conditions. Optional or missing fields stay
    None so presentation layers can omit them instead of fabricating data.
    """
    target_items: list[dict[str, Any]] = []
    for item in targets:
        no = _get(item, "target_no")
        price = _get(item, "price")
        if no is None or price is None:
            continue
        target_items.append({"target_no": int(no), "price": float(price)})
    target_items.sort(key=lambda item: item["target_no"])

    volume_mode = str(_get(row, "volume_mode", "") or "").upper() or None
    source = str(_get(row, "issuer_type", "") or "").upper() or None
    status = str(_get(row, "status", "") or "").upper() or None
    opened_at = _get(row, "opened_at") or _get(row, "issued_at")
    return {
        "signal_id": int(_get(row, "id", 0)) or None,
        "code": str(_get(row, "code", "") or "") or None,
        "market": str(_get(row, "market_type", "") or "").upper() or None,
        "symbol": str(_get(row, "symbol", "") or "").upper() or None,
        "direction": str(_get(row, "direction", "") or "").upper() or None,
        "timeframe": str(_get(row, "timeframe", "") or "").upper() or None,
        "order_type": str(_get(row, "order_type", "") or "").upper() or None,
        "entry_price": _optional_float(_get(row, "entry_price")),
        "stop_loss": _optional_float(_get(row, "stop_loss")),
        "take_profit_levels": target_items,
        "volume_mode": volume_mode,
        "volume": _optional_float(_get(row, "lot_size")) if volume_mode == "FIXED" else None,
        "risk_percent": _optional_float(_get(row, "risk_percent")) if volume_mode != "FIXED" else None,
        "risk_reward": _optional_float(_get(row, "rr_ratio")),
        "trailing_code": str(_get(row, "trailing_code", "") or "") or None,
        "status": status,
        "lifecycle_state": status,
        "opened_at": str(opened_at) if opened_at else None,
        "closed_at": str(_get(row, "closed_at")) if _get(row, "closed_at") else None,
        "exit_price": _optional_float(_get(row, "exit_price")),
        "realized_pnl": _optional_float(_get(row, "result_value")),
        "realized_pnl_unit": str(_get(row, "result_unit", "") or "") or None,
        "source": source,
        "source_account": str(_get(row, "issuer_account", "") or "") or None,
        "destination": str(_get(row, "destination", "") or "").upper() or None,
        "created_at": str(_get(row, "created_at")) if _get(row, "created_at") else None,
        "stop_limit_price": _optional_float(_get(row, "stop_limit_price")),
        "limit_activated_at": str(_get(row, "limit_activated_at")) if _get(row, "limit_activated_at") else None,
        "leverage": _optional_float(_get(row, "leverage")),
        "max_entry_deviation_pct": _optional_float(_get(row, "max_entry_deviation_pct")),
        "max_entry_deviation_abs": _optional_float(_get(row, "max_entry_deviation_abs")),
        "signal_uuid": str(_get(row, "signal_uuid", "") or "") or None,
        "revision": int(_get(row, "revision", 0) or 0) or None,
    }


def to_mt5_payload(contract: dict[str, Any], *, trailing_config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compatibility adapter for the established Expert wire contract."""
    required = ("signal_id", "code", "symbol", "direction", "timeframe", "order_type", "entry_price", "stop_loss")
    missing = [name for name in required if contract.get(name) in (None, "")]
    if missing:
        raise ValueError("canonical signal missing required MT5 fields: " + ", ".join(missing))

    targets = {int(item["target_no"]): float(item["price"]) for item in contract.get("take_profit_levels", [])}
    payload: dict[str, Any] = {
        "id": int(contract["signal_id"]),
        "signal_id": str(contract["code"]),
        "market": contract.get("market"),
        "symbol": str(contract["symbol"]),
        "timeframe": str(contract["timeframe"]),
        "direction": str(contract["direction"]),
        "entry": float(contract["entry_price"]),
        "sl": float(contract["stop_loss"]),
        "targets": [targets[k] for k in sorted(targets)],
        "risk_percent": contract.get("risk_percent"),
        "volume_mode": contract.get("volume_mode"),
        "lot_size": contract.get("volume"),
        "leverage": contract.get("leverage"),
        "trailing_code": contract.get("trailing_code") or "",
        "trailing_config": trailing_config,
        "max_entry_deviation_pct": contract.get("max_entry_deviation_pct"),
        "max_entry_deviation_abs": contract.get("max_entry_deviation_abs"),
        "order_type": str(contract["order_type"]),
        "stop_limit_price": contract.get("stop_limit_price"),
        "limit_activated_at": contract.get("limit_activated_at"),
        "status": contract.get("status"),
        "created_at": contract.get("created_at"),
        "destination": contract.get("destination"),
        "signal_uuid": contract.get("signal_uuid") or "",
        "revision": contract.get("revision") or 1,
        "issuer_type": contract.get("source") or "",
        "issuer_account": contract.get("source_account") or "",
        "issued_at": contract.get("opened_at") or "",
    }
    for number in range(1, 11):
        payload[f"tp{number}"] = targets.get(number)
    return payload
