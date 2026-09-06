from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LessonSpec:
    course_key: str
    module_key: str
    lesson_number: int
    topic_slug: str
    title_fa: str
    primary_keyword: str
    objective_fa: str
    exercise_prompt_fa: str


CURRICULUM: tuple[LessonSpec, ...] = (
    LessonSpec("ict_foundations", "market_structure", 1, "market_structure", "ساختار بازار در سبک ICT", "ساختار بازار ICT", "تشخیص روند، رنج و نقاط تغییر ساختار.", "روی یک نمودار یک‌ساعته، آخرین سقف و کف معتبر را مشخص کن."),
    LessonSpec("ict_foundations", "liquidity", 2, "liquidity", "نقدینگی در ICT", "نقدینگی در ICT", "شناخت نقدینگی سمت خرید و سمت فروش و دلیل اهمیت آن.", "دو ناحیه‌ای را پیدا کن که بالای سقف‌ها یا زیر کف‌ها نقدینگی جمع شده است."),
    LessonSpec("ict_foundations", "fvg", 3, "fvg", "شکاف ارزش منصفانه چیست؟", "FVG در ICT", "تشخیص شکاف ارزش منصفانه و تفاوت آن با حرکت عادی قیمت.", "یک FVG معتبر پیدا کن و مشخص کن هنوز پر نشده یا شده است."),
    LessonSpec("ict_foundations", "order_block", 4, "order_block", "بلوک سفارش در ICT", "Order Block در ICT", "تشخیص بلوک سفارش باکیفیت در کنار جابه‌جایی قدرتمند قیمت.", "یک بلوک سفارش پیدا کن که بعد از آن حرکت قدرتمند شکل گرفته باشد."),
    LessonSpec("ict_foundations", "mss", 5, "mss", "تغییر ساختار بازار", "MSS در ICT", "شناخت تغییر ساختار بعد از جمع‌آوری نقدینگی.", "نمونه‌ای از جمع‌آوری نقدینگی و سپس تغییر ساختار را روی نمودار پیدا کن."),
    LessonSpec("ict_foundations", "premium_discount", 6, "premium_discount", "ناحیه پرمیوم و دیسکانت", "Premium Discount ICT", "تقسیم محدوده معاملاتی به نیمه پرمیوم و دیسکانت.", "یک dealing range بساز و نیمه بالا و پایین آن را مشخص کن."),
    LessonSpec("ict_foundations", "session_liquidity", 7, "session_liquidity", "نقدینگی سشن‌ها", "نقدینگی سشن معاملاتی", "شناخت رفتار نقدینگی آسیا، لندن و نیویورک.", "سقف و کف سشن آسیا را علامت بزن و واکنش لندن به آن را بررسی کن."),
    LessonSpec("ict_foundations", "entry_model", 8, "confirmation", "مدل ورود با تأیید ساختاری", "ورود با تایید ICT", "ترکیب جمع‌آوری نقدینگی، تغییر ساختار، جابه‌جایی و بازآزمایی.", "یک ستاپ کامل پیدا کن که هر چهار مرحله را داشته باشد."),
    LessonSpec("risk", "fixed_risk", 9, "fixed_risk", "ریسک ثابت در هر معامله", "مدیریت ریسک معامله", "تعریف ریسک ثابت و جلوگیری از افزایش حجم احساسی.", "اگر سرمایه ۱۰۰۰ دلار و ریسک ۱٪ باشد، حداکثر زیان مجاز را حساب کن."),
    LessonSpec("mindset", "execution", 10, "discipline", "انضباط در اجرای پلن", "انضباط معاملاتی", "تفکیک تحلیل درست از اجرای درست و کنترل تصمیم‌های لحظه‌ای.", "سه قانونی را بنویس که قبل از هر ورود باید تیک بخورند."),
)


def lesson_for_index(index: int) -> LessonSpec:
    if not CURRICULUM:
        raise RuntimeError("academy curriculum is empty")
    return CURRICULUM[index % len(CURRICULUM)]
