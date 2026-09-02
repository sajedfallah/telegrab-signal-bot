# NEXUS v7.1.0 — اصلاح پرداخت USDT و ریالی

## اصلاحات

1. پرداخت USDT دیگر به دریافت نرخ USDT/RIAL وابسته نیست.
2. Endpoint پیش‌فرض Nobitex از API قدیمی `v2/orderbook` به endpoint مستندشده `v3/orderbook` تغییر کرد.
3. در صورت عدم دسترسی به Rate Provider، پیام کاربرپسند نمایش داده می‌شود و جزئیات خام شبکه به کاربر نشت نمی‌کند.
4. قابلیت Manual USDT/RIAL Rate موجود در پنل ادمین حفظ شده است؛ برای سروری که به Nobitex دسترسی ندارد می‌توان نرخ را دستی تعیین کرد.
5. تست مستقل اضافه شد که ثابت می‌کند ایجاد فاکتور USDT هیچ فراخوانی برای Rate Provider انجام نمی‌دهد.

## تست

- Pytest: **64 passed**
- compileall: **PASS**
- validate_build.py: **PASS**
- MT5 EX5: همچنان نیازمند Compile با MetaEditor روی Windows است.

## نکته عملی برای سرور

خطای فعلی سرور:

`api.nobitex.ir: Domain name not found`

یک مشکل دسترسی/DNS سرور به Nobitex است و با تغییر endpoint از v2 به v3 به‌تنهایی حل نمی‌شود. برای پرداخت ریالی تا زمان برقراری دسترسی به Rate Provider، از **Admin → Pricing Settings → Override USDT Rate** استفاده شود.

پرداخت USDT مستقل است و نباید به این خطا وابسته باشد.
