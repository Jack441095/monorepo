# NITE DSP

This monorepo contains the NITE DSP public platform, products, audio research,
and internal studio tools. Website payment operations belong to `website/`
and `backend/`.

## Layout

- `website/` — Next.js 16 / React 19 / Tailwind 4 / TypeScript public site.
- `backend/` — FastAPI backend: licensing, entitlements, Stripe commerce
  integration, Alembic migrations.
- `products/` — Product source, including Submit, SLO (Sample Library Optimizer), Para-phase, and KENN research.
- `audio-technology/` — Shared audio analysis and research tools.
- `autonomous-systems/` — Thursday and internal platform support.

## History

Imported with history preserved (via `git filter-repo`) from the canonical
source branch `web/nitedsp-world-class-v3` in `Nite_DSP_01`
(`Nite_DSP_01-web-v3` worktree, path `nitedsp/website` and `nitedsp/backend`).
Original commit authorship and messages are retained; only unrelated paths
were filtered out.

See [Stripe commerce](docs/STRIPE_COMMERCE.md) for checkout settings, webhook events, and migration details.

## Deployment and operations

The production website runs on Vercel; the FastAPI backend runs on Fly.io.
Release artifacts use S3-compatible Cloudflare R2 storage. PostgreSQL account
and commerce data is attached to the backend; the website waitlist has a
separate Neon integration. These providers were checked on 2026-10-08.

Stripe is the current payment provider. Production website/backend checkout,
legal review, and release readiness are disabled. Existing Stripe Payment Links
have their own activation state and must be checked separately before launch.

See [the operations audit and checklist](docs/OPERATIONS_AUDIT_2026-10-08.md)
for evidence, outstanding launch gates, and completed maintenance. Older
website reports and database migrations describe the platform at their recorded
date; use the Stripe commerce guide and this audit for current operations.

A durable staging deployment still needs a public customer rehearsal. The
local test uses an isolated PostgreSQL database, Stripe test mode, R2 artifact
reads, and Resend. It does not establish public staging or live purchase readiness.

The read-only staging gate checks health, storage/email configuration, and
unauthenticated download rejection without creating purchases:

```
cd backend
python scripts/check_staging_rehearsal.py \
  --base-url https://<staging-api> --require-checkout
```

## Local dev

```
cd website && npm install && npm run dev
cd backend && python -m venv .venv && source .venv/bin/activate \
  && pip install -r requirements.txt
```

## Ownership boundaries

- Product release approval is separate from website deployment.
- KENN planning remains in `products/kenn/KENN_PLAN.md`.
- Studio tools use deterministic fixtures for engineering; running Ableton sessions belong to the producer.
