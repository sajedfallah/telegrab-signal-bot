from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path
from typing import Any, Callable

from PIL import Image

from .. import db
from .broker_chart_fallback import ensure_broker_chart_asset

log = logging.getLogger("nexus.unified_signal_visual")

_STYLE_VERSION = "nexus-signal-minimal-v7"
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
    """Return a staged source screenshot only for MT5_ADMIN compatibility.

    WEB_ADMIN/Mini App screenshots are never publication authority in V37.
    Their Telegram artwork is always regenerated from fresh MT5 MarketFeed
    candles plus the canonical stored signal snapshot.
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
    """Normalize only a real canonical publication image.

    V38 removes the historical blank-image fallback. If the canonical broker
    visual is missing, corrupt, or unsafe, publication must fail closed and be
    retried later. Telegram must never receive a synthetic blank chart.
    """
    if not chart_bytes:
        raise ValueError("canonical publication image is missing")

    try:
        with Image.open(BytesIO(chart_bytes)) as source:
            source.verify()
        with Image.open(BytesIO(chart_bytes)) as source:
            image = source.convert("RGB")
    except Exception as exc:
        raise ValueError("canonical publication image is invalid") from exc

    if image.width < 1000 or image.height < 560 or image.width * image.height > 20_000_000:
        raise ValueError(f"unsafe canonical publication dimensions: {image.size}")

    if image.size != (1600, 900):
        image = image.resize((1600, 900), Image.Resampling.LANCZOS)

    out = BytesIO()
    image.save(out, format="PNG", optimize=True)
    raw = out.getvalue()
    if len(raw) < 10_000:
        raise ValueError("canonical publication image is suspiciously small")
    return raw


def install_unified_signal_visual(app) -> None:
    """Compatibility wrapper for V45 text-only Telegram signal publication.

    Signal images are intentionally disabled for both WEB_ADMIN (Mini App) and
    MT5_ADMIN issuance. The wrapper remains installed so existing runtime import
    order and publisher chaining stay stable, but it never stages, renders, or
    normalizes chart artwork.
    """
    if getattr(app.state, "nexus_unified_signal_visual_v37", False):
        return

    from . import api as api_mod

    original_publish: Callable[..., Any] = api_mod._publish_mt5_admin_signal_async

    async def unified_publish(
        row,
        chart_base64: str | None = None,
        *,
        allow_without_chart: bool = False,
    ) -> dict:
        signal_id = _signal_id(row)
        canonical = db.get_signal(signal_id) if signal_id > 0 else None
        canonical = canonical or row
        issuer = _issuer_type(canonical)

        # V45: all authority signals are Telegram text flash cards. Any image
        # supplied by legacy MT5/ChartAgent callers is ignored.
        result = await original_publish(
            canonical,
            None,
            allow_without_chart=True,
        )
        if isinstance(result, dict) and issuer in _SUPPORTED_ISSUERS:
            result["visual_style_version"] = "disabled"
            result["visual_source"] = "TEXT_ONLY"
            result["publication_mode"] = "TEXT_ONLY"
        return result

    api_mod._publish_mt5_admin_signal_async = unified_publish
    app.state.nexus_unified_signal_visual_v37 = True

