# NEXUS ICT — Development Handoff & Branch Governance

## برای تیم توسعه

اگر برای اولین بار این مسیر را بررسی می‌کنید، به این ترتیب بخوانید:

1. `docs/nexus-ict/CURRENT_STATUS_FA.md`
2. `docs/nexus-ict/ONE_WEEK_FORWARD_TEST_V22_46_FA.md`
3. `docs/nexus-ict/NEXT_V22_47_INSIGHT_ENGINE_FA.md`
4. `CHANGELOG.md`
5. Issue tracking فعلی

## Source of Truth

- `main`: مرجع مستندات تأییدشده.
- Private MQ5 artifact: خارج از public GitHub، به‌دلیل runtime secrets.
- Issue مربوط به V22.46: مرجع Test Evidence و bug tracking.
- Branchهای feature قدیمی را منبع وضعیت ICT Expert فرض نکنید.

## Branch cleanup policy

Repository شاخه‌های متعدد مربوط به Mini App، Provider Panel، Academy، Marketing، Release و Hotfix دارد. این شاخه‌ها Scopeهای متفاوت دارند و نباید صرفاً برای «کم کردن تعداد Branch» با هم Merge شوند.

برای NEXUS ICT Expert:
- Branch مستنداتی قدیمی `docs/nexus-ict-v22.31-trail07` پس از Merge این handoff **superseded** است.
- هر Doc update بعدی باید از `main` Branch شود.
- برای Bug fix V22.46 از نامی مثل `fix/nexus-ict-v22.46-<topic>` استفاده شود.
- برای V22.47 از `feature/nexus-ict-v22.47-insight-engine` استفاده شود.
- هیچ تغییر ICT Expert نباید روی branchهای Mini App / Academy / Provider Panel قرار گیرد.

## قواعد PR

هر PR مربوط به ICT Expert باید مشخص کند:
- Version.
- Signal behavior changed? yes/no.
- New gate/filter? yes/no.
- Risk/position-management changed? yes/no.
- Dataset/schema changed? yes/no.
- MetaEditor compile evidence.
- Demo evidence.
- Rollback plan.
- Secret exposure check.

## Freeze در هفته تست

از 2026-09-18 تا Review یک‌هفته‌ای:
- فقط bug/data integrity/performance/UI fixes.
- Strategy changes ممنوع.
- هر Fix باید در Issue تست ثبت شود.

## Security

- Telegram Bot Token هرگز در Issue/PR/README قرار نگیرد.
- Private MQ5 Server Build در public repo commit نشود.
- Screenshot شامل Token نباید public attach شود.
- اگر credential exposure رخ داد، Token rotate شود.

## Analytics Viewer

Viewer فعلی:
- فارسی و RTL.
- Mosaic Lite / Cruip inspired UI.
- باید GPL notice مربوط به Viewer حفظ شود.
- Viewer فقط Data Analysis است؛ Strategy را تغییر نمی‌دهد.

## بعد از یک هفته

تیم باید:
1. CSVها را Archive کند.
2. Data Quality report بسازد.
3. Insight review را انجام دهد.
4. نتیجه را در Issue ثبت کند.
5. فقط سپس V22.47 را شروع کند.
