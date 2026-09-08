from __future__ import annotations

import asyncio
import base64
import logging
import os
import re
from dataclasses import dataclass
from io import BytesIO
from typing import Iterable

import httpx
from aiogram import Bot, F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Message,
    ReplyParameters,
)

from . import db
from .config import settings
from .content.settings import content_settings

log = logging.getLogger("nexus-analysis-center")
router = Router(name="nexus-analysis-center")


_TRUE = {"1", "true", "yes", "on"}
_PRESET_SYMBOLS = ("XAUUSD", "BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "BNBUSD")
_SESSION_LOCKS: dict[int, asyncio.Lock] = {}
_SESSION_LOCKS_GUARD = asyncio.Lock()


@dataclass(frozen=True)
class AnalysisSettings:
    target_chat_id: int | str | None
    target_thread_id: int | None
    ai_api_key: str
    ai_base_url: str
    ai_model: str
    ai_timeout: float
    max_caption_chars: int
    history_limit: int
    enabled: bool


def _parse_chat_id(raw: str) -> int | str | None:
    value = (raw or "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return value


def _parse_optional_int(raw: str) -> int | None:
    value = (raw or "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def load_analysis_settings() -> AnalysisSettings:
    target = _parse_chat_id(os.getenv("ANALYSIS_TARGET_CHAT_ID", ""))
    api_key = os.getenv("ANALYSIS_AI_API_KEY", content_settings.ai_api_key).strip()
    base_url = os.getenv("ANALYSIS_AI_BASE_URL", content_settings.ai_base_url).strip().rstrip("/")
    model = os.getenv("ANALYSIS_AI_MODEL", content_settings.text_model).strip()
    enabled_raw = os.getenv("ANALYSIS_CENTER_ENABLED", "true").strip().lower()
    return AnalysisSettings(
        target_chat_id=target,
        target_thread_id=_parse_optional_int(os.getenv("ANALYSIS_TARGET_THREAD_ID", "")),
        ai_api_key=api_key,
        ai_base_url=base_url,
        ai_model=model,
        ai_timeout=max(15.0, float(os.getenv("ANALYSIS_AI_TIMEOUT", "60"))),
        max_caption_chars=max(500, min(1000, int(os.getenv("ANALYSIS_MAX_CAPTION_CHARS", "950")))),
        history_limit=max(1, min(12, int(os.getenv("ANALYSIS_HISTORY_LIMIT", "6")))),
        enabled=enabled_raw in _TRUE,
    )


analysis_settings = load_analysis_settings()


class AnalysisFlow(StatesGroup):
    waiting_h1 = State()
    waiting_m15 = State()
    waiting_update = State()
    waiting_custom_symbol = State()


def is_admin(user_id: int) -> bool:
    return int(user_id) in settings.admin_ids


def _kb(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=data) for label, data in row]
            for row in rows
        ]
    )


def _back_rows() -> list[list[tuple[str, str]]]:
    return [[("⬅️ بازگشت به پنل مدیریت", "admin")]]


def analysis_center_menu() -> InlineKeyboardMarkup:
    return _kb([
        [("➕ تحلیل جدید", "analysis:new"), ("🔄 آپدیت تحلیل", "analysis:update")],
        [("📂 تحلیل‌های فعال", "analysis:active"), ("✅ پایان تحلیل", "analysis:close")],
        *_back_rows(),
    ])


def symbol_menu() -> InlineKeyboardMarkup:
    rows: list[list[tuple[str, str]]] = []
    for index in range(0, len(_PRESET_SYMBOLS), 2):
        rows.append([
            (symbol, f"analysis:new:{symbol}")
            for symbol in _PRESET_SYMBOLS[index:index + 2]
        ])
    rows.append([("✍️ نماد دیگر", "analysis:new:CUSTOM")])
    rows.append([("⬅️ بازگشت", "analysis_center")])
    return _kb(rows)


def _session_menu(rows_data: Iterable, action: str) -> InlineKeyboardMarkup:
    rows: list[list[tuple[str, str]]] = []
    for row in rows_data:
        rows.append([(f"{row['symbol']}  •  #{row['id']}", f"analysis:{action}:{row['id']}")])
    if not rows:
        rows.append([("— تحلیل فعالی وجود ندارد —", "analysis:noop")])
    rows.append([("⬅️ بازگشت", "analysis_center")])
    return _kb(rows)


