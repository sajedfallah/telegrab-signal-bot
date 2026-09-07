from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto

from app.config import settings as core_settings
from app.content.agents import BrandGuardianAgent, ResearchAgent, WriterAgent
from app.content.ai_client import OpenAICompatibleTextClient
from app.content.models import ContentDraft, Topic
from app.content.routing import resolve_channel_destination
from app.content.settings import content_settings
from app.content.taxonomy import build_hashtags, make_post_id, tracking_hashtag

from . import repository
from .curriculum import LessonSpec, lesson_for_index
from .settings import academy_settings
from .visuals import render_academy_slide


GUIDES: dict[str, dict[str, object]] = {
    "market_structure": {
        "definition": "ساختار بازار یعنی ترتیب و رابطه سقف‌ها و کف‌های معتبر. در یک ساختار صعودی معمولاً سقف بالاتر و کف بالاتر می‌بینیم؛ در ساختار نزولی سقف پایین‌تر و کف پایین‌تر شکل می‌گیرد. اگر این توالی واضح نباشد، بازار می‌تواند در حالت رنج یا گذار باشد.",
        "why": "قبل از پیدا کردن FVG، بلوک سفارش یا مدل ورود باید بدانیم قیمت در چه ساختاری حرکت می‌کند؛ چون همان ناحیه در ساختار صعودی و نزولی معنای متفاوتی دارد.",
        "how": ["ابتدا آخرین سقف و کف واضح یک‌ساعته را علامت بزن.", "ببین شکست اخیر ادامه روند بوده یا تغییر رفتار.", "روی پانزده‌دقیقه فقط نواحی هم‌جهت با ساختار اصلی را اولویت بده."],
        "mistake": "هر نوسان کوچک را سقف یا کف ساختاری حساب نکن. نقطه ساختاری باید در حرکت بعدی بازار نقش قابل‌مشاهده داشته باشد.",
        "example": "اگر قیمت یک سقف معتبر را بشکند، سپس بالاتر از کف قبلی کف جدید بسازد و دوباره سقف بالاتری ثبت کند، ساختار صعودی منظم‌تر شده است.",
        "quiz": "در یک ساختار صعودی سالم، کدام توالی مهم‌تر است؟",
        "options": ["سقف بالاتر + کف بالاتر", "سقف پایین‌تر + کف پایین‌تر", "فقط تعداد کندل‌های سبز"],
        "correct": 0,
    },
    "liquidity": {
        "definition": "نقدینگی به نواحی‌ای گفته می‌شود که سفارش‌های توقف یا سفارش‌های معلق زیادی پیرامون آن‌ها جمع شده‌اند؛ مثل بالای سقف‌های برابر یا زیر کف‌های برابر. قیمت اغلب برای پر کردن سفارش‌ها به این نواحی واکنش نشان می‌دهد.",
        "why": "شناخت محل نقدینگی کمک می‌کند بفهمیم بازار احتمالاً کجا سفارش جمع می‌کند و چرا یک حرکت ناگهانی ممکن است قبل از برگشت رخ دهد.",
        "how": ["سقف‌های برابر و کف‌های برابر را پیدا کن.", "سقف و کف روز قبل و سشن‌ها را علامت بزن.", "بعد از جمع‌آوری نقدینگی منتظر تغییر ساختار یا حرکت قدرتمند بمان."],
        "mistake": "صرف لمس نقدینگی سیگنال ورود نیست؛ بدون تأیید ساختاری می‌تواند فقط ادامه حرکت باشد.",
        "example": "قیمت بالای دو سقف نزدیک به هم می‌رود، سفارش‌های خرید را جمع می‌کند و سپس با شکست ساختار کوتاه‌مدت برمی‌گردد.",
        "quiz": "کدام ناحیه معمولاً محل واضح‌تری برای نقدینگی است؟",
        "options": ["بالای سقف‌های برابر", "وسط یک رنج بدون سطح", "هر کندل بزرگ"],
        "correct": 0,
    },
    "fvg": {
        "definition": "شکاف ارزش منصفانه یک عدم‌تعادل سه‌کندلی است که در حرکت سریع قیمت ایجاد می‌شود؛ جایی که بین محدوده کندل اول و سوم هم‌پوشانی کامل وجود ندارد.",
        "why": "FVG می‌تواند نشان دهد قیمت با شتاب از یک ناحیه عبور کرده و در بازگشت، همان عدم‌تعادل به‌عنوان ناحیه واکنش بررسی شود.",
        "how": ["سه کندل متوالی را بررسی کن.", "فاصله بین بیشینه/کمینه کندل اول و سوم را مشخص کن.", "فقط FVG هم‌جهت با ساختار و نزدیک ناحیه مهم را جدی‌تر بگیر."],
        "mistake": "هر فاصله یا کندل بزرگ را FVG ننام؛ ساختار سه‌کندلی و زمینه بازار ضروری است.",
        "example": "بعد از جمع‌آوری نقدینگی، یک حرکت قدرتمند صعودی ایجاد می‌شود و بین کندل اول و سوم شکاف باقی می‌ماند؛ بازگشت به آن ناحیه می‌تواند برای تأیید بررسی شود.",
        "quiz": "FVG معتبر معمولاً از چه ساختاری تشکیل می‌شود؟",
        "options": ["عدم‌تعادل سه‌کندلی", "یک کندل دوجی", "دو میانگین متحرک"],
        "correct": 0,
    },
    "order_block": {
        "definition": "بلوک سفارش ناحیه‌ای است که آخرین کندل یا مجموعه کندل مخالف قبل از یک جابه‌جایی قدرتمند و شکست ساختار را در بر می‌گیرد.",
        "why": "وقتی بلوک سفارش با ساختار، نقدینگی و جابه‌جایی هم‌راستا باشد، می‌تواند ناحیه‌ای برای بررسی واکنش قیمت در بازگشت باشد.",
        "how": ["ابتدا شکست ساختار و حرکت قدرتمند را تأیید کن.", "آخرین کندل مخالف قبل از حرکت را مشخص کن.", "اعتبار ناحیه را با نقدینگی و FVG اطرافش بسنج."],
        "mistake": "هر کندل مخالف قبل از حرکت، بلوک سفارش باکیفیت نیست؛ باید نتیجه ساختاری قابل‌مشاهده داشته باشد.",
        "example": "پس از جمع‌آوری نقدینگی فروش، آخرین کندل نزولی قبل از حرکت صعودی که سقف مهم را می‌شکند می‌تواند بلوک سفارش صعودی باشد.",
        "quiz": "برای اعتبار یک بلوک سفارش کدام مورد مهم‌تر است؟",
        "options": ["جابه‌جایی و شکست ساختار بعد از آن", "رنگ کندل به‌تنهایی", "تعداد اندیکاتورها"],
        "correct": 0,
    },
    "mss": {
        "definition": "تغییر ساختار بازار زمانی رخ می‌دهد که پس از یک حرکت یا جمع‌آوری نقدینگی، قیمت یک نقطه ساختاری مهم در جهت مخالف را با قدرت می‌شکند.",
        "why": "MSS به ما کمک می‌کند بین یک واکنش ساده و آغاز تغییر رفتار کوتاه‌مدت بازار تفاوت قائل شویم.",
        "how": ["ابتدا نقدینگی یا نقطه محرک را پیدا کن.", "شکست واضح نقطه ساختاری مخالف را ببین.", "به کیفیت جابه‌جایی بعد از شکست توجه کن."],
        "mistake": "شکست یک میکروسوینگ کوچک بدون جابه‌جایی را MSS قطعی در نظر نگیر.",
        "example": "قیمت بالای سقف قبلی نقدینگی می‌گیرد و سپس آخرین کف کوتاه‌مدت را با حرکت نزولی قوی می‌شکند.",
        "quiz": "MSS قوی معمولاً با چه چیزی بهتر تأیید می‌شود؟",
        "options": ["شکست ساختار همراه حرکت قدرتمند", "فقط یک سایه کندل", "افزایش تعداد کندل‌ها"],
        "correct": 0,
    },
}

