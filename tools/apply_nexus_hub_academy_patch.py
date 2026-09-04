from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def write(rel: str, text: str) -> None:
    (ROOT / rel).write_text(text, encoding="utf-8", newline="\n")


def replace_once(rel: str, old: str, new: str) -> None:
    text = read(rel)
    if new in text:
        return
    if old not in text:
        raise RuntimeError(f"Expected patch anchor not found in {rel}: {old[:100]!r}")
    write(rel, text.replace(old, new, 1))


def regex_replace_once(rel: str, pattern: str, replacement: str) -> None:
    text = read(rel)
    new_text, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count == 0:
        # Idempotent reruns are allowed if the new marker is already present.
        if replacement.strip()[:60] in text:
            return
        raise RuntimeError(f"Regex patch anchor not found in {rel}: {pattern[:100]!r}")
    write(rel, new_text)


# ---------------------------------------------------------------------------
# 1) Runtime dependencies
# ---------------------------------------------------------------------------
replace_once(
    "requirements.txt",
    "Pillow==11.3.0\n",
    "Pillow==11.3.0\nqrcode>=8,<9\n",
)


# ---------------------------------------------------------------------------
# 2) Core settings: official folder + dedicated Academy destination
# ---------------------------------------------------------------------------
replace_once(
    "app/config.py",
    '    public_channel_url: str = _required("PUBLIC_CHANNEL_URL")\n    free_channel_url: str = _required("FREE_CHANNEL_URL")\n    vip_channel_id: int = _int("VIP_CHANNEL_ID")\n',
    '    public_channel_url: str = _required("PUBLIC_CHANNEL_URL")\n'
    '    nexus_folder_url: str = os.getenv("NEXUS_FOLDER_URL", "https://t.me/addlist/ASXi4-91edg2YzA8").strip()\n'
    '    academy_channel_id: str = os.getenv("ACADEMY_CHANNEL_ID", "").strip()\n'
    '    academy_channel_url: str = os.getenv("ACADEMY_CHANNEL_URL", "").strip()\n'
    '    free_channel_url: str = _required("FREE_CHANNEL_URL")\n'
    '    vip_channel_id: int = _int("VIP_CHANNEL_ID")\n',
)


# ---------------------------------------------------------------------------
# 3) .env template. Folder URL is public/non-secret; Academy target stays blank
#    until the real channel is created and the bot is made administrator there.
# ---------------------------------------------------------------------------
replace_once(
    ".env.example",
    "PUBLIC_CHANNEL_URL=https://t.me/your_public_channel\nFREE_CHANNEL_URL=https://t.me/your_free_signal_channel\n",
    "PUBLIC_CHANNEL_URL=https://t.me/your_public_channel\n"
    "# Official Telegram folder: single entry point to the NEXUS ecosystem\n"
    "NEXUS_FOLDER_URL=https://t.me/addlist/ASXi4-91edg2YzA8\n"
    "# Dedicated educational channel. Fill these before production deploy.\n"
    "ACADEMY_CHANNEL_ID=\n"
    "ACADEMY_CHANNEL_URL=\n"
    "FREE_CHANNEL_URL=https://t.me/your_free_signal_channel\n",
)

replace_once(
    ".env.example",
    "# --- NEXUS Agentic Public Channel Content ---\n",
    "# --- NEXUS Agentic Content / Academy + Public routing ---\n",
)