def _safe_symbol(raw: str) -> str | None:
    value = re.sub(r"[^A-Za-z0-9._/-]", "", (raw or "").upper().strip())
    if not value or len(value) > 20:
        return None
    return value.replace("/", "").replace("-", "")


def init_analysis_db() -> None:
    with db.conn() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS analysis_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                admin_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                root_chat_id TEXT,
                root_message_id INTEGER,
                h1_file_id TEXT NOT NULL,
                m15_file_id TEXT NOT NULL,
                initial_analysis TEXT NOT NULL,
                created_at TEXT NOT NULL,
                closed_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_analysis_sessions_status_symbol
                ON analysis_sessions(status, symbol, created_at DESC);

            CREATE UNIQUE INDEX IF NOT EXISTS uq_analysis_active_symbol
                ON analysis_sessions(symbol)
                WHERE status = 'ACTIVE';

            CREATE TABLE IF NOT EXISTS analysis_updates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                update_no INTEGER NOT NULL,
                image_file_id TEXT NOT NULL,
                analysis_text TEXT NOT NULL,
                telegram_message_id INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES analysis_sessions(id) ON DELETE CASCADE,
                UNIQUE(session_id, update_no)
            );

            CREATE INDEX IF NOT EXISTS idx_analysis_updates_session
                ON analysis_updates(session_id, update_no DESC);
            """
        )


def list_active_sessions():
    with db.conn() as con:
        return con.execute(
            "SELECT * FROM analysis_sessions WHERE status='ACTIVE' ORDER BY created_at DESC"
        ).fetchall()


def get_active_session(session_id: int):
    with db.conn() as con:
        return con.execute(
            "SELECT * FROM analysis_sessions WHERE id=? AND status='ACTIVE'",
            (int(session_id),),
        ).fetchone()


def get_active_session_by_symbol(symbol: str):
    with db.conn() as con:
        return con.execute(
            "SELECT * FROM analysis_sessions WHERE symbol=? AND status='ACTIVE' LIMIT 1",
            (symbol,),
        ).fetchone()


def create_active_session(
    *,
    symbol: str,
    admin_id: int,
    root_chat_id: int | str,
    root_message_id: int,
    h1_file_id: str,
    m15_file_id: str,
    initial_analysis: str,
) -> int:
    with db.conn() as con:
        cur = con.execute(
            """
            INSERT INTO analysis_sessions(
                symbol, admin_id, status, root_chat_id, root_message_id,
                h1_file_id, m15_file_id, initial_analysis, created_at
            ) VALUES(?, ?, 'ACTIVE', ?, ?, ?, ?, ?, ?)
            """,
            (
                symbol,
                int(admin_id),
                str(root_chat_id),
                int(root_message_id),
                h1_file_id,
                m15_file_id,
                initial_analysis,
                db.now_iso(),
            ),
        )
        return int(cur.lastrowid)


def recent_updates(session_id: int, limit: int):
    with db.conn() as con:
        rows = con.execute(
            """
            SELECT * FROM analysis_updates
            WHERE session_id=?
            ORDER BY update_no DESC
            LIMIT ?
            """,
            (int(session_id), int(limit)),
        ).fetchall()
    return list(reversed(rows))


def add_update(
    *, session_id: int, image_file_id: str, analysis_text: str, telegram_message_id: int
) -> int:
    with db.conn() as con:
        next_no = int(
            con.execute(
                "SELECT COALESCE(MAX(update_no), 0) + 1 FROM analysis_updates WHERE session_id=?",
                (int(session_id),),
            ).fetchone()[0]
        )
        con.execute(
            """
            INSERT INTO analysis_updates(
                session_id, update_no, image_file_id, analysis_text,
                telegram_message_id, created_at
            ) VALUES(?, ?, ?, ?, ?, ?)
            """,
            (
                int(session_id),
                next_no,
                image_file_id,
                analysis_text,
                int(telegram_message_id),
                db.now_iso(),
            ),
        )
        return next_no


def close_session(session_id: int) -> bool:
    with db.conn() as con:
        cur = con.execute(
            """
            UPDATE analysis_sessions
            SET status='CLOSED', closed_at=?
            WHERE id=? AND status='ACTIVE'
            """,
            (db.now_iso(), int(session_id)),
        )
        return cur.rowcount > 0


async def _session_lock(session_id: int) -> asyncio.Lock:
    async with _SESSION_LOCKS_GUARD:
        lock = _SESSION_LOCKS.get(int(session_id))
        if lock is None:
            lock = asyncio.Lock()
            _SESSION_LOCKS[int(session_id)] = lock
        return lock


async def _download_photo(bot: Bot, file_id: str) -> tuple[bytes, str]:
    telegram_file = await bot.get_file(file_id)
    buffer = BytesIO()
    await bot.download_file(telegram_file.file_path, destination=buffer)
    payload = buffer.getvalue()
    return payload, "image/jpeg"


def _data_uri(image_bytes: bytes, mime: str) -> str:
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _base_system_prompt() -> str:
    return (
        "You are NEXUS's professional market analyst and Persian analysis writer. "
        "Your job is to read TradingView chart screenshots and write the admin's analysis in one stable voice. "
        "Never invent prices or zones that cannot be supported by the images. "
        "If a drawn zone is technically misplaced, too wide, too narrow, or invalid, explicitly correct it and use the corrected zone. "
        "Core methodology is Smart Money / ICT: H1 gives context and directional bias; M15 is used for important Decision Points, FVG, Order Blocks and liquidity; M5 is only the entry trigger timeframe. "
        "A zone touch is never an entry signal. Entry is discussed only after valid reaction and confirmation such as liquidity sweep, displacement, MSS/CHOCH and a usable FVG/OB entry model. "
        "If confirmation is absent, say there is no trade. Do not force a setup and do not guarantee outcomes. "
        "Write in fluent, conversational, professional Persian suitable for direct Telegram publication. Keep jargon understandable. "
        "Do not use Markdown tables, code blocks, or headings with #. Keep the answer concise enough for a Telegram photo caption."
    )


def _initial_prompt(symbol: str) -> str:
    return f"""
