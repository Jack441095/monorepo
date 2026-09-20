# Railway Deployment

Phase 5.6, Sections 10-12. Everything Codex can prepare without Railway credentials. **No real
deployment has been performed** -- this is preparation, verified locally where possible, not a
claim of a working hosted deployment.

## Why Railway

Section 10's instruction: minimize infrastructure complexity, prefer one platform for
website + API + Postgres over separate providers, no Kubernetes/AWS microservices/VPS unless
Railway presents a concrete technical blocker. Nothing about this stack (Next.js, FastAPI,
Postgres) requires anything Railway can't run as three ordinary services in one project.

## Topology

```text
IONOS DNS (docs/IONOS_DNS_SETUP.md)
│
├── nitedsp.co.uk        → Railway service: nitedsp-website (Next.js)
│
└── api.nitedsp.co.uk    → Railway service: nitedsp-backend (FastAPI)
                                    ↓
                          Railway plugin: PostgreSQL
```

Three things in one Railway project: `nitedsp-website`, `nitedsp-backend`, and a Postgres
database plugin. `DATABASE_URL` is provided automatically by Railway's Postgres plugin when
attached to the backend service -- never hand-set.

## Service configuration (prepared, not yet deployed)

- `nitedsp/backend/railway.json` -- Nixpacks build (auto-detects Python via `requirements.txt`),
  start command runs `alembic upgrade head` before `uvicorn`, healthcheck at `/ready` (confirms
  real DB connectivity before Railway routes traffic to a new deploy, not just process
  liveness).
- `nitedsp/website/railway.json` -- Nixpacks build using `npm run build:production` (Section 9's
  fail-closed production-config guard runs as part of the build itself, not a separate step
  someone could forget), start command `npm run start` (Next.js reads `$PORT` automatically).

## Root directory

Railway's monorepo support requires setting each service's "root directory" in its dashboard --
`nitedsp/backend` for the backend service, `nitedsp/website` for the website service. This is a
Railway-dashboard setting, not something expressible in a committed file.

## Environment variables to set on Railway (once the project exists)

See `nitedsp/backend/.env.production.example` for the full backend list with real values
(`nitedsp.co.uk`, `nitedsp@outlook.com`) filled in and secrets left as explicit placeholders --
and `docs/PRODUCTION_CONFIG_REFERENCE.md` for the classification of each. Website needs only
`NEXT_PUBLIC_NITE_DSP_API_URL=https://api.nitedsp.co.uk` and `NITEDSP_BUILD_ENV=production`.

## Known gap: object storage

`MOCK_STORAGE_DIR` (local filesystem) does not survive a Railway redeploy -- Railway's
filesystem is ephemeral per-deploy. Downloads would break on every redeploy until this is
replaced with real object storage (S3-compatible; Railway doesn't provide one natively, so this
needs a separate provider -- e.g. Cloudflare R2 or AWS S3 -- or a Railway volume as a
lower-effort interim fix). Not resolved this phase: no object storage account exists, and
building the abstraction further without a real target to test against risks guessing wrong.
Flagged here explicitly rather than silently deferred.

## What's verified locally (not on Railway itself)

- `alembic upgrade head` against a genuinely fresh, empty local Postgres database -- clean
  (`docs/DATABASE_...` migration rehearsal, reconfirmed this phase).
- `_validate_production_config` accepts a real production-shaped environment (real domain, real
  email, real-looking secrets) and rejects a dev-shaped one -- verified directly this phase.
- `npm run build:production` with the real API URL -- succeeds, zero secrets/localhost in the
  output bundle (`docs/PHASE_5_6_FINAL_SYNTHESIS.md`).
- `/health` and `/ready` behave correctly through a real local Postgres outage (Phase 5.5).

## What can only be verified once a Railway project actually exists

Whether Nixpacks correctly auto-detects both services' build systems, whether the Postgres
plugin's `DATABASE_URL` format matches `psycopg2`'s expected scheme exactly (Railway's default
is `postgresql://`; this codebase's SQLAlchemy URL needs `postgresql+psycopg2://` --
**this will need adjusting at deploy time**, flagged explicitly rather than assumed to just
work), whether the healthcheck timing works during a cold deploy, and real HTTPS/cookie/CORS
behavior across the actual `nitedsp.co.uk`/`api.nitedsp.co.uk` origins.
