from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, Message

from .agents.ict import assess_ict
from .chart_renderer import render_ict_chart
from .shadow_runner import ShadowRunnerConfig, _assessment_summary
from .snapshot_adapter import build_mt5_snapshot
from .telegram_reporter import format_hourly_analysis

router = Router()
_config: ShadowRunnerConfig | None = None
_allowed_chat_id = ""


def _analysis_record(config: ShadowRunnerConfig, symbol: str):
    snapshot = build_mt5_snapshot(config.account, symbol)
    ict = assess_ict(snapshot)
    assessment = _assessment_summary(ict)
    m5 = snapshot.timeframes.get("M5", ())
    recent = m5[-24:] if m5 else ()
    return snapshot, assessment, {
        "symbol": snapshot.symbol,
        "snapshot_id": snapshot.snapshot_id,
        "final": "ANALYSIS",
        "direction": ict.direction.value,
        "bid": snapshot.bid,
        "ask": snapshot.ask,
        "m5_recent_high": max((float(x["high"]) for x in recent), default=None),
        "m5_recent_low": min((float(x["low"]) for x in recent), default=None),
        "assessments": [assessment],
    }


@router.message(Command("analysis"))
async def analysis_command(message: Message):
    if _config is None:
        return
    if _allowed_chat_id and str(message.chat.id) != _allowed_chat_id:
        return
    parts = (message.text or "").split()
    symbol = parts[1].upper() if len(parts) > 1 else "XAUUSD"
    if symbol not in _config.symbols:
        await message.answer("نماد مجاز نیست. فعلاً: " + ", ".join(_config.symbols))
        return
    status = await message.answer(f"در حال ساخت آپدیت تازه {symbol} از Snapshot متاتریدر…")
    try:
        snapshot, assessment, record = await asyncio.to_thread(_analysis_record, _config, symbol)
        png = await asyncio.to_thread(render_ict_chart, snapshot, assessment)
        await message.answer_photo(BufferedInputFile(png, filename=f"nexus_{symbol}_ict.png"))
        await message.answer(format_hourly_analysis(record))
        await status.delete()
    except Exception as exc:
        await status.edit_text(f"آپدیت ساخته نشد: {type(exc).__name__}: {exc}")


async def run(account: str, symbols: tuple[str, ...]):
    global _config, _allowed_chat_id
    token = os.getenv("NEXUS_AGENT_TEST_BOT_TOKEN", "").strip()
    _allowed_chat_id = os.getenv("NEXUS_AGENT_TEST_CHAT_ID", "").strip()
    if not token:
        raise RuntimeError("NEXUS_AGENT_TEST_BOT_TOKEN is required")
    _config = ShadowRunnerConfig(account=account, symbols=symbols, journal_dir=Path("data/agent_shadow"))
    bot = Bot(token=token)
    dp = Dispatcher()
    dp.include_router(router)
    try:
        await dp.start_polling(bot, allowed_updates=["message"])
    finally:
        await bot.session.close()


def main():
    parser = argparse.ArgumentParser(description="NEXUS on-demand ICT Telegram analysis bot")
    parser.add_argument("--account", required=True)
    parser.add_argument("--symbols", default="XAUUSD")
    args = parser.parse_args()
    symbols = tuple(dict.fromkeys(x.strip().upper() for x in args.symbols.split(",") if x.strip()))
    asyncio.run(run(args.account, symbols))


if __name__ == "__main__":
    main()
