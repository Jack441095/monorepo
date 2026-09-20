# Staging Deployment

Phase 4 Section 76. A genuine, running local staging environment -- not a description of one.
Everything below runs on this development machine; nothing is reachable from the public internet
(correct staging/production boundary per Section 6/7, since no domain or hosting account exists
-- `docs/HUMAN_COMMERCIAL_REQUIREMENTS.md`).

## Components

| Component | How it runs locally | Real or mock |
|---|---|---|
| PostgreSQL 16.14 | Homebrew service, `nitedsp_staging` + `nitedsp_test` databases | Real |
| Backend (FastAPI) | `uvicorn app.main:app`, `nitedsp/backend/.venv` | Real |
| Website (Next.js) | `npm run build && npm run start`, port 3000 | Real |
| Ed25519 signing key | `scripts/generate_staging_keypair.py`, gitignored `staging_keys/` | Real key, staging-only |
| Object storage | `mock_storage/`, gitignored | Mock |
| Email | `email_provider=console`, logs instead of sending | Mock |
| Paddle | `paddle_api_key` empty -- mock mode; webhook verification logic is real | Mixed |

## Reproducing this environment

```bash
cd nitedsp/backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env   # then fill in SESSION_SECRET, PADDLE_WEBHOOK_SECRET, ADMIN_API_KEY
createdb nitedsp_staging
.venv/bin/python scripts/generate_staging_keypair.py
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --port 8420

cd ../website
npm install
echo "NEXT_PUBLIC_NITE_DSP_API_URL=http://localhost:8420" > .env.local
npm run build && npm run start
```

## What this proves and what it doesn't

Proves: the schema deploys via real migrations, the API genuinely runs and serves real database-
backed responses, real Ed25519 signatures verify independently, the website genuinely builds and
serves. Does not prove: behavior under real internet-facing load/latency, TLS termination,
production secrets handling, or anything requiring a real Paddle/hosting/domain account -- all
correctly deferred to `docs/HUMAN_COMMERCIAL_REQUIREMENTS.md`.
