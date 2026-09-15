from __future__ import annotations

import argparse
import asyncio
import hashlib
import html
import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import BufferedInputFile

from app import db
from app.autotrade.broker_chart_fallback import _STYLE_VERSION, _load_series, _render_chart
from app.config import settings


def _value(row, key: str, default=None):
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[key]
    except Exception:
        return default


def _build_preview(signal) -> tuple[bytes, dict]:
    candles, meta = _load_series(signal)
    if not candles:
        raise RuntimeError(f"fresh MT5 MarketFeed unavailable: {meta.get('reason')}")

    signal_id = int(_value(signal, "id", 0) or 0)
    targets = [float(row["price"]) for row in db.get_signal_targets(signal_id)]
    raw = _render_chart(signal, candles, meta, targets)
    if not raw.startswith(b"\x89PNG\r\n\x1a\n") or len(raw) < 10_000:
        raise RuntimeError("renderer returned an invalid PNG")
    return raw, meta


def _target(channel: str):
    channel = channel.upper()
    if channel == "VIP":
        return settings.vip_channel_id
    if channel == "FREE":
        return settings.free_channel_target
    raise ValueError("channel must be VIP or FREE")


async def _send(signal, raw: bytes, meta: dict, channel: str) -> dict:
    code = str(_value(signal, "code", "NEXUS") or "NEXUS")
    symbol = str(_value(signal, "symbol", "") or "").upper()
    timeframe = str(_value(signal, "timeframe", "") or "").upper()
    caption = (
        "🧪 <b>NEXUS VISUAL PREVIEW</b>\n"
        "<b>TEST ONLY • NO TRADE ACTION</b>\n"
        f"<code>{html.escape(code)}</code> • {html.escape(symbol)} • {html.escape(timeframe)}"
    )

    async with Bot(settings.bot_token) as bot:
        message = await bot.send_photo(
            chat_id=_target(channel),
            photo=BufferedInputFile(raw, filename=f"{code}_visual_preview.png"),
            caption=caption,
            parse_mode=ParseMode.HTML,
        )

    return {
        "ok": True,
        "channel": channel.upper(),
        "message_id": int(message.message_id),
        "signal_code": code,
        "style_version": _STYLE_VERSION,
        "visual_source": "MT5_MARKET_FEED",
        "broker_symbol": meta.get("broker_symbol"),
        "timeframe": meta.get("timeframe"),
        "age_seconds": meta.get("age_seconds"),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "production_signal_anchor_untouched": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render and optionally send a standalone NEXUS signal visual preview without touching publication anchors."
    )
    parser.add_argument("--code", required=True, help="Existing signal code, for example NX-55")
    parser.add_argument("--channel", choices=("VIP", "FREE"), default="VIP")
    parser.add_argument(
        "--send",
        action="store_true",
        help="Actually send the preview. Without this flag the command only renders and reports metadata.",
    )
    args = parser.parse_args()

    signal = db.get_signal_by_code(str(args.code).strip())
    if not signal:
        raise SystemExit(f"signal not found: {args.code}")

    raw, meta = _build_preview(signal)
    dry = {
        "ok": True,
        "sent": False,
        "signal_code": str(_value(signal, "code", "") or ""),
        "style_version": _STYLE_VERSION,
        "visual_source": "MT5_MARKET_FEED",
        "broker_symbol": meta.get("broker_symbol"),
        "timeframe": meta.get("timeframe"),
        "age_seconds": meta.get("age_seconds"),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "production_signal_anchor_untouched": True,
    }

    if not args.send:
        print("VISUAL_PREVIEW_DRY_RUN:", json.dumps(dry, ensure_ascii=False))
        return 0

    result = asyncio.run(_send(signal, raw, meta, args.channel))
    result["sent"] = True
    print("VISUAL_PREVIEW_SENT:", json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
