# Provider Panel Route Map

Current preview is a single-page static shell. Production routing target:

- `/provider` -> Dashboard
- `/provider/signals` -> Signal Center
- `/provider/copy-trade` -> Copy Trade
- `/provider/subscribers` -> Subscribers
- `/provider/reports` -> Reports & Analytics
- `/provider/branding` -> Settings & Branding
- `/provider/settings` -> Connections / workspace settings

All production routes require authenticated tenant context and RBAC. Provider routes must remain separate from the existing customer Mini App routes.