from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path
from typing import Any, Callable

from PIL import Image

from .. import db
from .broker_chart_fallback import ensure_broker_chart_asset

log = logging.getLogger("nexus.unified_signal_visual")

_STYLE_VERSION = "nexus-signal-canonical-v4"
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


def _row_value(row: Any, key: str, default: Any = None) -> Any:
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[key]
    except Exception:
        return default


def _authoritative_staged_chart(row: Any) -> str | None:
    """Return a real staged MT5 chart when it must outrank renderer fallback.

    WEB_ADMIN screenshots become authoritative only after the ChartAgent result
    endpoint has durably staged the image and changed publication_stage to
    CHART_RECEIVED. MT5_ADMIN may stage its own source screenshot directly, so an
    existing valid image asset from that issuer is authoritative as well.

    MarketFeed-rendered fallback assets never satisfy the WEB_ADMIN
    CHART_RECEIVED gate and therefore remain fallback-only.
    """
    signal_id = _signal_id(row)
    issuer = _issuer_type(row)
    if signal_id <= 0 or issuer != "MT5_ADMIN":
        return None

    asset = db.get_mt5_signal_publication_asset(signal_id)
    if not asset:
        return None

    path = Path(str(asset))
    try:
        if not path.is_file() or path.stat().st_size < 512:
            return None
        with path.open("rb") as handle:
            magic = handle.read(8)
    except OSError:
        return None

    if not (magic.startswith(b"\x89PNG\r\n\x1a\n") or magic.startswith(b"\xff\xd8\xff")):
        return None
    return str(path)


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
    """Use a real MT5 screenshot first and MarketFeed rendering only as fallback.

    The wrapper is additive and does not touch execution, receipts, Telegram
    routing or EA behavior. A successfully staged ChartAgent/MT5 source image is
    authoritative. Only when no such source image exists may the existing fresh
    MT5 MarketFeed renderer stage a fallback chart.
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
        visual_source = "EXISTING_PIPELINE"

        # Mini App / WEB_ADMIN has one publication authority: a deterministic
        # broker-truth render generated from the canonical DB signal snapshot.
        # ChartAgent screenshots are diagnostics only and can never override it.
        if issuer == "WEB_ADMIN" and signal_id > 0:
            broker_result = ensure_broker_chart_asset(canonical)
            if not broker_result.get("ok"):
                reason = str(broker_result.get("reason") or "canonical broker visual unavailable")
                try:
                    with db.conn() as con:
                        con.execute(
                            "UPDATE signals SET publication_stage='WAITING_FOR_VISUAL' "
                            "WHERE id=? AND UPPER(COALESCE(publication_stage,''))!='PUBLISHED'",
                            (signal_id,),
                        )
                    db.add_signal_event(
                        signal_id,
                        "SIGNAL_VISUAL_CANONICALIZE_FAILED",
                        actor_type="BACKEND",
                        actor_id=_row_value(canonical, "created_by"),
                        account_number=str(_row_value(canonical, "issuer_account", "") or ""),
                        correlation_id=str(_row_value(canonical, "code", "") or ""),
                        result="FAILED",
                        reason=reason[:1000],
                        payload={
                            "style_version": _STYLE_VERSION,
                            "issuer_type": issuer,
                            "source": "MT5_MARKET_FEED_CANONICAL",
                            "broker_result": broker_result,
                        },
                    )
                except Exception:
                    log.exception("failed recording WEB_ADMIN canonical visual failure signal_id=%s", signal_id)
                return {
                    "free_message_id": None,
                    "vip_message_id": None,
                    "errors": [f"VISUAL_GATE: {reason}"],
                    "published": False,
                    "complete": False,
                    "visual_style_version": _STYLE_VERSION,
                    "visual_source": "MT5_MARKET_FEED_CANONICAL",
                    "visual_retryable": True,
                }

            visual_source = "MT5_MARKET_FEED_CANONICAL"
            chart_base64 = None
            try:
                with db.conn() as con:
                    con.execute(
                        "UPDATE signals SET publication_stage='CANONICAL_VISUAL_READY' "
                        "WHERE id=? AND UPPER(COALESCE(publication_stage,''))!='PUBLISHED'",
                        (signal_id,),
                    )
                db.add_signal_event(
                    signal_id,
                    "SIGNAL_VISUAL_CANONICALIZED",
                    actor_type="BACKEND",
                    actor_id=_row_value(canonical, "created_by"),
                    account_number=str(_row_value(canonical, "issuer_account", "") or ""),
                    correlation_id=str(_row_value(canonical, "code", "") or ""),
                    payload={
                        "style_version": _STYLE_VERSION,
                        "issuer_type": issuer,
                        "source": visual_source,
                        "file_path": broker_result.get("file_path"),
                        "signal_visual_fingerprint": broker_result.get("fingerprint"),
                        "image_sha256": broker_result.get("image_sha256"),
                        "age_seconds": broker_result.get("age_seconds"),
                        "anchor_applied": broker_result.get("anchor_applied"),
                        "anchor_bar_time": broker_result.get("anchor_bar_time"),
                        "anchor_field": broker_result.get("anchor_field"),
                    },
                )
            except Exception:
                log.exception("failed recording WEB_ADMIN canonical visual event signal_id=%s", signal_id)

        else:
            authoritative_path = _authoritative_staged_chart(canonical)
            if authoritative_path:
                visual_source = "MT5_SOURCE_SCREENSHOT"
                try:
                    db.add_signal_event(
                        signal_id,
                        "SIGNAL_VISUAL_CANONICALIZED",
                        actor_type="BACKEND",
                        actor_id=_row_value(canonical, "created_by"),
                        account_number=str(_row_value(canonical, "issuer_account", "") or ""),
                        correlation_id=str(_row_value(canonical, "code", "") or ""),
                        payload={
                            "style_version": _STYLE_VERSION,
                            "issuer_type": issuer,
                            "source": visual_source,
                            "file_path": authoritative_path,
                            "authoritative_mt5_screenshot": True,
                        },
                    )
                except Exception:
                    log.exception("failed recording MT5 source visual event signal_id=%s", signal_id)
            elif issuer in _SUPPORTED_ISSUERS and signal_id > 0:
                broker_result = ensure_broker_chart_asset(canonical)
                if broker_result.get("ok"):
                    chart_base64 = None
                    visual_source = "MT5_MARKET_FEED_FALLBACK"
                else:
                    try:
                        db.add_signal_event(
                            signal_id,
                            "SIGNAL_VISUAL_CANONICALIZE_FAILED",
                            actor_type="BACKEND",
                            actor_id=_row_value(canonical, "created_by"),
                            account_number=str(_row_value(canonical, "issuer_account", "") or ""),
                            correlation_id=str(_row_value(canonical, "code", "") or ""),
                            result="FAILED",
                            reason=str(broker_result.get("reason") or "canonical renderer unavailable")[:1000],
                            payload={
                                "style_version": _STYLE_VERSION,
                                "issuer_type": issuer,
                                "source": "MT5_MARKET_FEED_FALLBACK",
                            },
                        )
                    except Exception:
                        log.exception("failed recording fallback visual failure signal_id=%s", signal_id)

        result = await original_publish(
            canonical,
            chart_base64,
            allow_without_chart=allow_without_chart,
        )
        if isinstance(result, dict):
            result["visual_style_version"] = _STYLE_VERSION
            result["visual_source"] = visual_source
            if broker_result:
                result["visual_fingerprint"] = broker_result.get("fingerprint")
        return result

    api_mod._publish_mt5_admin_signal_async = unified_publish
    app.state.nexus_unified_signal_visual_v28 = True
