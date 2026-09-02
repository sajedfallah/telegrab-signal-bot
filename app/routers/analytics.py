from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from .. import db
from ..config import settings
from ..services import analytics_service as analytics

router = Router(name="analytics")


def _lang(user_id: int) -> str:
    row = db.get_user(user_id)
    return row["language"] if row and row["language"] in {"fa", "en"} else "fa"


def _is_admin(user_id: int) -> bool:
    return user_id in settings.admin_ids


def _period_buttons(key: str) -> list[InlineKeyboardButton]:
    return [
        InlineKeyboardButton(text=("✅ 7D" if key == "7" else "7D"), callback_data="analytics:overview:7"),
        InlineKeyboardButton(text=("✅ 30D" if key == "30" else "30D"), callback_data="analytics:overview:30"),
        InlineKeyboardButton(text=("✅ ALL" if key == "all" else "ALL"), callback_data="analytics:overview:all"),
    ]


def _menu(lang: str, key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        _period_buttons(key),
        [
            InlineKeyboardButton(text="📊 نمادها" if lang == "fa" else "📊 Symbols", callback_data=f"analytics:symbols:{key}"),
            InlineKeyboardButton(text="🔄 تریلینگ" if lang == "fa" else "🔄 Trailing", callback_data=f"analytics:trailing:{key}"),
        ],
        [InlineKeyboardButton(text="🆓 Free vs VIP 💎", callback_data=f"analytics:channels:{key}")],
        [InlineKeyboardButton(text="⬅️ Signal Center" if lang == "en" else "⬅️ مرکز سیگنال", callback_data="admin_signals")],
        [InlineKeyboardButton(text="🏠 پنل ادمین" if lang == "fa" else "🏠 Admin Panel", callback_data="admin")],
    ])


async def _render(cb: CallbackQuery, text: str, markup: InlineKeyboardMarkup) -> None:
    try:
        await cb.message.edit_text(text, reply_markup=markup, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        db.set_last_menu_message(cb.from_user.id, cb.message.message_id)
    except Exception:
        sent = await cb.message.answer(text, reply_markup=markup, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        db.set_last_menu_message(cb.from_user.id, sent.message_id)


def _period_name(info, lang: str) -> str:
    return info.label_fa if lang == "fa" else info.label_en


@router.callback_query(F.data == "signal_analytics")
@router.callback_query(F.data.startswith("analytics:overview:"))
async def analytics_overview(cb: CallbackQuery):
    if not _is_admin(cb.from_user.id):
        await cb.answer("Access denied", show_alert=True)
        return
    key = cb.data.rsplit(":", 1)[1] if cb.data.startswith("analytics:") else "30"
    lang = _lang(cb.from_user.id)
    data = analytics.overview(key)
    p = data["period"]
    await cb.answer()
    if lang == "fa":
        text = (
            f"<b>داشبورد تحلیلی سیگنال — {_period_name(p, lang)}</b>\n\n"
            f"معاملات بسته: <b>{data['total']}</b>\n"
            f"برد / باخت / سر‌به‌سر: <b>{data['wins']} / {data['losses']} / {data['be']}</b>\n"
            f"وین‌ریت: <b>{data['win_rate']}٪</b>\n"
            f"بازده خام: <b>{data['net_pct']:+g}٪</b>\n"
            f"فارکس: <b>{data['forex_pips']:+g} Pips</b>\n"
            f"کریپتو: <b>{data['crypto_pct']:+g}٪</b>\n"
            f"میانگین R:R: <b>{data['avg_rr']:g}</b>\n"
            f"سیگنال فعال: <b>{data['active']}</b>"
        )
    else:
        text = (
            f"<b>Signal Analytics — {_period_name(p, lang)}</b>\n\n"
            f"Closed trades: <b>{data['total']}</b>\n"
            f"Win / Loss / BE: <b>{data['wins']} / {data['losses']} / {data['be']}</b>\n"
            f"Win rate: <b>{data['win_rate']}%</b>\n"
            f"Raw return: <b>{data['net_pct']:+g}%</b>\n"
            f"Forex: <b>{data['forex_pips']:+g} Pips</b>\n"
            f"Crypto: <b>{data['crypto_pct']:+g}%</b>\n"
            f"Average R:R: <b>{data['avg_rr']:g}</b>\n"
            f"Active signals: <b>{data['active']}</b>"
        )
    await _render(cb, text, _menu(lang, key))


@router.callback_query(F.data.startswith("analytics:symbols:"))
async def analytics_symbols(cb: CallbackQuery):
    if not _is_admin(cb.from_user.id): return
    key = cb.data.rsplit(":", 1)[1]; lang = _lang(cb.from_user.id)
    rows = analytics.symbols(key)
    await cb.answer()
    lines = []
    for r in rows:
        if lang == "fa":
            lines.append(f"<b>{escape(r['symbol'])}</b> — {r['total']} معامله | WR {r['win_rate']}٪ | {r['net_pct']:+g}٪")
        else:
            lines.append(f"<b>{escape(r['symbol'])}</b> — {r['total']} trades | WR {r['win_rate']}% | {r['net_pct']:+g}%")
    title = "<b>عملکرد نمادها</b>" if lang == "fa" else "<b>Symbol Performance</b>"
    await _render(cb, title + "\n\n" + ("\n".join(lines) if lines else "—"), _menu(lang, key))


@router.callback_query(F.data.startswith("analytics:trailing:"))
async def analytics_trailing(cb: CallbackQuery):
    if not _is_admin(cb.from_user.id): return
    key = cb.data.rsplit(":", 1)[1]; lang = _lang(cb.from_user.id)
    rows = analytics.trailing(key)
    await cb.answer()
    lines = []
    for r in rows:
        if lang == "fa":
            lines.append(f"<b>{escape(r['code'])}</b> — {r['total']} معامله | WR {r['win_rate']}٪ | {r['net_pct']:+g}٪")
        else:
            lines.append(f"<b>{escape(r['code'])}</b> — {r['total']} trades | WR {r['win_rate']}% | {r['net_pct']:+g}%")
    title = "<b>عملکرد مدل‌های حدضرر متحرک</b>" if lang == "fa" else "<b>Trailing Model Performance</b>"
    await _render(cb, title + "\n\n" + ("\n".join(lines) if lines else "—"), _menu(lang, key))


@router.callback_query(F.data.startswith("analytics:channels:"))
async def analytics_channels(cb: CallbackQuery):
    if not _is_admin(cb.from_user.id): return
    key = cb.data.rsplit(":", 1)[1]; lang = _lang(cb.from_user.id)
    rows = analytics.channels(key)
    await cb.answer()
    free, vip = rows["FREE"], rows["VIP"]
    if lang == "fa":
        text = (
            "<b>مقایسه کانال‌ها</b>\n\n"
            "<b>FREE</b>\n"
            f"معاملات: {free['total']} | WR: {free['win_rate']}٪ | بازده: {free['net_pct']:+g}٪\n\n"
            "<b>VIP</b>\n"
            f"معاملات: {vip['total']} | WR: {vip['win_rate']}٪ | بازده: {vip['net_pct']:+g}٪"
        )
    else:
        text = (
            "<b>Channel Comparison</b>\n\n"
            "<b>FREE</b>\n"
            f"Trades: {free['total']} | WR: {free['win_rate']}% | Return: {free['net_pct']:+g}%\n\n"
            "<b>VIP</b>\n"
            f"Trades: {vip['total']} | WR: {vip['win_rate']}% | Return: {vip['net_pct']:+g}%"
        )
    await _render(cb, text, _menu(lang, key))