# ---------------------------------------------------------------------------
# 4) Customer UI: one dominant NEXUS entry point, with existing management
#    actions retained underneath. Telegram URL buttons open the addlist folder
#    natively; the QR button is useful for desktop/secondary-device onboarding.
# ---------------------------------------------------------------------------
ui = read("app/ui.py")
main_menu_pattern = r'def main_menu\(lang: str, is_admin: bool = False\) -> InlineKeyboardMarkup:\n.*?\n    return kb\(rows\)\n\n\ndef guide_hub_menu'
main_menu_replacement = '''def main_menu(lang: str, is_admin: bool = False) -> InlineKeyboardMarkup:
    """NEXUS customer gateway.

    The Telegram folder is the primary ecosystem entry point. Commercial and
    account actions remain in the bot, while channels themselves live inside
    the official NEXUS folder.
    """
    if lang == "fa":
        rows = [
            [InlineKeyboardButton(text="🚀 ورود به NEXUS", url=settings.nexus_folder_url)],
            [
                InlineKeyboardButton(text="📊 مدیریت سیگنال‌ها", callback_data="client_signals"),
                InlineKeyboardButton(text="💎 خرید اشتراک", callback_data="vip"),
            ],
            [
                InlineKeyboardButton(text="👤 حساب من", callback_data="account"),
                InlineKeyboardButton(text="🎓 راهنما", callback_data="guide_hub"),
            ],
            [
                InlineKeyboardButton(text="📱 QR فولدر NEXUS", callback_data="nexus_folder_qr"),
                InlineKeyboardButton(text="🛟 پشتیبانی", callback_data="support"),
            ],
            [InlineKeyboardButton(text="🌐 تغییر زبان", callback_data="change_language")],
        ]
        if is_admin:
            rows[-1].append(InlineKeyboardButton(text="🛠 پنل مدیریت", callback_data="admin"))
    else:
        rows = [
            [InlineKeyboardButton(text="🚀 Enter NEXUS", url=settings.nexus_folder_url)],
            [
                InlineKeyboardButton(text="📊 Manage Signals", callback_data="client_signals"),
                InlineKeyboardButton(text="💎 Buy Subscription", callback_data="vip"),
            ],
            [
                InlineKeyboardButton(text="👤 My Account", callback_data="account"),
                InlineKeyboardButton(text="🎓 Guide", callback_data="guide_hub"),
            ],
            [
                InlineKeyboardButton(text="📱 NEXUS Folder QR", callback_data="nexus_folder_qr"),
                InlineKeyboardButton(text="🛟 Support", callback_data="support"),
            ],
            [InlineKeyboardButton(text="🌐 Change Language", callback_data="change_language")],
        ]
        if is_admin:
            rows[-1].append(InlineKeyboardButton(text="🛠 Admin Panel", callback_data="admin"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def guide_hub_menu'''
new_ui, n = re.subn(main_menu_pattern, main_menu_replacement, ui, count=1, flags=re.S)
if n == 0 and "QR فولدر NEXUS" not in ui:
    raise RuntimeError("Could not replace main_menu in app/ui.py")
if n:
    write("app/ui.py", new_ui)


# ---------------------------------------------------------------------------
# 5) Branded, functional QR generator. The URL is the source of truth; the QR
#    is regenerated from it so a future folder-link change cannot leave a stale
#    image embedded in the bot.
# ---------------------------------------------------------------------------
portal_py = r'''from __future__ import annotations

import io
from pathlib import Path
from urllib.parse import urlparse

import qrcode
from qrcode.constants import ERROR_CORRECT_H
from PIL import Image, ImageDraw, ImageFont, ImageOps


FOLDER_PREFIX = "https://t.me/addlist/"


def _font(size: int, bold: bool = False):
    candidates = (
        [r"C:\Windows\Fonts\segoeuib.ttf", r"C:\Windows\Fonts\arialbd.ttf"]
        if bold
        else [r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\arial.ttf"]
    ) + [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    ]
    for raw in candidates:
        path = Path(raw)
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size=size)
            except Exception:
                pass
    return ImageFont.load_default()


def _validate_folder_url(url: str) -> str:
    value = str(url or "").strip()
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.netloc.lower() not in {"t.me", "telegram.me"}:
        raise ValueError("NEXUS folder URL must be an HTTPS Telegram URL")
    if not parsed.path.startswith("/addlist/"):
        raise ValueError("NEXUS folder URL must be a Telegram addlist URL")
    return value


def build_nexus_folder_qr(folder_url: str) -> bytes:
    """Return a scan-safe NEXUS-branded PNG for the official Telegram folder."""
    folder_url = _validate_folder_url(folder_url)

    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_H,
        box_size=16,
        border=4,
    )
    qr.add_data(folder_url)
    qr.make(fit=True)

    monochrome = qr.make_image(fill_color="black", back_color="white").convert("L")
    mask = ImageOps.invert(monochrome)
    w, h = monochrome.size

    # Vertical magenta -> violet -> blue gradient inspired by the supplied QR.
    gradient = Image.new("RGB", (w, h), "white")
    gp = gradient.load()
    top = (211, 81, 154)
    bottom = (76, 157, 245)
    for y in range(h):
        t = y / max(1, h - 1)
        color = tuple(int(top[i] * (1 - t) + bottom[i] * t) for i in range(3))
        for x in range(w):
            gp[x, y] = color
    colored_qr = Image.composite(gradient, Image.new("RGB", (w, h), "white"), mask)

    canvas = Image.new("RGB", (1080, 1080), "white")
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((28, 28, 1052, 1052), radius=58, outline=(225, 229, 236), width=4)
    draw.text((540, 68), "NEXUS", font=_font(56, True), fill=(17, 24, 39), anchor="ma")
    draw.text((540, 132), "OFFICIAL TELEGRAM ECOSYSTEM", font=_font(22, True), fill=(107, 114, 128), anchor="ma")

    max_qr = 820
    scale = min(max_qr / colored_qr.width, max_qr / colored_qr.height)
    qr_size = max(1, int(colored_qr.width * scale))
    colored_qr = colored_qr.resize((qr_size, qr_size), Image.Resampling.NEAREST)
    x = (1080 - qr_size) // 2
    y = 190
    canvas.paste(colored_qr, (x, y))

    draw.text((540, 1030), "SCAN OR TAP ‘ENTER NEXUS’ IN THE BOT", font=_font(20, True), fill=(107, 114, 128), anchor="mm")

    out = io.BytesIO()
    canvas.save(out, format="PNG", optimize=True)
    return out.getvalue()
'''
write("app/portal.py", portal_py)