نماد: {symbol}

دو تصویر به ترتیب مربوط به تایم‌فریم‌های 1H و 15M هستند.
تحلیل مولتی‌تایم‌فریم روز را بنویس.

الزام‌ها:
- ابتدا جهت و ساختار کلی H1 را توضیح بده، بدون قطعیت غیرواقعی.
- سپس نواحی مهم 15M را بررسی کن و بگو قیمت در کدام محدوده‌ها ارزش صبر کردن دارد.
- هر ناحیه‌ای که روی چارت اشتباه ترسیم شده را اصلاح کن و محدوده صحیح را روشن بگو.
- اگر ناحیه‌ها درست هستند، نیاز نیست بی‌دلیل ایراد بگیری.
- برای هر سناریو بگو روی 5M چه واکنش/تریگری لازم است؛ لمس ناحیه به‌تنهایی ورود نیست.
- اگر قیمت وسط مسیر است، تأکید کن دنبال قیمت نمی‌رویم.
- پایان متن یک جمع‌بندی کوتاه از پلن امروز داشته باشد.
- متن روان، طبیعی و قابل فهم باشد و لحن در تمام روز ثابت بماند.
- حداکثر حدود 850 تا 900 کاراکتر فارسی بنویس.
""".strip()


def _update_prompt(symbol: str, initial: str, updates: list) -> str:
    history = "\n\n".join(
        f"آپدیت {row['update_no']}:\n{row['analysis_text']}" for row in updates
    ) or "هنوز آپدیتی ثبت نشده است."
    return f"""
نماد: {symbol}

تحلیل پایه امروز:
{initial}

آپدیت‌های قبلی همین سشن:
{history}

تصویر پیوست، چارت جدید همین نماد در ادامه همان تحلیل است.
یک متن آپدیت جدید بنویس که فقط بر اساس همین سشن و تصویر جدید باشد.