DEFAULT_GUIDE = {
    "definition": "این مفهوم یکی از اجزای چارچوب ICT برای خواندن منظم رفتار قیمت است و باید همیشه در کنار ساختار بازار، نقدینگی و مدیریت ریسک بررسی شود.",
    "why": "هدف این درس تبدیل مفهوم نظری به یک معیار مشخص روی نمودار است تا تصمیم‌گیری از حالت حدس خارج شود.",
    "how": ["مفهوم را روی تایم‌فریم بالاتر پیدا کن.", "زمینه و جهت ساختار را مشخص کن.", "برای ورود، تأیید تایم‌فریم پایین‌تر را منتظر بمان."],
    "mistake": "استفاده از مفهوم به‌صورت جدا از زمینه بازار، یکی از خطاهای رایج است.",
    "example": "یک نمونه واقعی روی نمودار پیدا کن و قبل و بعد از شکل‌گیری مفهوم را مقایسه کن.",
    "quiz": "بهترین روش استفاده از این مفهوم چیست؟",
    "options": ["همراه ساختار و تأیید", "به‌تنهایی و بدون زمینه", "فقط بر اساس رنگ کندل"],
    "correct": 0,
}


class AcademyMentorAgent:
    def __init__(self) -> None:
        ai = OpenAICompatibleTextClient(content_settings.ai_api_key, content_settings.text_model,
                                        content_settings.ai_base_url, content_settings.ai_provider)
        self.researcher = ResearchAgent()
        self.writer = WriterAgent(ai)
        self.guardian = BrandGuardianAgent()
        self.assets_dir = Path(__file__).resolve().parents[2] / "assets" / "academy_generated"
        self.assets_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _guide(spec: LessonSpec) -> dict[str, object]:
        return dict(DEFAULT_GUIDE | GUIDES.get(spec.topic_slug, {}))

    @classmethod
    def _topic(cls, spec: LessonSpec) -> Topic:
        guide = cls._guide(spec)
        return Topic(slug=spec.topic_slug, template_key="ict_education", title_fa=spec.title_fa,
                     definition_fa=str(guide["definition"]), key_points_fa=tuple(guide["how"]),
                     example_fa=str(guide["example"]), level="foundation")

    @staticmethod
    def _seo(spec: LessonSpec) -> dict[str, object]:
        return {"primary_keyword": spec.primary_keyword,
                "secondary_keywords": [spec.title_fa, "آموزش ICT", "آموزش معامله‌گری"],
                "meta_description": f"آموزش کاربردی {spec.primary_keyword} با تعریف، روش تشخیص، اشتباه رایج، مثال و تمرین در NEXUS Academy.",
                "slug": f"academy-{spec.topic_slug}"}

    @classmethod
    def _caption(cls, draft: ContentDraft, spec: LessonSpec) -> str:
        g = cls._guide(spec)
        how = "\n".join(f"• {x}" for x in list(g["how"])[:3])
        return (
            f"<b>📘 NEXUS Academy | درس {spec.lesson_number}</b>\n\n"
            f"<b>{draft.title}</b>\n\n"
            f"<b>تعریف ساده</b>\n{g['definition']}\n\n"
            f"<b>چرا مهم است؟</b>\n{g['why']}\n\n"
            f"<b>روش تشخیص روی نمودار</b>\n{how}\n\n"
            f"<b>⚠️ اشتباه رایج</b>\n{g['mistake']}\n\n"
            f"<b>مثال</b>\n{g['example']}\n\n"
            f"<b>🧩 تمرین</b>\n{g['quiz']}\n\n"
            "هدف امروز: مفهوم را بتوانی بدون کمک روی نمودار تشخیص بدهی."
        )[:3600]

    async def build_for_day(self, day: date) -> int:
        day_key = day.isoformat(); existing = repository.get_by_day(day_key)
        if existing and str(existing["status"]) in {"ready","previewed","published"}:
            return int(existing["id"])
        spec = lesson_for_index(repository.next_sequence_index()); guide = self._guide(spec)
        topic = self.researcher.research(self._topic(spec)); draft = await self.writer.write(day_key, topic)
        draft.definition = str(guide["definition"]); draft.key_points = list(guide["how"])
        draft.example = str(guide["example"]); draft.category_key = "ict_education"
        draft.post_id = make_post_id("ict_education", day_key, spec.topic_slug)
        draft.hashtags = build_hashtags("ict_education", spec.topic_slug,
                                        " ".join([draft.title,draft.definition,*draft.key_points,draft.example]))
        draft.hashtags.append(tracking_hashtag(draft.post_id)); draft.cta = "تمرین را پاسخ بده و بازخورد فوری بگیر."
        ok, errors = self.guardian.validate(draft)
        if not ok: raise RuntimeError("academy quality gate rejected lesson: " + "; ".join(errors))

        slides = [
            render_academy_slide(title=draft.title, slug=spec.topic_slug, step="01 · مفهوم",
                                 body=str(guide["definition"]), bullets=[str(guide["why"])], note="اول مفهوم را بفهم؛ بعد دنبال ستاپ بگرد."),
            render_academy_slide(title="چطور روی نمودار تشخیصش بدهیم؟", slug=spec.topic_slug, step="02 · تشخیص",
                                 body=str(guide["example"]), bullets=[str(x) for x in list(guide["how"])], note=f"اشتباه رایج: {guide['mistake']}"),
            render_academy_slide(title="تمرین امروز", slug=spec.topic_slug, step="03 · تمرین",
                                 body=str(guide["quiz"]), bullets=[str(x) for x in list(guide["options"])], note="پاسخت را از دکمه‌های زیر پست ثبت کن."),
        ]
        image_paths=[]
        for idx,data in enumerate(slides[:max(3, academy_settings.image_count)], start=1):
            path=self.assets_dir/f"{day_key}_{spec.topic_slug}_v2_{idx}.png"; path.write_bytes(data); image_paths.append(str(path))

        seo=self._seo(spec)
        return repository.save_ready(scheduled_date=day_key, course_key=spec.course_key, module_key=spec.module_key,
            lesson_number=spec.lesson_number, topic_slug=spec.topic_slug, title=draft.title,
            primary_keyword=str(seo["primary_keyword"]), secondary_keywords=list(seo["secondary_keywords"]),
            meta_description=str(seo["meta_description"]), slug=str(seo["slug"]), caption=self._caption(draft,spec),
            image_paths=image_paths, exercise_prompt=str(guide["quiz"]), exercise_options=[str(x) for x in list(guide["options"])],
            correct_option=int(guide["correct"]))

    async def preview(self, bot: Bot, day: date) -> bool:
        await self.build_for_day(day); row=repository.get_by_day(day.isoformat())
        if row is None: return False
        images=json.loads(row["image_paths_json"] or "[]"); caption=str(row["caption"] or "")
        for admin_id in core_settings.admin_ids:
            media=[]
            for index,path in enumerate(images):
                data=Path(path).read_bytes(); media.append(InputMediaPhoto(media=BufferedInputFile(data,filename=Path(path).name),
                    caption=caption if index==0 else None, parse_mode=ParseMode.HTML if index==0 else None))
            if media: await bot.send_media_group(admin_id,media)
            await bot.send_message(admin_id,f"🧭 Academy V2 | درس {row['lesson_number']} آماده است.\n/academy_approve {day.isoformat()}\n/academy_rebuild {day.isoformat()}\n/academy_cancel {day.isoformat()}")
        repository.mark_previewed(day.isoformat()); return True

    async def publish(self, bot: Bot, day: date) -> bool:
        await self.build_for_day(day); row=repository.get_by_day(day.isoformat())
        if row is None or str(row["status"])=="cancelled": return False
        if str(row["status"])=="published": return True
        destination=resolve_channel_destination(core_settings,"ict_education")
        images=json.loads(row["image_paths_json"] or "[]"); caption=str(row["caption"] or "")
        media=[]
        for index,path in enumerate(images):
            data=Path(path).read_bytes(); media.append(InputMediaPhoto(media=BufferedInputFile(data,filename=Path(path).name),
                caption=caption if index==0 else None,parse_mode=ParseMode.HTML if index==0 else None))
        if not media: raise RuntimeError("academy lesson has no visual assets")
        send_kwargs={}
        if destination.message_thread_id: send_kwargs["message_thread_id"]=destination.message_thread_id
        sent=await bot.send_media_group(destination.chat_id,media,**send_kwargs); message_id=int(sent[0].message_id)
        lesson_id=int(row["id"]); options=json.loads(row["exercise_options_json"] or "[]")
        keyboard=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"{chr(65+idx)} · {label}",callback_data=f"academy_answer:{lesson_id}:{idx}")]
            for idx,label in enumerate(options[:3])])
        await bot.send_message(destination.chat_id,f"<b>🧠 آزمون کوتاه درس {row['lesson_number']}</b>\n\n{row['exercise_prompt']}\n\nیک گزینه را انتخاب کن؛ نتیجه همان لحظه ثبت می‌شود.",
                               parse_mode=ParseMode.HTML,reply_markup=keyboard,**send_kwargs)
        repository.mark_published(day.isoformat(),message_id); return True