# ---------------------------------------------------------------------------
# 6) Channel routing policy: educational/editorial evergreen content goes to
#    NEXUS Academy; live analysis/news stays in the Public channel.
# ---------------------------------------------------------------------------
routing_py = r'''from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


ACADEMY_CATEGORY_KEYS = frozenset({
    "ict_education",
    "quick_tip",
    "tools",
    "risk",
    "trade_review",
    "mindset",
})


@dataclass(frozen=True)
class ChannelDestination:
    key: str
    label_fa: str
    chat_id: int | str
    channel_url: str


def route_key_for_category(category_key: str) -> str:
    return "academy" if str(category_key or "").strip() in ACADEMY_CATEGORY_KEYS else "public"


def route_label_fa(category_key: str) -> str:
    return "NEXUS Academy" if route_key_for_category(category_key) == "academy" else "کانال عمومی NEXUS"


def _public_username_target(url: str) -> str | None:
    value = str(url or "").strip().rstrip("/")
    if not value:
        return None
    try:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() not in {"t.me", "telegram.me"}:
            return None
        slug = parsed.path.strip("/")
        if not slug or slug.startswith("+") or "/" in slug:
            return None
        return "@" + slug.lstrip("@")
    except Exception:
        return None


def resolve_channel_destination(settings, category_key: str) -> ChannelDestination:
    route = route_key_for_category(category_key)
    if route == "public":
        return ChannelDestination(
            key="public",
            label_fa="کانال عمومی NEXUS",
            chat_id=settings.public_channel_id,
            channel_url=settings.public_channel_url,
        )

    raw_id = str(getattr(settings, "academy_channel_id", "") or "").strip()
    url = str(getattr(settings, "academy_channel_url", "") or "").strip()
    target: int | str | None = None
    if raw_id:
        try:
            target = int(raw_id)
        except ValueError:
            target = raw_id
    if target is None:
        target = _public_username_target(url)

    if target is None:
        raise RuntimeError(
            "ACADEMY_CHANNEL_ID or a public ACADEMY_CHANNEL_URL is required before direct educational publishing"
        )
    if not url:
        raise RuntimeError("ACADEMY_CHANNEL_URL is required to create traceable Telegram post permalinks")

    return ChannelDestination(
        key="academy",
        label_fa="NEXUS Academy",
        chat_id=target,
        channel_url=url,
    )
'''
write("app/content/routing.py", routing_py)