الزام‌ها:
- مشخص کن کدام بخش از سناریوی قبلی تأیید، رد یا هنوز فعال است.
- اگر قیمت به ناحیه رسیده، واکنش را بررسی کن؛ لمس ناحیه را سیگنال ورود حساب نکن.
- اگر ناحیه مصرف شده/شکسته/نامعتبر شده، صریح اعلام کن.
- اگر ساختار یا Bias تغییر کرده، دلیل تغییر را روان توضیح بده.
- اگر در تصویر جدید ناحیه‌ای اشتباه رسم شده، اصلاحش کن.
- در صورت نیاز تریگر 5M را مشخص کن؛ بدون تأیید = بدون معامله.
- از تحلیل روزهای دیگر یا نمادهای دیگر هیچ چیزی وارد متن نکن.
- متن باید ادامه طبیعی تحلیل قبلی باشد، نه یک تحلیل کاملاً مستقل.
- حداکثر حدود 800 تا 900 کاراکتر فارسی بنویس.
""".strip()


async def _vision_complete(prompt: str, images: list[tuple[bytes, str]]) -> str | None:
    cfg = analysis_settings
    if not (cfg.enabled and cfg.ai_api_key and cfg.ai_base_url and cfg.ai_model):
        return None

    content: list[dict] = [{"type": "text", "text": prompt}]
    for payload, mime in images:
        content.append({
            "type": "image_url",
            "image_url": {"url": _data_uri(payload, mime)},
        })

    request_payload = {
        "model": cfg.ai_model,
        "messages": [
            {"role": "system", "content": _base_system_prompt()},
            {"role": "user", "content": content},
        ],
        "max_tokens": 1300,
    }
    headers = {
        "Authorization": f"Bearer {cfg.ai_api_key}",
        "Content-Type": "application/json",
    }
    endpoint = f"{cfg.ai_base_url}/chat/completions"

    try:
        async with httpx.AsyncClient(timeout=cfg.ai_timeout) as client:
            response = await client.post(endpoint, headers=headers, json=request_payload)
            response.raise_for_status()
            data = response.json()

        log.info(
            "analysis AI response model=%s body=%s",
            data.get("model"),
            str(data)[:4000],
        )

        choices = data.get("choices") or []
        if not choices:
            log.error("analysis AI response has no choices body=%s", str(data)[:4000])
            return None

        choice = choices[0] or {}
        message = choice.get("message") or {}

        value = message.get("content")

        if isinstance(value, str):
            value = value.strip()
            if value:
                return value

        if isinstance(value, list):
            chunks: list[str] = []
            for item in value:
                if isinstance(item, dict):
                    item_text = item.get("text") or item.get("content")
                    if isinstance(item_text, str) and item_text.strip():
                        chunks.append(item_text.strip())
            result = "\n".join(chunks).strip()
            if result:
                return result

        # Some reasoning-capable providers may expose usable text separately.
        reasoning = message.get("reasoning")
        if isinstance(reasoning, str) and reasoning.strip():
            log.warning(
                "analysis AI returned reasoning without normal content; using reasoning fallback"
            )
            return reasoning.strip()

        # Some providers may put text directly on the choice object.
        choice_text = choice.get("text")
        if isinstance(choice_text, str) and choice_text.strip():
            return choice_text.strip()

        log.error(
            "analysis AI returned empty content finish_reason=%s body=%s",
            choice.get("finish_reason"),
            str(data)[:4000],
        )
        return None
    except httpx.HTTPStatusError as exc:
        body = ""
        try:
            body = exc.response.text[:2000]
        except Exception:
            pass
        log.exception(
            "analysis AI request failed status=%s body=%s",
            getattr(exc.response, "status_code", "?"),
            body,
        )
        return None
    except Exception as exc:
        log.exception("analysis AI request failed: %s", exc)
        return None


def _caption(text: str) -> str:
    value = (text or "").strip()
    value = re.sub(r"```.*?```", "", value, flags=re.S)
    value = value.replace("**", "").replace("###", "").replace("##", "").replace("# ", "")
    value = re.sub(r"\n{3,}", "\n\n", value).strip()
    limit = analysis_settings.max_caption_chars
    if len(value) <= limit:
        return value
    shortened = value[: max(1, limit - 1)].rstrip(" ،,:؛;-.\n")
    return shortened + "…"


async def _send_center(bot: Bot, user_id: int, chat_id: int, text: str | None = None) -> None:
    cfg = analysis_settings
    status = []
    if not cfg.target_chat_id:
        status.append("⚠️ مقصد انتشار تنظیم نشده است (ANALYSIS_TARGET_CHAT_ID).")
    if not (cfg.ai_api_key and cfg.ai_base_url and cfg.ai_model):
        status.append("⚠️ تنظیمات مدل تحلیل کامل نیست.")
    body = text or "<b>🧠 NEXUS Analysis Center</b>\n\nتحلیل‌های چندنمادی را از این بخش مدیریت کنید."
    if status:
        body += "\n\n" + "\n".join(status)
    await bot.send_message(
        chat_id,
        body,
        parse_mode=ParseMode.HTML,
        reply_markup=analysis_center_menu(),
    )


async def _require_admin(cb_or_message) -> bool:
    user_id = cb_or_message.from_user.id
    if is_admin(user_id):
        return True
    if isinstance(cb_or_message, CallbackQuery):
        await cb_or_message.answer("دسترسی مجاز نیست.", show_alert=True)
    return False


async def _publish_initial(
    bot: Bot,
    *,
    symbol: str,
    admin_id: int,
    h1_file_id: str,
    m15_file_id: str,
    analysis_text: str,
) -> int:
    target = analysis_settings.target_chat_id
    if target is None:
        raise RuntimeError("ANALYSIS_TARGET_CHAT_ID is not configured")
    caption = _caption(f"📊 تحلیل {symbol}\n\n{analysis_text}")
    media = [
        InputMediaPhoto(media=h1_file_id, caption=caption),
        InputMediaPhoto(media=m15_file_id),
    ]
    kwargs = {}
    if analysis_settings.target_thread_id:
        kwargs["message_thread_id"] = analysis_settings.target_thread_id
    sent = await bot.send_media_group(chat_id=target, media=media, **kwargs)
    root_message_id = int(sent[0].message_id)
    return create_active_session(
        symbol=symbol,
        admin_id=admin_id,
        root_chat_id=target,
        root_message_id=root_message_id,
        h1_file_id=h1_file_id,
        m15_file_id=m15_file_id,
        initial_analysis=_caption(analysis_text),
    )


async def _publish_update(
    bot: Bot,
    *,
    session,
    file_id: str,
    analysis_text: str,
) -> int:
    target: int | str
    root_chat = str(session["root_chat_id"] or "").strip()
    try:
        target = int(root_chat)
    except ValueError:
        target = root_chat
    kwargs = {
        "chat_id": target,
        "photo": file_id,
        "caption": _caption(f"🔄 آپدیت {session['symbol']}\n\n{analysis_text}"),
        "reply_parameters": ReplyParameters(
            message_id=int(session["root_message_id"]),
            allow_sending_without_reply=True,
        ),
    }
    if analysis_settings.target_thread_id:
        kwargs["message_thread_id"] = analysis_settings.target_thread_id
    msg = await bot.send_photo(**kwargs)
    return int(msg.message_id)


@router.message(Command("analysis"))
async def analysis_command(message: Message, bot: Bot, state: FSMContext):
    if not await _require_admin(message):
        return
    await state.clear()
    await _send_center(bot, message.from_user.id, message.chat.id)


@router.callback_query(F.data == "analysis_center")
async def analysis_center_cb(cb: CallbackQuery, bot: Bot, state: FSMContext):
    if not await _require_admin(cb):
        return
    await state.clear()
    await cb.answer()
    await _send_center(bot, cb.from_user.id, cb.message.chat.id)


@router.callback_query(F.data == "analysis:noop")
async def analysis_noop(cb: CallbackQuery):
    await cb.answer("تحلیل فعالی وجود ندارد.")


@router.callback_query(F.data == "analysis:new")
async def analysis_new(cb: CallbackQuery, bot: Bot, state: FSMContext):
    if not await _require_admin(cb):
        return
    await state.clear()
    await cb.answer()
    await bot.send_message(
        cb.message.chat.id,
        "<b>➕ تحلیل جدید</b>\n\nنماد را انتخاب کنید. هر نماد سشن مستقل خودش را دارد و می‌توانید چند نماد را همزمان فعال نگه دارید.",
        parse_mode=ParseMode.HTML,
        reply_markup=symbol_menu(),
    )


@router.callback_query(F.data == "analysis:new:CUSTOM")
async def analysis_new_custom(cb: CallbackQuery, bot: Bot, state: FSMContext):
    if not await _require_admin(cb):
        return
    await cb.answer()
    await state.set_state(AnalysisFlow.waiting_custom_symbol)
    await bot.send_message(cb.message.chat.id, "نماد را تایپ کنید؛ مثال: NASDAQ یا EURUSD")


@router.message(AnalysisFlow.waiting_custom_symbol, F.text)
async def analysis_custom_symbol_text(message: Message, bot: Bot, state: FSMContext):
    if not await _require_admin(message):
        return
    symbol = _safe_symbol(message.text or "")
    if not symbol:
        await bot.send_message(message.chat.id, "نماد معتبر نیست. دوباره ارسال کنید.")
        return
    if get_active_session_by_symbol(symbol):
        await state.clear()
        await bot.send_message(
            message.chat.id,
            f"برای {symbol} یک تحلیل فعال وجود دارد. برای ادامه از «آپدیت تحلیل» استفاده کنید.",
            reply_markup=analysis_center_menu(),
        )
        return
    await state.update_data(analysis_symbol=symbol)
    await state.set_state(AnalysisFlow.waiting_h1)
    await bot.send_message(message.chat.id, f"📷 {symbol}\nابتدا تصویر تایم‌فریم 1H را ارسال کنید.")


@router.callback_query(F.data.startswith("analysis:new:"))
async def analysis_new_symbol(cb: CallbackQuery, bot: Bot, state: FSMContext):
    if not await _require_admin(cb):
        return
    raw = cb.data.split(":", 2)[2]
    if raw == "CUSTOM":
        return
    symbol = _safe_symbol(raw)
    if not symbol:
        await cb.answer("نماد نامعتبر است.", show_alert=True)
        return
    if get_active_session_by_symbol(symbol):
        await cb.answer("برای این نماد تحلیل فعال دارید. از بخش آپدیت استفاده کنید.", show_alert=True)
        return
    await cb.answer()
    await state.clear()
    await state.update_data(analysis_symbol=symbol)
    await state.set_state(AnalysisFlow.waiting_h1)
    await bot.send_message(cb.message.chat.id, f"📷 {symbol}\nابتدا تصویر تایم‌فریم 1H را ارسال کنید.")


@router.message(AnalysisFlow.waiting_h1, F.photo)
async def analysis_receive_h1(message: Message, bot: Bot, state: FSMContext):
    if not await _require_admin(message):
        return
    data = await state.get_data()
    symbol = _safe_symbol(str(data.get("analysis_symbol") or ""))
    if not symbol:
        await state.clear()
        await bot.send_message(message.chat.id, "سشن نامعتبر شد. تحلیل جدید را دوباره شروع کنید.")
        return
    await state.update_data(analysis_h1_file_id=message.photo[-1].file_id)
    await state.set_state(AnalysisFlow.waiting_m15)
    await bot.send_message(message.chat.id, f"✅ 1H دریافت شد.\nحالا تصویر تایم‌فریم 15M برای {symbol} را ارسال کنید.")


@router.message(AnalysisFlow.waiting_m15, F.photo)
async def analysis_receive_m15(message: Message, bot: Bot, state: FSMContext):
    if not await _require_admin(message):
        return
    data = await state.get_data()
    symbol = _safe_symbol(str(data.get("analysis_symbol") or ""))
    h1_file_id = str(data.get("analysis_h1_file_id") or "")
    m15_file_id = message.photo[-1].file_id
    if not symbol or not h1_file_id:
        await state.clear()
        await bot.send_message(message.chat.id, "اطلاعات تحلیل ناقص شد. تحلیل جدید را دوباره شروع کنید.")
        return
    if get_active_session_by_symbol(symbol):
        await state.clear()
        await bot.send_message(message.chat.id, f"برای {symbol} از قبل سشن فعال وجود دارد.")
        return
    if not analysis_settings.target_chat_id:
        await state.clear()
        await bot.send_message(message.chat.id, "ANALYSIS_TARGET_CHAT_ID تنظیم نشده است؛ انتشار انجام نشد.")
        return

    wait_msg = await bot.send_message(message.chat.id, f"🧠 در حال تحلیل مولتی‌تایم‌فریم {symbol}…")
    try:
        h1_image, h1_mime = await _download_photo(bot, h1_file_id)
        m15_image, m15_mime = await _download_photo(bot, m15_file_id)
        analysis_text = await _vision_complete(
            _initial_prompt(symbol),
            [(h1_image, h1_mime), (m15_image, m15_mime)],
        )
        if not analysis_text:
            raise RuntimeError("AI returned no analysis")
        session_id = await _publish_initial(
            bot,
            symbol=symbol,
            admin_id=message.from_user.id,
            h1_file_id=h1_file_id,
            m15_file_id=m15_file_id,
            analysis_text=analysis_text,
        )
        await state.clear()
        await bot.edit_message_text(
            chat_id=wait_msg.chat.id,
            message_id=wait_msg.message_id,
            text=f"✅ تحلیل {symbol} منتشر شد و به‌عنوان سشن #{session_id} فعال است.\nآپدیت‌های بعدی فقط به همین سشن متصل می‌شوند.",
            reply_markup=analysis_center_menu(),
        )
    except Exception as exc:
        log.exception("initial analysis failed symbol=%s: %s", symbol, exc)
        await state.clear()
        await bot.edit_message_text(
            chat_id=wait_msg.chat.id,
            message_id=wait_msg.message_id,
            text=f"❌ تحلیل {symbol} منتشر نشد. تنظیمات AI/گروه مقصد یا لاگ سرور را بررسی کنید.",
            reply_markup=analysis_center_menu(),
        )


@router.callback_query(F.data == "analysis:update")
async def analysis_update_pick(cb: CallbackQuery, bot: Bot, state: FSMContext):
    if not await _require_admin(cb):
        return
    await state.clear()
    await cb.answer()
    rows = list_active_sessions()
    await bot.send_message(
        cb.message.chat.id,
        "<b>🔄 آپدیت تحلیل</b>\n\nنمادی را انتخاب کنید که عکس جدید مربوط به آن است:",
        parse_mode=ParseMode.HTML,
        reply_markup=_session_menu(rows, "update"),
    )


@router.callback_query(F.data.startswith("analysis:update:"))
async def analysis_update_session(cb: CallbackQuery, bot: Bot, state: FSMContext):
    if not await _require_admin(cb):
        return
    try:
        session_id = int(cb.data.rsplit(":", 1)[1])
    except ValueError:
        await cb.answer("سشن نامعتبر است.", show_alert=True)
        return
    session = get_active_session(session_id)
    if not session:
        await cb.answer("این تحلیل دیگر فعال نیست.", show_alert=True)
        return
    await cb.answer()
    await state.clear()
    await state.update_data(analysis_session_id=session_id)
    await state.set_state(AnalysisFlow.waiting_update)
    await bot.send_message(
        cb.message.chat.id,
        f"📷 آپدیت {session['symbol']}\nعکس جدید چارت را ارسال کنید. این آپدیت به تحلیل اصلی همین نماد ریپلای می‌شود.",
    )


@router.message(AnalysisFlow.waiting_update, F.photo)
async def analysis_receive_update(message: Message, bot: Bot, state: FSMContext):
    if not await _require_admin(message):
        return
    data = await state.get_data()
    session_id = int(data.get("analysis_session_id") or 0)
    session = get_active_session(session_id)
    if not session:
        await state.clear()
        await bot.send_message(message.chat.id, "این سشن بسته یا حذف شده است.", reply_markup=analysis_center_menu())
        return

    lock = await _session_lock(session_id)
    async with lock:
        # Re-read under lock so a simultaneous close/update cannot mix contexts.
        session = get_active_session(session_id)
        if not session:
            await state.clear()
            await bot.send_message(message.chat.id, "این تحلیل دیگر فعال نیست.")
            return
        file_id = message.photo[-1].file_id
        wait_msg = await bot.send_message(message.chat.id, f"🧠 در حال آپدیت {session['symbol']}…")
        try:
            image, mime = await _download_photo(bot, file_id)
            history = recent_updates(session_id, analysis_settings.history_limit)
            analysis_text = await _vision_complete(
                _update_prompt(session["symbol"], session["initial_analysis"], history),
                [(image, mime)],
            )
            if not analysis_text:
                raise RuntimeError("AI returned no update")
            published_message_id = await _publish_update(
                bot,
                session=session,
                file_id=file_id,
                analysis_text=analysis_text,
            )
            update_no = add_update(
                session_id=session_id,
                image_file_id=file_id,
                analysis_text=_caption(analysis_text),
                telegram_message_id=published_message_id,
            )
            await state.clear()
            await bot.edit_message_text(
                chat_id=wait_msg.chat.id,
                message_id=wait_msg.message_id,
                text=f"✅ آپدیت #{update_no} برای {session['symbol']} منتشر شد و روی تحلیل اولیه ریپلای شد.",
                reply_markup=analysis_center_menu(),
            )
        except Exception as exc:
            log.exception("analysis update failed session=%s: %s", session_id, exc)
            await state.clear()
            await bot.edit_message_text(
                chat_id=wait_msg.chat.id,
                message_id=wait_msg.message_id,
                text=f"❌ آپدیت {session['symbol']} منتشر نشد. لاگ سرور را بررسی کنید.",
                reply_markup=analysis_center_menu(),
            )


@router.callback_query(F.data == "analysis:active")
async def analysis_active(cb: CallbackQuery, bot: Bot):
    if not await _require_admin(cb):
        return
    await cb.answer()
    rows = list_active_sessions()
    if not rows:
        text = "📂 تحلیل فعالی وجود ندارد."
    else:
        lines = ["<b>📂 تحلیل‌های فعال</b>", ""]
        for row in rows:
            count = len(recent_updates(int(row["id"]), 1000))
            lines.append(f"• {row['symbol']}  |  سشن #{row['id']}  |  {count} آپدیت")
        text = "\n".join(lines)
    await bot.send_message(cb.message.chat.id, text, parse_mode=ParseMode.HTML, reply_markup=analysis_center_menu())


@router.callback_query(F.data == "analysis:close")
async def analysis_close_pick(cb: CallbackQuery, bot: Bot, state: FSMContext):
    if not await _require_admin(cb):
        return
    await state.clear()
    await cb.answer()
    await bot.send_message(
        cb.message.chat.id,
        "<b>✅ پایان تحلیل</b>\n\nنمادی را انتخاب کنید که سناریوی آن تمام شده است:",
        parse_mode=ParseMode.HTML,
        reply_markup=_session_menu(list_active_sessions(), "close"),
    )


@router.callback_query(F.data.startswith("analysis:close:"))
async def analysis_close_session(cb: CallbackQuery, bot: Bot, state: FSMContext):
    if not await _require_admin(cb):
        return
    try:
        session_id = int(cb.data.rsplit(":", 1)[1])
    except ValueError:
        await cb.answer("سشن نامعتبر است.", show_alert=True)
        return
    session = get_active_session(session_id)
    if not session:
        await cb.answer("این تحلیل از قبل بسته شده است.", show_alert=True)
        return
    lock = await _session_lock(session_id)
    async with lock:
        session = get_active_session(session_id)
        if not session:
            await cb.answer("این تحلیل از قبل بسته شده است.", show_alert=True)
            return
        target_raw = str(session["root_chat_id"] or "")
        try:
            target: int | str = int(target_raw)
        except ValueError:
            target = target_raw
        kwargs = {
            "chat_id": target,
            "text": f"✅ پایان تحلیل {session['symbol']}\n\nاین سناریو بسته شد و آپدیت بعدی به این تحلیل متصل نخواهد شد.",
            "reply_parameters": ReplyParameters(
                message_id=int(session["root_message_id"]),
                allow_sending_without_reply=True,
            ),
        }
        if analysis_settings.target_thread_id:
            kwargs["message_thread_id"] = analysis_settings.target_thread_id
        try:
            await bot.send_message(**kwargs)
        except Exception as exc:
            log.warning("close marker could not be published session=%s: %s", session_id, exc)
        closed = close_session(session_id)
        await state.clear()
        await cb.answer("تحلیل بسته شد." if closed else "تحلیل از قبل بسته بود.")
        await bot.send_message(
            cb.message.chat.id,
            f"✅ سشن #{session_id} برای {session['symbol']} بسته شد.",
            reply_markup=analysis_center_menu(),
        )


def install_analysis_center(core_module) -> None:
    """Attach Analysis Center to the existing admin dashboard without touching core handlers."""
    init_analysis_db()
    original_admin_menu = core_module.admin_menu

    def patched_admin_menu(lang: str) -> InlineKeyboardMarkup:
        markup = original_admin_menu(lang)
        rows = [list(row) for row in markup.inline_keyboard]
        label = "🧠 مرکز تحلیل" if lang == "fa" else "🧠 Analysis Center"
        button = InlineKeyboardButton(text=label, callback_data="analysis_center")
        # Insert before the final navigation/language row so the admin layout remains familiar.
        insert_at = max(0, len(rows) - 1)
        rows.insert(insert_at, [button])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    core_module.admin_menu = patched_admin_menu
    log.info(
        "Analysis Center installed enabled=%s target=%s model=%s",
        analysis_settings.enabled,
        analysis_settings.target_chat_id,
        analysis_settings.ai_model,
    )
