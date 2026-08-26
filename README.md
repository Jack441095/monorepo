# NITE DSP Platform

This repository owns the NITE DSP public platform: the website, the backend
API, and the deployment configuration that serves them. It is **not** a home
for NITE DSP products (Smart Sample Manager, KENN, NITE Submit) or research —
those live in their own repositories.

## Layout

- `website/` — Next.js 16 / React 19 / Tailwind 4 / TypeScript public site.
- `backend/` — FastAPI backend: licensing, entitlements, Paddle commerce
  integration, Alembic migrations.

## History

Imported with history preserved (via `git filter-repo`) from the canonical
source branch `web/nitedsp-world-class-v3` in `Nite_DSP_01`
(`Nite_DSP_01-web-v3` worktree, path `nitedsp/website` and `nitedsp/backend`).
Original commit authorship and messages are retained; only unrelated paths
were filtered out.

## Railway deployment (current)

- Website service root: `/website`
- Backend service root: `/backend`

Railway Production Website and Backend are deployed from this repository's
`main` branch. The Submit-staging Backend is also connected to `/backend` and
uses the same source branch. The current verified platform pin is `9945f72`;
the root workspace's launch and recovery runbooks hold the dated deployment
receipts and live readiness evidence.

Production checkout remains explicitly disabled until the owner completes the
live Paddle catalog/key gate. Submit staging is Sandbox-only, uses an isolated
database, and currently uses local release storage; it is not a durable paid-
launch environment. A separate staging Website service has not been
provisioned because of the current Railway project capacity limit.

## Local dev

```
cd website && npm install && npm run dev
cd backend && python -m venv .venv && source .venv/bin/activate \
  && pip install -r requirements.txt
```

## Ownership boundaries

- Products (Smart Sample Manager, KENN, NITE Submit): separate repos.
- Autonomous systems (Thursday): separate repo (`thursday`).
- Research / SLO / audio technology: separate repos, not migrated here.