# ---------------------------------------------------------------------------
# 7) Route Agentic content at publish time.
# ---------------------------------------------------------------------------
pipeline_py = r'''from __future__ import annotations

import logging
from pathlib import Path

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import BufferedInputFile

from ..config import settings as core_settings
from . import repository
from .agents import (
    BrandGuardianAgent,
    CreativeDirectorAgent,
    ResearchAgent,
    TopicPlannerAgent,
    WriterAgent,
)
from .ai_client import OpenAICompatibleTextClient
from .editorial import ChannelEditorAgent
from .image_client import GeminiImageClient
from .routing import resolve_channel_destination, route_key_for_category, route_label_fa
from .settings import content_settings
from .taxonomy import public_post_link
from .visuals import render_post_card

log = logging.getLogger("nexus-content-pipeline")


class ContentPipeline:
    def __init__(self):
        ai = OpenAICompatibleTextClient(
            content_settings.ai_api_key,
            content_settings.text_model,
            content_settings.ai_base_url,
            content_settings.ai_provider,
        )
        self.image_ai = GeminiImageClient(
            content_settings.ai_api_key,
            content_settings.image_model,
            content_settings.image_ai_enabled,
        )
        self.planner = TopicPlannerAgent()
        self.researcher = ResearchAgent()
        self.writer = WriterAgent(ai)
        self.creative_director = CreativeDirectorAgent()
        self.guardian = BrandGuardianAgent()
        self.editor = ChannelEditorAgent()
        self.assets_dir = Path(__file__).resolve().parents[2] / "assets" / "content_generated"
        self.assets_dir.mkdir(parents=True, exist_ok=True)

    async def run_day(self, bot: Bot, scheduled_date: str) -> bool:
        if not repository.claim_day(scheduled_date):
            return False

        draft = None
        try:
            topic = self.planner.choose(scheduled_date)
            grounded = self.researcher.research(topic)
            draft = await self.writer.write(scheduled_date, grounded)
            visual_brief = self.creative_director.direct(draft)
            route_key = route_key_for_category(draft.category_key)
            draft.metadata["channel_route"] = route_key

            ok, errors = self.guardian.validate(draft)
            if not ok:
                raise RuntimeError("brand/quality gate rejected draft: " + "; ".join(errors))

            repository.registry_upsert(
                post_id=draft.post_id,
                scheduled_date=draft.scheduled_date,
                category_key=draft.category_key,
                template_key=draft.template_key,
                topic_slug=draft.topic_slug,
                title=draft.title,
                priority=draft.priority,
                hashtags=draft.hashtags,
                source_urls=draft.source_urls,
                status="proposed",
            )

            decision = self.editor.evaluate(
                scheduled_date=draft.scheduled_date,
                category_key=draft.category_key,
                priority=draft.priority,
            )
            if not decision.allowed:
                repository.mark_skipped(scheduled_date, decision.reason)
                repository.registry_mark_skipped(draft.post_id, decision.reason)
                log.info("content skipped by editor post_id=%s reason=%s", draft.post_id, decision.reason)
                return False

            draft.related_links = repository.related_published(
                draft.category_key,
                draft.post_id,
                limit=2,
            )

            hero_image = await self.image_ai.generate(visual_brief.prompt)
            image_bytes = render_post_card(draft, hero_image_bytes=hero_image)
            image_path = self.assets_dir / f"{scheduled_date}_{draft.topic_slug}.png"
            image_path.write_bytes(image_bytes)
            caption = draft.caption()

            repository.save_draft(
                scheduled_date,
                draft.template_key,
                draft.topic_slug,
                draft.title,
                caption,
                str(image_path),
            )
            repository.registry_upsert(
                post_id=draft.post_id,
                scheduled_date=draft.scheduled_date,
                category_key=draft.category_key,
                template_key=draft.template_key,
                topic_slug=draft.topic_slug,
                title=draft.title,
                priority=draft.priority,
                hashtags=draft.hashtags,
                source_urls=draft.source_urls,
                status="ready",
            )

            if content_settings.approval_mode:
                preview_message_id: int | None = None
                preview_caption = (
                    f"🧭 <b>مقصد انتشار:</b> {route_label_fa(draft.category_key)}\n\n" + caption
                )
                for admin_id in core_settings.admin_ids:
                    photo = BufferedInputFile(image_bytes, filename=image_path.name)
                    message = await bot.send_photo(
                        admin_id,
                        photo=photo,
                        caption=preview_caption[:1024],
                        parse_mode=ParseMode.HTML,
                        protect_content=False,
                    )
                    if preview_message_id is None:
                        preview_message_id = int(message.message_id)
                repository.mark_previewed(scheduled_date, preview_message_id)
                repository.registry_mark_previewed(draft.post_id, preview_message_id)
                return True

            destination = resolve_channel_destination(core_settings, draft.category_key)
            photo = BufferedInputFile(image_bytes, filename=image_path.name)
            message = await bot.send_photo(
                destination.chat_id,
                photo=photo,
                caption=caption,
                parse_mode=ParseMode.HTML,
                protect_content=content_settings.protect_content,
            )
            message_id = int(message.message_id)
            permalink = public_post_link(destination.channel_url, message_id)

            final_caption = draft.caption(permalink=permalink)
            if final_caption != caption:
                try:
                    await bot.edit_message_caption(
                        chat_id=destination.chat_id,
                        message_id=message_id,
                        caption=final_caption,
                        parse_mode=ParseMode.HTML,
                    )
                except Exception as exc:
                    log.warning("could not append Telegram permalink to %s: %s", draft.post_id, exc)

            repository.mark_published(scheduled_date, message_id)
            repository.registry_mark_published(draft.post_id, message_id, permalink)
            log.info(
                "content published post_id=%s route=%s chat=%s",
                draft.post_id,
                destination.key,
                destination.chat_id,
            )
            return True
        except Exception as exc:
            repository.mark_failed(scheduled_date, str(exc))
            if draft is not None and draft.post_id:
                repository.registry_mark_failed(draft.post_id, str(exc))
            log.exception("daily content pipeline failed for %s", scheduled_date)
            return False
'''
write("app/content/pipeline.py", pipeline_py)


