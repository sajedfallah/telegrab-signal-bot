from __future__ import annotations

from typing import Any, Mapping

from .contracts import MarketSnapshot
from .fast_scalp import FastScalpAssessment, FastScalpState, build_fast_scalp_signal


def build_shadow_scenarios(snapshot: MarketSnapshot, timeframe: str, fast: FastScalpAssessment | None = None) -> dict[str, Any]:
    """Evidence-backed WATCH plans. Only confirmed M1 engine may supply numeric executable fields."""
    rows = snapshot.timeframes.get(timeframe, ())
    state = "WAIT"
    reasons: list[str] = []
    if snapshot.data_freshness_ms > 30_000 or snapshot.missing_data or snapshot.bid is None or snapshot.ask is None:
        reasons.append("missing_or_stale_market_data")
    if len(rows) < 20:
        reasons.append("insufficient_trigger_candles")
    levels: dict[str, float] = {}
    if not reasons:
        recent = rows[-24:]
        levels = {"sell_side_reference": min(float(r["low"]) for r in recent),
                  "buy_side_reference": max(float(r["high"]) for r in recent)}
        state = "WATCH"
    result: dict[str, Any] = {
        "schema_version": "2.0", "snapshot_id": snapshot.snapshot_id,
        "symbol": snapshot.symbol, "timeframe": timeframe, "status": state,
        "reference_levels": levels,
        "long": {"sweep": "SELL_SIDE", "mss": "BULLISH", "required": ["sell-side sweep and reclaim", "bullish MSS and displacement", "new directional FVG after MSS", "retest of that FVG"]},
        "short": {"sweep": "BUY_SIDE", "mss": "BEARISH", "required": ["buy-side sweep and reclaim", "bearish MSS and displacement", "new directional FVG after MSS", "retest of that FVG"]},
        "entry": None, "stop_loss": None, "take_profits": [], "rr": None,
        "blocks": reasons, "execution_allowed": False,
    }
    if timeframe == "M1" and fast is not None:
        result["fast_scalp_state"] = fast.state.value
        result["poi"] = list(fast.poi) if fast.poi else None
        result["active_entry_zone"] = list(fast.entry_zone) if fast.entry_zone else None
        result["sweep_anchor"] = fast.sweep_anchor
        result["blocks"].extend(fast.blocks)
        if not reasons and fast.state == FastScalpState.ENTRY_READY:
            plan, blocks = build_fast_scalp_signal(snapshot, fast)
            if plan is not None:
                result.update(status="STRUCTURE_CONFIRMED_SHADOW", entry=plan.entry,
                              stop_loss=plan.stop_loss, take_profits=list(plan.take_profits), rr=plan.rr,
                              confirmed_direction=plan.direction.value,
                              active_entry_zone=[plan.entry_low, plan.entry_high])
            else:
                result["blocks"].extend(blocks)
    return result


def format_shadow_scenarios(data: Mapping[str, Any]) -> str:
    levels = data.get("reference_levels") or {}
    lines = ["🎯 NEXUS Conditional Setup V2 (Shadow)",
             f"وضعیت: {data['status']}", "","🟢 سناریوی Long:",
             f"• مرجع نقدینگی پایین: {levels.get('sell_side_reference', 'ناموجود')}",
             "• ابتدا برداشت نقدینگی فروشندگان و بازگشت به محدوده، سپس MSS/Displacement صعودی و FVG جدید و Retest آن.",
             "🔴 سناریوی Short:",
             f"• مرجع نقدینگی بالا: {levels.get('buy_side_reference', 'ناموجود')}",
             "• ابتدا برداشت نقدینگی خریداران و بازگشت به محدوده، سپس MSS/Displacement نزولی و FVG جدید و Retest آن."]
    if data.get("poi"):
        lines.append(f"• POI تایم بالاتر: {data['poi'][0]:g} تا {data['poi'][1]:g} (هنوز مجوز ورود نیست)")
    if data.get("fast_scalp_state"):
        lines.append(f"• مرحله Fast Scalp: {data['fast_scalp_state']}")
    if data.get("entry") is not None:
        lines.extend(["",f"📐 ساختار تأییدشده Shadow: {data['confirmed_direction']}",
                      f"Entry: {data['entry']:g}",f"SL: {data['stop_loss']:g}"])
        lines.extend(f"TP{i}: {target:g}" for i,target in enumerate(data["take_profits"],1))
        lines.append(f"RR (TP1): {data['rr']:.2f}")
    else:
        lines.append("• Entry / SL / TP / RR: در انتظار تشکیل و تأیید واقعی ستاپ؛ عدد فرضی صادر نمی‌شود.")
    if data.get("blocks"):
        lines.append("• شروط تکمیل‌نشده: " + ", ".join(str(s) for s in data["blocks"][:6]))
    lines.append("⛔ صرفاً ارزیابی Shadow؛ مجوز معامله واقعی صادر نشده است.")
    return "\n".join(lines)
