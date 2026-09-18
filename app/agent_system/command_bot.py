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
_allowed_user_id = ""


def _analysis_record(config: ShadowRunnerConfig, symbol: str, timeframe: str = "M5"):
    snapshot = build_mt5_snapshot(config.account, symbol)
    ict = assess_ict(snapshot, trigger_timeframe=timeframe)
    assessment = _assessment_summary(ict)
    trigger_rows = snapshot.timeframes.get(timeframe, ())
    recent = trigger_rows[-24:] if trigger_rows else ()
    return snapshot, assessment, {
        "symbol": snapshot.symbol,
        "snapshot_id": snapshot.snapshot_id,
        "final": "ANALYSIS",
        "direction": ict.direction.value,
        "bid": snapshot.bid,
        "ask": snapshot.ask,
        "analysis_timeframe": timeframe,
        "m5_recent_high": max((float(x["high"]) for x in recent), default=None),
        "m5_recent_low": min((float(x["low"]) for x in recent), default=None),
        "assessments": [assessment],
    }


@router.message(Command("whoami"))
async def whoami_command(message: Message):
    user_id = message.from_user.id if message.from_user else "-"
    await message.answer(f"User ID: {user_id}\nChat ID: {message.chat.id}")


async def _send_id(message: Message):
    user_id = message.from_user.id if message.from_user else "-"
    thread_id = message.message_thread_id if message.message_thread_id is not None else "-"
    chat_type = getattr(message.chat, "type", "-")
    await message.answer(
        f"Chat ID: {message.chat.id}\n"
        f"Topic / Thread ID: {thread_id}\n"
        f"User ID: {user_id}\n"
        f"Chat Type: {chat_type}"
    )


@router.message(Command("id"))
async def id_command(message: Message):
    await _send_id(message)


@router.channel_post(Command("id"))
async def id_channel_command(message: Message):
    await _send_id(message)


@router.message(Command("analysis"))
async def analysis_command(message: Message):
    if _config is None:
        return
    sender_id = str(message.from_user.id) if message.from_user else ""
    if not _allowed_user_id or sender_id != _allowed_user_id:
        await message.answer("این دستور فقط برای ادمین NEXUS فعال است. /whoami را ارسال کنید.")
        return
    parts = (message.text or "").split()[1:]
    supported_timeframes = {"M1", "M5", "M15", "H1", "D1"}
    symbol = "XAUUSD"
    timeframe = "M5"
    for raw in parts:
        value = raw.upper()
        if value in supported_timeframes:
            timeframe = value
        elif value in _config.symbols:
            symbol = value
        else:
            await message.answer("فرمت دستور نامعتبر است. مثال: /analysis M1 یا /analysis XAUUSD M5")
            return
    status = await message.answer(f"در حال ساخت آپدیت تازه {symbol} • {timeframe} از Snapshot متاتریدر…")
    try:
        snapshot, assessment, record = await asyncio.to_thread(_analysis_record, _config, symbol, timeframe)
        if timeframe not in snapshot.timeframes or len(snapshot.timeframes.get(timeframe, ())) < 20:
            raise ValueError(f"داده کافی {timeframe} در MT5 Market Feed موجود نیست")
        png = await asyncio.to_thread(render_ict_chart, snapshot, assessment, timeframe=timeframe)
        await message.answer_photo(BufferedInputFile(png, filename=f"nexus_{symbol}_ict.png"))
        await message.answer(format_hourly_analysis(record))
        await status.delete()
    except Exception as exc:
        await status.edit_text(f"آپدیت ساخته نشد: {type(exc).__name__}: {exc}")


async def run(account: str, symbols: tuple[str, ...]):
    global _config, _allowed_chat_id, _allowed_user_id
    token = os.getenv("NEXUS_AGENT_TEST_BOT_TOKEN", "").strip()
    _allowed_chat_id = os.getenv("NEXUS_AGENT_TEST_CHAT_ID", "").strip()
    _allowed_user_id = os.getenv("NEXUS_AGENT_COMMAND_USER_ID", "").strip()
    if not token:
        raise RuntimeError("NEXUS_AGENT_TEST_BOT_TOKEN is required")
    _config = ShadowRunnerConfig(account=account, symbols=symbols, journal_dir=Path("data/agent_shadow"))
    bot = Bot(token=token)
    dp = Dispatcher()
    dp.include_router(router)
    try:
        await dp.start_polling(bot, allowed_updates=["message", "channel_post"])
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
