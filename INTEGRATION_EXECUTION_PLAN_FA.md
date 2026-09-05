# NEXUS v0.6.5 — Integration Execution Plan

این سند قرارداد اجرایی شاخه یکپارچه جدید NEXUS است.

## مبنای Production

- Base: `feature/v065-integrated-release`
- Base SHA: `394ff3d45ff1bda3607c76d6daf9d630227569fb`

## قابلیت‌هایی که باید روی همین هسته یکپارچه شوند

1. Web Admin / User Portal
2. Telegram Mini App
3. طراحی جدید پنل Expert در MT5
4. Web → MT5 VPS chart capture → NEXUS flashcard → Telegram publication

## تصمیم قطعی درباره Signal Authority

سیگنال فقط از دو منبع مجاز صادر می‌شود:

- MT5 Admin Expert
- Web Admin Panel

Telegram Mini App **هیچ endpoint یا UI برای ایجاد/صدور/انتشار سیگنال ندارد**.

Mini App فقط می‌تواند سیگنال‌های مجاز را نمایش دهد و ابزارهای کاربر/ادمین غیرمرتبط با صدور سیگنال را ارائه کند.

## اصول غیرقابل تغییر

- Backend تنها مرجع canonical Signal است.
- فرمت عمومی Signal: `NX-01`, `NX-02`, ... `NX-100`.
- Risk فقط یک Source of Truth دارد: Risk Firewall فعلی Production.
- License/Payment/VIP از Service Layer مشترک عبور می‌کنند؛ SQL مستقیم برای عملیات دامنه‌ای ممنوع است.
- Web و Mini App نباید Risk Engine موازی بسازند.
- Screenshot انتشار Signal وب باید از MT5 روی VPS گرفته شود؛ Browser یا Mini App chart مصنوعی تولید نمی‌کند.
- Screenshot Agent باید از Trading EA جدا شود تا capture/upload مسیر مدیریت معامله را block نکند.
- FREE/VIP/BOTH از routing فعلی Production استفاده می‌کنند و Chat ID جدید hardcode نمی‌شود.
- `.env` Production هرگز با فایل branch جایگزین نمی‌شود.
- DB wipe ممنوع است.

## مراحل اجرایی

### Phase 1 — Integration Branch & Contracts
- ایجاد شاخه یکپارچه از Production Base.
- ثبت این قرارداد.
- افزودن regression guard برای ممنوع بودن Signal issuance در Mini App.

### Phase 2 — Web Admin/User
- انتقال UI و API وب به هسته Integrated.
- اتصال Risk UI به `risk_firewall` فعلی.
- حذف Kill Switch / Risk tables موازی.
- انتقال Payment/License actions به service layer.

### Phase 3 — Telegram Mini App
- انتقال Mini App User UX.
- حفظ Telegram initData verification.
- حذف کامل Admin Signal creation از Mini App.
- اتصال VIP, Payment, Referral, AutoTrade, Risk و Support به serviceهای canonical.

### Phase 4 — MT5 UI
- انتقال طراحی جدید Expert به Source فعلی Integrated.
- حفظ تمام execution/trailing hardeningهای فعلی.
- Admin/User role-specific navigation.
- confirmation برای عملیات destructive.

### Phase 5 — Web Signal + MT5 Chart Agent
- Web تنها issuer جدید است.
- ایجاد durable chart capture jobs.
- ساخت `NEXUS_ChartAgent` جدا از Trading EA.
- real broker chart + Entry/SL/TP + screenshot + upload.
- flashcard renderer و Telegram routing فعلی reuse می‌شوند.

### Phase 6 — Hardening
- idempotent Signal issuance.
- exactly-once Telegram publication claims.
- publication retry مستقل از screenshot retry.
- valid image decode/verify.
- transactional SQLite backup.
- admin-only trading authority.

### Phase 7 — CI / Staging / E2E
- Python compile + full pytest.
- Admin Web build.
- Mini App build.
- MetaEditor compile zero errors.
- Staging API/DB copy.
- E2E: Web → MT5 ChartAgent → Telegram → AutoTrade → Broker receipt.
- E2E Mini App user flows بدون Signal issuance.

### Phase 8 — Production Cutover
- backup قابل بازیابی.
- ثبت SHA قبلی VPS.
- controlled deploy.
- health checks.
- single controlled Signal validation.
- rollback plan آماده.
