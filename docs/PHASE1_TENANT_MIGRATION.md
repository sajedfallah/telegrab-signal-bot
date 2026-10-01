# Phase 1 — Tenant Foundation + RBAC

This phase is intentionally additive. It establishes tenant identity/RBAC and backfills legacy NEXUS-owned rows to the NEXUS tenant without changing existing signal, Telegram, MT5, EA, payment, Mini App, or license behavior.

## Safety gate

Do not run the write migration on production until a VPS/database backup exists and the current regression suite has passed against the deployed commit.

Recommended sequence:

```powershell
# From repository root on the VPS, with the existing venv activated.
Copy-Item .\nexus_bot.db (".\backups\nexus_bot.pre-phase1." + (Get-Date -Format "yyyyMMdd-HHmmss") + ".db")
python -m pytest -q
python .\scripts\phase1_tenant_migration.py --db .\nexus_bot.db --dry-run
python .\scripts\phase1_tenant_migration.py --db .\nexus_bot.db
python -m pytest -q
```

The migration uses `BEGIN IMMEDIATE`, reconciles row counts, verifies that migrated tenant-owned rows have no NULL `tenant_id`, and rolls back on failure.

## What is added

- `tenants`
- `tenant_memberships`
- RBAC roles: OWNER / ADMIN / ANALYST / PUBLISHER / VIEWER
- NEXUS bootstrap tenant
- additive `tenant_id` on the Phase-1 legacy ownership tables
- indexes on the new tenant ownership columns
- server-side tenant-context resolver

## Compatibility rule

Legacy NEXUS code is not switched to tenant queries in this phase. Existing rows are merely assigned to the NEXUS tenant. Domain-by-domain enforcement follows in subsequent phases so the production runtime does not undergo a big-bang rewrite.

## Verification

After migration, verify:

1. Exactly one `tenants.slug='nexus'` row exists.
2. Row counts for migrated legacy tables are unchanged.
3. No migrated row has NULL `tenant_id`.
4. Existing Telegram signal publication/lifecycle still works.
5. Existing MT5 heartbeat/command/receipt flows still work.
6. Existing customer Mini App still works.
7. Existing payment/license flows still work.

## Rollback

Because SQLite cannot safely drop arbitrary added columns on every deployed SQLite version, rollback is restore-based for the production DB:

1. Stop NEXUS services.
2. Preserve the failed DB for diagnostics.
3. Restore the pre-Phase-1 database snapshot.
4. Deploy the previous application commit.
5. Start services and run smoke checks.

Do not attempt to manually delete tenant data from a production DB as a rollback strategy.
