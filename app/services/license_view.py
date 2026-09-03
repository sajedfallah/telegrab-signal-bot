from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from typing import Any

from .license_service import AccessSnapshot


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def remaining_duration_text(expires_at: str | None, *, lang: str = "fa", now: datetime | None = None) -> str:
    exp = _parse_dt(expires_at)
    if not exp:
        return "—"
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    seconds = max(0, int((exp - current).total_seconds()))
    if seconds <= 0:
        return "منقضی‌شده" if lang == "fa" else "Expired"
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    if lang == "fa":
        parts = []
        if days:
            parts.append(f"{days} روز")
        if hours or days:
            parts.append(f"{hours} ساعت")
        parts.append(f"{minutes} دقیقه")
        return " و ".join(parts)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)


def _fmt_dt(value: str | None, timezone_obj) -> str:
    dt = _parse_dt(value)
    if not dt:
        return "—"
    try:
        dt = dt.astimezone(timezone_obj)
    except Exception:
        pass
    return dt.strftime("%Y/%m/%d - %H:%M")


def _plan_label(snapshot: AccessSnapshot, plan: Any | None, *, lang: str) -> str:
    if plan is not None:
        try:
            keys = set(plan.keys())
        except Exception:
            keys = set()
        preferred = "title_fa" if lang == "fa" else "title_en"
        fallback = "fa" if lang == "fa" else "en"
        for key in (preferred, fallback, "code"):
            try:
                value = plan[key] if key in keys else None
            except Exception:
                value = None
            if value:
                return str(value)
    return str(snapshot.plan_code or "—")


def render_autotrade_license(
    snapshot: AccessSnapshot,
    *,
    license_key: str | None,
    mt5_account: str | None,
    plan: Any | None,
    timezone_obj,
    lang: str = "fa",
    now: datetime | None = None,
) -> tuple[str, bool]:
    """Render the canonical detailed AutoTrade license screen.

    Returns ``(text, purchase_cta_required)``. AutoTrade validity details are
    intentionally centralized here so dashboard/status screens can stay concise.
    """
    if not snapshot.autotrade:
        if lang == "fa":
            return (
                "<b>🔑 مجوز من — NEXUS AutoTrade</b>\n\n"
                "🔴 وضعیت: <b>غیرفعال</b>\n\n"
                "برای دریافت مجوز اختصاصی AutoTrade ابتدا سرویس AutoTrade یا پکیج VIP + AutoTrade را خریداری/تمدید کنید.\n"
                "پس از فعال شدن سرویس، شماره حساب MT5 ثبت می‌شود و لایسنس اختصاصی همان حساب در این بخش نمایش داده خواهد شد.",
                True,
            )
        return (
            "<b>🔑 My License — NEXUS AutoTrade</b>\n\n"
            "🔴 Status: <b>INACTIVE</b>\n\n"
            "Purchase or renew AutoTrade / VIP + AutoTrade to receive a dedicated license. "
            "After activation, your MT5 account is registered and the bound license is shown here.",
            True,
        )

    expiry = snapshot.autotrade_expires_at or snapshot.expires_at
    plan_label = escape(_plan_label(snapshot, plan, lang=lang))
    key = (license_key or "").strip()
    account = (mt5_account or "").strip()
    remaining = remaining_duration_text(expiry, lang=lang, now=now)

    if lang == "fa":
        key_line = f"<code>{escape(key)}</code>" if key else "<b>در انتظار صدور پس از ثبت حساب MT5</b>"
        account_line = f"<code>{escape(account)}</code>" if account else "<b>ثبت نشده</b>"
        text = (
            "<b>🔑 مجوز من — NEXUS AutoTrade</b>\n\n"
            "🟢 وضعیت: <b>فعال</b>\n"
            f"📦 نوع اشتراک: <b>{plan_label}</b>\n"
            f"🗓 شروع: <b>{_fmt_dt(snapshot.starts_at, timezone_obj)}</b>\n"
            f"📅 پایان AutoTrade: <b>{_fmt_dt(expiry, timezone_obj)}</b>\n"
            f"⏳ باقی‌مانده: <b>{escape(remaining)}</b>\n\n"
            f"🖥 حساب MT5: {account_line}\n"
            f"🔐 License Key:\n{key_line}\n\n"
            "این مجوز شخصی است و فقط برای حساب MT5 ثبت‌شده معتبر است."
        )
    else:
        key_line = f"<code>{escape(key)}</code>" if key else "<b>Pending MT5 account registration</b>"
        account_line = f"<code>{escape(account)}</code>" if account else "<b>Not registered</b>"
        text = (
            "<b>🔑 My License — NEXUS AutoTrade</b>\n\n"
            "🟢 Status: <b>ACTIVE</b>\n"
            f"📦 Subscription: <b>{plan_label}</b>\n"
            f"🗓 Starts: <b>{_fmt_dt(snapshot.starts_at, timezone_obj)}</b>\n"
            f"📅 AutoTrade expires: <b>{_fmt_dt(expiry, timezone_obj)}</b>\n"
            f"⏳ Remaining: <b>{escape(remaining)}</b>\n\n"
            f"🖥 MT5 account: {account_line}\n"
            f"🔐 License Key:\n{key_line}\n\n"
            "This license is personal and valid only for the registered MT5 account."
        )
    return text, False