# ---------------------------------------------------------------------------
# 8) Main runtime: improved home copy + QR callback. Exact anchor-based edits
#    avoid touching unrelated trading / AutoTrade logic in the large main.py.
# ---------------------------------------------------------------------------
replace_once(
    "app/main.py",
    "from .config import settings\nfrom . import db\n",
    "from .config import settings\nfrom .portal import build_nexus_folder_qr\nfrom . import db\n",
)

replace_once(
    "app/main.py",
    '        tr(lang, "<b>⚡ NEXUS</b>\\n\\nاز این بخش می‌توانید سیگنال‌ها، معاملات خودکار و حساب کاربری خود را مدیریت کنید.\\n\\nسرویس موردنظر را انتخاب کنید:", "<b>⚡ NEXUS</b>\\n\\nManage signals, Auto Trade and your account from here.\\n\\nSelect a service:"),\n',
    '        tr(\n'
    '            lang,\n'
    '            "<b>⚡ NEXUS | مرکز دسترسی</b>\\n\\nتمام کانال‌ها و سرویس‌های NEXUS از یک نقطه در دسترس شما هستند.\\n\\n🚀 <b>ورود به NEXUS</b> فولدر رسمی تلگرام را باز می‌کند؛ کانال عمومی، Academy، Free و VIP در همان فولدر قرار می‌گیرند.\\n\\nبرای مدیریت اشتراک، سیگنال‌ها، حساب یا راهنما از گزینه‌های پایین استفاده کنید.",\n'
    '            "<b>⚡ NEXUS | Access Center</b>\\n\\nAll NEXUS channels and services are available from one gateway.\\n\\n🚀 <b>Enter NEXUS</b> opens the official Telegram folder containing Public, Academy, Free and VIP channels.\\n\\nUse the options below to manage subscriptions, signals, account and guides.",\n'
    '        ),\n',
)

replace_once(
    "app/main.py",
    '        text = tr(lang, "<b>⚡ NEXUS</b>\\n\\nمنوی اصلی", "<b>⚡ NEXUS</b>\\n\\nMain Menu")\n',
    '        text = tr(lang, "<b>⚡ NEXUS | مرکز دسترسی</b>\\n\\nبرای ورود به اکوسیستم NEXUS از دکمه «ورود به NEXUS» استفاده کنید.", "<b>⚡ NEXUS | Access Center</b>\\n\\nUse “Enter NEXUS” to open the official ecosystem folder.")\n',
)

