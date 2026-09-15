from __future__ import annotations

import logging
from io import BytesIO
from typing import Any, Callable

from PIL import Image

from .. import db
from .broker_chart_fallback import ensure_broker_chart_asset

log = logging.getLogger("nexus.unified_signal_visual")

_STYLE_VERSION = "nexus-clean-signal-v3"
_SUPPORTED_ISSUERS = {"MT5_ADMIN", "WEB_ADMIN"}


def _issuer_type(row: Any) -> str:
    if isinstance(row, dict):
        return str(row.get("issuer_type") or "").strip().upper()
    try:
        return str(row["issuer_type"] or "").strip().upper()
    except Exception:
        return ""


def _signal_id(row: Any) -> int:
    if isinstance(row, dict):
        return int(row.get("id") or 0)
    try:
        return int(row["id"] or 0)
    except Exception:
        return 0


def _clean_publication_image(chart_bytes: bytes | None, signal: dict) -> bytes:
    """Publication renderer contract: the staged chart is already final artwork.

    The old renderer added a header rail, large logo panel and a numeric footer.
    Those decorations intentionally disappear. A valid staged PNG is normalized
    to RGB/1280x720 and returned without adding any extra text or panels. Level
    labels/prices, when present, are already part of the canonical staged chart.
    """
    if chart_bytes:
        try:
            with Image.open(BytesIO(chart_bytes)) as source:
                image = source.convert("RGB")
            if image.size != (1280, 720):
                image = image.resize((1280, 720), Image.Resampling.LANCZOS)
            out = BytesIO()
            image.save(out, format="PNG", optimize=True)
            return out.getvalue()
        except Exception:
            log.exception("failed normalizing staged publication chart")

    # Last-resort reliability image. It deliberately contains no synthetic
    # prices, no trade numbers and no marketing copy.
    image = Image.new("RGB", (1280, 720), (5, 16, 29))
    out = BytesIO()
    image.save(out, format="PNG", optimize=True)
    return out.getvalue()


def install_unified_signal_visual(app) -> None:
    """Make MT5 Admin and Mini App signals use the same canonical chart renderer.

    The wrapper is additive and does not touch execution, receipts, Telegram
    routing or EA behavior. Immediately before publication/repair it stages the
    approved broker-truth image from the fresh MT5 MarketFeed. Because the core
    publisher imports build_publication_signal_image dynamically, replacing that
    renderer here also prevents the old decorative frame/footer from returning.
    """
    if getattr(app.state, "nexus_unified_signal_visual_v28", False):
        return

    from . import api as api_mod
    from ..signals import card_generator

    card_generator.build_publication_signal_image = _clean_publication_image

    original_publish: Callable[..., Any] = api_mod._publish_mt5_admin_signal_async

    async def unified_publish(row, chart_base64: str | None = None, *, allow_without_chart: bool = False) -> dict:
        signal_id = _signal_id(row)
        canonical = db.get_signal(signal_id) if signal_id > 0 else None
        canonical = canonical or row
        issuer = _issuer_type(canonical)

        broker_result: dict[str, Any] | None = None
        if issuer in _SUPPORTED_ISSUERS and signal_id > 0:
            broker_result = ensure_broker_chart_asset(canonical)
            if broker_result.get("ok"):
                # The broker renderer has staged the final PNG in the canonical
                # DB asset slot. Ignore source-specific screenshot bytes so MT5
                # and Mini App publication paths cannot diverge visually.
                chart_base64 = None
                try:
                    db.add_signal_event(
                        signal_id,
                        "SIGNAL_VISUAL_CANONICALIZED",
                        actor_type="BACKEND",
                        actor_id=canonical["created_by"],
                        account_number=str(canonical["issuer_account"] or ""),
                        correlation_id=str(canonical["code"]),
                        payload={
                            "style_version": _STYLE_VERSION,
                            "issuer_type": issuer,
                            "source": "MT5_MARKET_FEED",
                            "file_path": broker_result.get("file_path"),
                            "age_seconds": broker_result.get("age_seconds"),
                            "anchor_applied": broker_result.get("anchor_applied"),
                            "anchor_bar_time": broker_result.get("anchor_bar_time"),
                            "anchor_field": broker_result.get("anchor_field"),
                        },
                    )
                except Exception:
                    log.exception("failed recording canonical visual event signal_id=%s", signal_id)
            else:
                # Reliability stays fail-open for the visual layer only: if the
                # feed is temporarily unavailable, the existing chart pipeline
                # may still publish. Execution/trading gates remain untouched.
                try:
                    db.add_signal_event(
                        signal_id,
                        "SIGNAL_VISUAL_CANONICALIZE_FAILED",
                        actor_type="BACKEND",
                        actor_id=canonical["created_by"],
                        account_number=str(canonical["issuer_account"] or ""),
                        correlation_id=str(canonical["code"]),
                        result="FAILED",
                        reason=str(broker_result.get("reason") or "canonical renderer unavailable")[:1000],
                        payload={
                            "style_version": _STYLE_VERSION,
                            "issuer_type": issuer,
                            "source": "MT5_MARKET_FEED",
                        },
                    )
                except Exception:
                    log.exception("failed recording canonical visual failure signal_id=%s", signal_id)

        result = await original_publish(
            canonical,
            chart_base64,
            allow_without_chart=allow_without_chart,
        )
        if isinstance(result, dict):
            result["visual_style_version"] = _STYLE_VERSION
            result["visual_source"] = "MT5_MARKET_FEED" if broker_result and broker_result.get("ok") else "EXISTING_PIPELINE"
        return result

    api_mod._publish_mt5_admin_signal_async = unified_publish
    app.state.nexus_unified_signal_visual_v28 = True
