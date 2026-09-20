# NITE DSP Production Backup & Recovery (Design Only)

Phase 3, Section 71. **Design document — no production database exists yet.**

## What needs backing up

Once deployed, the single Postgres instance backing `docs/NITE_DSP_DATABASE_SCHEMA.md` holds
everything commercially critical: `users`, `products`, `purchases`, `entitlements`,
`activations`, `trials`, `releases`, `downloads`, `webhook_events`. This is the entire
commercial record of the business — losing it without a backup would mean losing the ability to
prove who owns what, a business-ending scenario for a licensing-based product, not a minor
inconvenience.

Object storage (installers) is separately durable by nature of most managed object-storage
providers (typically 99.999999999%-class durability out of the box) — the backup concern here is
specifically the database, not the binaries.

## Requirements (Section 71)

```text
Scheduled backups     -- daily, minimum; most managed Postgres providers (the
                          hosting choice deferred to docs/HUMAN_COMMERCIAL_REQUIREMENTS.md)
                          offer automated daily backups plus point-in-time recovery
                          as a built-in feature -- prefer using the provider's
                          built-in mechanism over hand-rolling one, per Section 83's
                          "do not overengineer" instruction
Retention policy        -- recommend 30 days of daily backups minimum, longer if the
                             hosting provider's default tier already includes it at no
                             extra cost
Restore procedure         -- documented, provider-specific (varies by managed Postgres
                               choice) -- to be filled in with the actual provider's
                               restore steps once hosting is selected
Restore test               -- a backup that has never been restored is not a verified
                                backup -- a real restore-to-a-scratch-instance test
                                should happen at least once before going live, and
                                periodically afterward (e.g. quarterly)
```

## Recommended approach: use the hosting provider's built-in backup/PITR, don't build custom tooling

Per Section 83's explicit "do not overengineer" instruction, a single-product company at this
stage should not build custom backup infrastructure (a cron job dumping `pg_dump` to a separate
bucket, custom retention logic, etc.) when essentially every reputable managed Postgres provider
(the specific choice is deferred to hosting selection — `docs/HUMAN_COMMERCIAL_REQUIREMENTS.md`)
already provides automated daily backups and point-in-time recovery as a standard feature. The
engineering effort belongs in *verifying* the provider's restore process actually works
(the restore test above), not in building a parallel system.

## What's explicitly deferred

The actual restore procedure's exact steps depend on which managed Postgres provider is chosen —
writing detailed restore-runbook steps now, before a provider exists, would mean rewriting them
once one is chosen anyway. This document establishes the *requirement* (backups + tested
restore); the *runbook* gets filled in once hosting exists.

## Status

**Design only.** No production database, no backup schedule, no restore test has been performed.