menu_anchor = '''@router.callback_query(F.data == "main")
async def menu(cb: CallbackQuery, bot: Bot, state: FSMContext):
    await state.clear()
    if not await gated(cb, bot):
        return
    await cb.answer()
    await show_main(bot, cb.from_user.id, cb.message.chat.id)


'''
qr_handler = menu_anchor + '''@router.callback_query(F.data == "nexus_folder_qr")
async def nexus_folder_qr(cb: CallbackQuery, bot: Bot):
    if not await gated(cb, bot):
        return
    lang = get_lang(cb.from_user.id)
    await cb.answer()
    try:
        qr_bytes = build_nexus_folder_qr(settings.nexus_folder_url)
    except Exception as exc:
        log.exception("could not build NEXUS folder QR")
        await cb.answer(tr(lang, "ساخت QR موقتاً ناموفق بود.", "Could not generate the QR right now."), show_alert=True)
        return

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=tr(lang, "🚀 باز کردن فولدر NEXUS", "🚀 Open NEXUS Folder"),
            url=settings.nexus_folder_url,
        )],
        [InlineKeyboardButton(
            text=tr(lang, "🏠 بازگشت به مرکز دسترسی", "🏠 Back to Access Center"),
            callback_data="main",
        )],
    ])
    await bot.send_photo(
        cb.from_user.id,
        photo=BufferedInputFile(qr_bytes, filename="NEXUS_Official_Folder_QR.png"),
        caption=tr(
            lang,
            "<b>📱 فولدر رسمی NEXUS</b>\\n\\nبرای ورود مستقیم روی دکمه زیر بزنید؛ یا QR را با دستگاه دیگر اسکن کنید.\\n\\n<code>https://t.me/addlist/ASXi4-91edg2YzA8</code>",
            "<b>📱 Official NEXUS Folder</b>\\n\\nTap the button below to open it directly, or scan the QR from another device.\\n\\n<code>https://t.me/addlist/ASXi4-91edg2YzA8</code>",
        ),
        reply_markup=markup,
        parse_mode=ParseMode.HTML,
        protect_content=False,
    )


'''
text = read("app/main.py")
if "async def nexus_folder_qr(" not in text:
    if menu_anchor not in text:
        raise RuntimeError("Main menu callback anchor not found in app/main.py")
    write("app/main.py", text.replace(menu_anchor, qr_handler, 1))


# ---------------------------------------------------------------------------
# 9) Tests for the new gateway, QR and routing contract.
# ---------------------------------------------------------------------------
test_py = r'''from __future__ import annotations

from app import ui
from app.config import settings
from app.content.routing import ACADEMY_CATEGORY_KEYS, route_key_for_category
from app.portal import build_nexus_folder_qr


def _buttons(markup):
    return [button for row in markup.inline_keyboard for button in row]


def test_main_menu_has_official_nexus_folder_as_primary_gateway():
    markup = ui.main_menu("fa")
    first = markup.inline_keyboard[0][0]
    assert first.text == "🚀 ورود به NEXUS"
    assert first.url == "https://t.me/addlist/ASXi4-91edg2YzA8"
    assert first.url == settings.nexus_folder_url


def test_main_menu_exposes_qr_action_and_keeps_management_actions():
    buttons = _buttons(ui.main_menu("fa"))
    callbacks = {button.callback_data for button in buttons if button.callback_data}
    assert "nexus_folder_qr" in callbacks
    assert {"client_signals", "vip", "account", "guide_hub", "support", "change_language"} <= callbacks


def test_nexus_folder_qr_is_a_real_png():
    data = build_nexus_folder_qr("https://t.me/addlist/ASXi4-91edg2YzA8")
    assert data.startswith(b"\\x89PNG\\r\\n\\x1a\\n")
    assert len(data) > 10_000


def test_education_family_routes_to_academy():
    assert {"ict_education", "quick_tip", "tools", "risk", "trade_review", "mindset"} <= ACADEMY_CATEGORY_KEYS
    for key in ACADEMY_CATEGORY_KEYS:
        assert route_key_for_category(key) == "academy"


def test_news_and_daily_analysis_stay_public():
    for key in ("daily_analysis", "market_news", "important_news", "news_alert"):
        assert route_key_for_category(key) == "public"
'''
write("tests/test_nexus_hub_academy.py", test_py)


# ---------------------------------------------------------------------------
# 10) Deployment note / contract for the final VPS release.
# ---------------------------------------------------------------------------
doc = '''# NEXUS Central Hub + Academy Routing\n\n## Customer UI\n\nThe primary button is now **Enter NEXUS** and points to the official Telegram folder:\n\n`https://t.me/addlist/ASXi4-91edg2YzA8`\n\nThe bot also generates a branded, scan-safe QR from this URL on demand.\n\n## Channel routing\n\nAcademy:\n- ICT education\n- Quick Tips\n- Tools / indicators\n- Risk management\n- Trade reviews\n- Trader mindset\n\nPublic:\n- Daily analysis\n- Market news\n- Important / high-impact news\n- Economic-calendar alerts\n\nBefore direct production publishing, set both:\n\n```env\nACADEMY_CHANNEL_ID=-100...\nACADEMY_CHANNEL_URL=https://t.me/...\n```\n\nApproval mode can run without those values because previews go only to admins. Direct educational publication intentionally fails closed if Academy is not configured, preventing accidental education posts from going to the Public channel.\n'''
write("docs/NEXUS_HUB_ACADEMY_ROUTING_FA.md", doc)

print("NEXUS hub + Academy patch applied successfully")
