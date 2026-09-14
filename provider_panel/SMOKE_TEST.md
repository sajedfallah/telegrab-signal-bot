# Provider Panel UI v1 — Visual Acceptance

Run locally from repository root:

```powershell
python .\provider_panel\serve.py
```

Open `http://127.0.0.1:8091`.

Acceptance checklist:

- Desktop sidebar and header match the approved dense SaaS dashboard hierarchy.
- Dashboard shows four KPI cards, real canvas revenue chart, real canvas donut chart, Recent Signals table, Quick Actions and integration health strip.
- Signal Center navigation works and preserves a dense filter/table layout.
- Copy Trade shows KPIs, copier growth chart and prepaid credit capacity.
- Subscribers displays the customer table.
- Reports displays KPI cards and P&L visualization.
- Branding displays assets, brand colors and a live brand preview.
- Settings displays Telegram, MT5, subscription and Copy Trade health.
- Responsive layout remains usable on narrow screens.
- Existing `miniapp/` is unchanged.

The chart/table components must not be removed during backend integration. Replace fixture values with tenant-scoped API data while preserving the visual contract.