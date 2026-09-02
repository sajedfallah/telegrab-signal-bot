from __future__ import annotations

from copy import deepcopy

# v1 defaults. A snapshot is stored with each signal so future edits do not
# silently change the management rules of an already-published trade.
TRAILING_PROFILES: dict[str, dict] = {
    "NEXUS_TRAIL_01": {
        "name": "اسکالپینگ محافظه‌کارانه",
        "version": 2,
        "break_even_r": 1.0,
        "trail_step_r": 0.50,
        "lock_step_r": 0.30,
    },
    "NEXUS_TRAIL_02": {
        "name": "Step Profit Lock",
        "version": 2,
        "steps": [
            {"trigger_r": 1.0, "lock_r": 0.0},
            {"trigger_r": 2.0, "lock_r": 1.0},
            {"trigger_r": 3.0, "lock_r": 2.0},
        ],
    },
    "NEXUS_TRAIL_03": {
        "name": "Dynamic ATR",
        "version": 2,
        "atr_period": 14,
        "atr_multiplier": 2.0,
        "activation_r": 1.0,
    },
    "NEXUS_TRAIL_04": {
        "name": "ساختار بازار",
        "version": 2,
        "swing_left": 2,
        "swing_right": 2,
        "buffer_points": 0,
        "activation_r": 1.0,
    },
    "NEXUS_TRAIL_05": {
        "name": "VIP Runner",
        "version": 2,
        "tp1_close_pct": 30.0,
        "tp2_close_pct": 30.0,
        "runner_pct": 40.0,
        "break_even_after_tp1": True,
        "runner_mode": "MARKET_STRUCTURE_ATR_FALLBACK",
        "atr_period": 14,
        "atr_multiplier": 2.0,
    },
    "NEXUS_TRAIL_06": {
        "name": "Fast Scalping",
        "version": 2,
        "break_even_r": 0.50,
        "trail_step_r": 0.35,
        "lock_step_r": 0.25,
    },
    "NEXUS_TRAIL_07": {
        "name": "NEXUS Smart Hybrid",
        "version": 2,
        "break_even_r": 1.0,
        "tp1_close_pct": 30.0,
        "tp2_close_pct": 30.0,
        "runner_pct": 40.0,
        "runner_mode": "MARKET_STRUCTURE_ATR_FALLBACK",
        "atr_period": 14,
        "atr_multiplier": 2.0,
        "swing_left": 2,
        "swing_right": 2,
    },
}


def profile_snapshot(code: str) -> dict:
    normalized = str(code or "").strip().upper()
    if normalized not in TRAILING_PROFILES:
        raise ValueError(f"unknown trailing profile: {code}")
    data = deepcopy(TRAILING_PROFILES[normalized])
    data["code"] = normalized
    return data

TRAILING_GUIDE_FA: dict[str, str] = {
    "NEXUS_TRAIL_01": "اسکالپینگ محافظه‌کارانه. در آستانه سود مشخص به سر‌به‌سر می‌رود و سپس حدضرر را پله‌ای جلو می‌آورد؛ هر تغییر SL با نتیجه واقعی MT5 تأیید می‌شود.",
    "NEXUS_TRAIL_02": "قفل سود مرحله‌ای. در 1R، 2R و 3R حدضرر به‌ترتیب روی ورود، +1R و +2R قفل می‌شود؛ فقط حرکت‌های بهبوددهنده پذیرفته و نتیجه MT5 تأیید می‌شود.",
    "NEXUS_TRAIL_03": "تریلینگ پویا بر اساس ATR. فاصله حدضرر با نوسان بازار تغییر می‌کند و هر اصلاح فقط در جهت بهبود انجام می‌شود و نتیجه واقعی MT5 تأیید می‌گردد.",
    "NEXUS_TRAIL_04": "مدیریت ساختاری. در خرید استاپ به سمت کف نوسانی معتبر و در فروش به سمت سقف نوسانی معتبر حرکت می‌کند؛ استاپ هرگز عقب نمی‌رود و نتیجه تغییر در MT5 تأیید می‌شود.",
    "NEXUS_TRAIL_05": "VIP Runner. بخشی از حجم در TP1/TP2 با Partial Close تأییدشده بسته می‌شود و Runner با Structure/ATR مدیریت می‌شود؛ شکست Partial باعث Retry می‌شود و TP_DONE فقط پس از تأیید حجم ثبت می‌گردد.",
    "NEXUS_TRAIL_06": "اسکالپینگ تهاجمی. سر‌به‌سر در 0.5R و پله‌های 0.35R با قفل 0.25R؛ فقط در جهت بهبود و با تأیید نتیجه واقعی MT5.",
    "NEXUS_TRAIL_07": "هیبرید اصلی NEXUS: سر‌به‌سر (Break Even) + Partial Close تأییدشده + Structure با پشتیبان ATR. TP state فقط بعد از تأیید Execution تغییر می‌کند و خطای Partial با Backoff/Retry پیگیری می‌شود.",
}

TRAILING_GUIDE_EN: dict[str, str] = {
    "NEXUS_TRAIL_01": "Fast scalping protection. Moves to break-even at the configured profit threshold, then trails in steps to protect profit early.",
    "NEXUS_TRAIL_02": "Step-based profit locking. As the trade reaches configured R milestones, the stop moves from entry to progressively higher locked-profit levels.",
    "NEXUS_TRAIL_03": "Dynamic ATR trailing. Stop distance adapts to market volatility: wider in volatile conditions and tighter when volatility is low.",
    "NEXUS_TRAIL_04": "Market-structure management. BUY stops trail below valid swing lows; SELL stops trail above valid swing highs.",
    "NEXUS_TRAIL_05": "دونده وی‌آی‌پی. Closes portions at TP1/TP2 and leaves a runner managed by structure with پشتیبان ATR for larger moves.",
    "NEXUS_TRAIL_06": "Aggressive M1/scalping profile with faster break-even and tighter trailing than اسکالپینگ محافظه‌کارانه.",
    "NEXUS_TRAIL_07": "Main NEXUS hybrid: Break Even + Partial Close + ساختار بازار with پشتیبان ATR, designed to manage the trade through completion.",
}


def profile_guide(code: str, lang: str = "fa") -> str:
    normalized = str(code or "").strip().upper()
    profile = TRAILING_PROFILES.get(normalized)
    if not profile:
        raise ValueError(f"unknown trailing profile: {code}")
    detail = (TRAILING_GUIDE_FA if lang == "fa" else TRAILING_GUIDE_EN).get(normalized, "")
    return f"{normalized}\n{profile['name']}\n\n{detail}"
