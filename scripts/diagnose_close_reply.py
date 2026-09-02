from __future__ import annotations

"""Runtime diagnostics for missing NEXUS closed-position Telegram replies.

Safe to run on the deployed server. The script never prints BOT_TOKEN or the
admin token. It checks:
- effective FREE/VIP targets,
- Telegram bot identity and channel membership/post permission,
- signals that are CLOSED/CLOSING without a delivered CLOSE reply,
- recent CLOSE-related worker errors from logs/nexus.log.

Exit code is non-zero when Bot API/channel posting capability is not healthy,
so the same command can be used as a CI/runtime gate.
"""

import asyncio
import re
import sys
from pathlib import Path

# Running `python scripts/diagnose_close_reply.py` makes scripts/ sys.path[0].
# Add the repository root explicitly so `app` imports work identically on
# Windows servers and GitHub Actions runners.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aiogram import Bot
from aiogram.enums import ChatMemberStatus

from app.config import settings
from app import db


CLOSE_ACTIONS = {"CLOSE", "MT5_CLOSE"}


def _reply_state(signal_id: int) -> tuple[bool, bool]:
    free = vip = False
    for row in db.signal_updates(int(signal_id)):
        if str(row["action"] or "").upper() not in CLOSE_ACTIONS:
            continue
        free = free or row["free_message_id"] is not None
        vip = vip or row["vip_message_id"] is not None
    return free, vip


def _expected(destination: str) -> tuple[bool, bool]:
    dest = str(destination or "BOTH").upper()
    return dest in {"FREE", "BOTH"}, dest in {"VIP", "BOTH"}


async def _check_target(bot: Bot, label: str, target) -> bool:
    me = await bot.get_me()
    try:
        chat = await bot.get_chat(target)
        member = await bot.get_chat_member(target, me.id)
        status = member.status
        can_post = getattr(member, "can_post_messages", None)
        is_admin = status in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}
        permission_ok = bool(is_admin and (can_post is None or can_post))
        print(
            f"[{label}] target={target!r} chat_id={chat.id} title={getattr(chat, 'title', '')!r} "
            f"status={status} can_post_messages={can_post} permission_ok={permission_ok}"
        )
        return permission_ok
    except Exception as exc:
        print(f"[{label}] FAILED target={target!r}: {type(exc).__name__}: {exc}")
        return False


async def telegram_checks() -> bool:
    bot = Bot(settings.bot_token)
    try:
        me = await bot.get_me()
        print(f"BOT OK: id={me.id} username=@{me.username or ''}")
        print(f"FREE effective target: {settings.free_channel_target!r}")
        print(f"VIP effective target: {settings.vip_channel_id!r}")
        free_ok, vip_ok = await asyncio.gather(
            _check_target(bot, "FREE", settings.free_channel_target),
            _check_target(bot, "VIP", settings.vip_channel_id),
        )
        return bool(free_ok and vip_ok)
    except Exception as exc:
        print(f"BOT TOKEN/API FAILED: {type(exc).__name__}: {exc}")
        return False
    finally:
        await bot.session.close()


def database_checks() -> int:
    db.init_db()
    print("\nDB close-delivery audit:")
    with db.conn() as con:
        rows = con.execute(
            """SELECT * FROM signals
               WHERE status IN ('CLOSED','CLOSING')
               ORDER BY COALESCE(closed_at,created_at) DESC LIMIT 100"""
        ).fetchall()
    problems = 0
    for row in rows:
        free_done, vip_done = _reply_state(int(row["id"]))
        need_free, need_vip = _expected(str(row["destination"] or "BOTH"))
        missing = []
        if need_free and not free_done:
            missing.append("FREE")
        if need_vip and not vip_done:
            missing.append("VIP")
        if missing:
            problems += 1
            print(
                f"MISSING_REPLY signal={row['code']} id={row['id']} status={row['status']} "
                f"destination={row['destination']} missing={','.join(missing)} "
                f"anchor_free={row['free_message_id']} anchor_vip={row['vip_message_id']} "
                f"last_free={row['free_last_message_id']} last_vip={row['vip_last_message_id']}"
            )
    if not problems:
        print("No CLOSED/CLOSING signal with a missing required close reply was found in the last 100 rows.")
    return problems


def log_checks() -> None:
    path = ROOT / "logs" / "nexus.log"
    print(f"\nLog audit: {path}")
    if not path.exists():
        print("No runtime nexus.log is available in this workspace.")
        return
    patterns = re.compile(
        r"CLOSE|CLOSE_REPLY|MT5_EVENT|text result reply failed|SIGNAL_ANCHOR|Telegram|BadRequest|Forbidden|RetryAfter",
        re.IGNORECASE,
    )
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    hits = [line for line in lines if patterns.search(line)]
    for line in hits[-120:]:
        print(line)
    if not hits:
        print("No close/reply-related log lines found.")


async def _main() -> int:
    database_checks()
    log_checks()
    telegram_ok = await telegram_checks()
    if not telegram_ok:
        print("\nFAIL: Telegram bot/channel posting capability is not healthy.")
        return 2
    print("\nPASS: Telegram bot identity and FREE/VIP posting permissions are healthy.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
