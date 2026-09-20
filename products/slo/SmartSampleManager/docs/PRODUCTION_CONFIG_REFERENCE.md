# Production Configuration Reference

Phase 5.5, Sections 22-24. Canonical reference for every backend/website configuration
variable, its classification, and where it's defined. The authoritative template is
`nitedsp/backend/.env.example` (backend) and `nitedsp/website/.env.local`'s shape (website,
`NEXT_PUBLIC_NITE_DSP_API_URL` only) -- this document explains and classifies what's there,
it doesn't duplicate the values.

## Secret classification (Section 24)

| Class | Meaning | Examples |
|---|---|---|
| **PUBLIC** | Safe to appear in a client-side bundle or public repo | `NITE_DSP_PUBLIC_URL`, `NITE_DSP_API_URL`, `NITE_DSP_SUPPORT_EMAIL` |
| **CLIENT BUILD CONFIG** | Baked into the website's client-side JS bundle at build time -- functionally PUBLIC the moment the site is built, never a secret | `NEXT_PUBLIC_NITE_DSP_API_URL` |
| **SERVER SECRET** | Must only ever exist server-side; a leak compromises real security properties | `SESSION_SECRET`, `ADMIN_API_KEY`, `PADDLE_WEBHOOK_SECRET`, `PADDLE_API_KEY`, `LICENSING_PRIVATE_KEY_PATH`'s file contents |
| **BUILD SECRET** | Only needed at CI/release-build time, never at runtime | Apple signing identity / notarization credentials (not yet applicable -- no credentials exist) |

## Preventing SERVER SECRET -> client leakage (Section 24)

Next.js's own convention is the enforcement mechanism: only environment variables prefixed
`NEXT_PUBLIC_` are ever inlined into the client bundle; everything else stays server-only by
default. This project follows that convention exactly -- `NEXT_PUBLIC_NITE_DSP_API_URL` is the
only website env var, and it's PUBLIC/CLIENT BUILD CONFIG by definition (the API's own base URL
is not sensitive). No `PADDLE_*`, `ADMIN_API_KEY`, `SESSION_SECRET`, or licensing key ever has a
`NEXT_PUBLIC_` counterpart. Verified this phase via the config-leak scan of the built website
bundle (`docs/PHASE_5_5_FINAL_SYNTHESIS.md`) -- zero secrets found.

## Full variable reference (backend, `nitedsp/backend/.env.example`)

| Variable | Class | Fails closed in production if missing/default? |
|---|---|---|
| `ENVIRONMENT` | PUBLIC | N/A -- this IS the gate |
| `DATABASE_URL` | SERVER SECRET (contains credentials in a real deployment) | Yes -- rejects `nitedsp_staging`/`nitedsp_test` |
| `NITE_DSP_PUBLIC_URL` | PUBLIC | Yes -- rejects `localhost` |
| `NITE_DSP_API_URL` | PUBLIC | Yes -- rejects `localhost` |
| `NITE_DSP_SUPPORT_EMAIL` | PUBLIC | Yes -- rejects `@localhost.invalid` |
| `SESSION_SECRET` | SERVER SECRET | Yes -- rejects the dev default string |
| `PADDLE_API_KEY` | SERVER SECRET | Not yet -- Paddle isn't required for private beta (Section 71) |
| `PADDLE_WEBHOOK_SECRET` | SERVER SECRET | Not yet, same reason |
| `EMAIL_PROVIDER` | PUBLIC | Not yet -- `"console"` in production would just mean emails never actually send, a functional gap not a security one |
| `EMAIL_FROM_NAME` / `EMAIL_FROM_ADDRESS` | PUBLIC | `EMAIL_FROM_ADDRESS` rejects `@localhost.invalid` |
| `LICENSING_PRIVATE_KEY_PATH` | points at a SERVER SECRET (the key file itself) | Yes -- rejects the `staging_keys/` path |
| `LICENSING_PUBLIC_KEY_PATH` | PUBLIC (it's a public key) | No check needed |
| `MOCK_STORAGE_DIR` | PUBLIC (a local path, not sensitive) | Not yet checked -- real object storage config doesn't exist yet either |
| `ADMIN_API_KEY` | SERVER SECRET | Yes -- rejects empty |

See `nitedsp/backend/app/config.py`'s `_validate_production_config` (Phase 5.5) for the exact,
authoritative enforcement -- this table describes it, the code is the source of truth.

## Full variable reference (website)

| Variable | Class |
|---|---|
| `NEXT_PUBLIC_NITE_DSP_API_URL` | CLIENT BUILD CONFIG / PUBLIC |
| `NITEDSP_BUILD_ENV` | PUBLIC (build-time gate flag, not a secret) |

## Verified this phase (Phase 5.5)

`_validate_production_config` tested directly: refuses to start with `ENVIRONMENT=production`
and dev defaults (collects and reports every violation at once); starts cleanly in normal
development mode. The website's `scripts/check-production-config.mjs` tested the same way for
`npm run build:production`. Both are new this phase -- see `docs/SECURITY_MODEL.md`'s Phase 5.5
update.

## Phase 5.6 update -- real values applied, Section 14's WEBSITE/BACKEND/DATABASE/BUILD/SECRET/PUBLIC breakdown

`nitedsp/backend/.env.production.example` now contains the real approved domain
(`nitedsp.co.uk`/`api.nitedsp.co.uk`) and company email (`nitedsp@outlook.com`) as actual
values, with every remaining secret left as an explicit `<...>` placeholder -- never a real
secret. Verified directly this phase: `_validate_production_config` accepts a fully
production-shaped environment built from these real values (see
`docs/PHASE_5_6_FINAL_SYNTHESIS.md`).

| Variable | Category | Class |
|---|---|---|
| `ENVIRONMENT` | BACKEND | PUBLIC |
| `DATABASE_URL` | DATABASE | SECRET (set automatically by Railway's Postgres plugin) |
| `NITE_DSP_PUBLIC_URL` | BACKEND | PUBLIC (real value: `https://nitedsp.co.uk`) |
| `NITE_DSP_API_URL` | BACKEND | PUBLIC (real value: `https://api.nitedsp.co.uk`) |
| `NITE_DSP_SUPPORT_EMAIL` | BACKEND | PUBLIC (real value: `nitedsp@outlook.com` -- a real mailbox, not a verified transactional sender, see `docs/EMAIL_CONFIGURATION.md`) |
| `SESSION_SECRET` | BACKEND | SECRET |
| `ADMIN_API_KEY` | BACKEND | SECRET |
| `PADDLE_API_KEY` / `PADDLE_WEBHOOK_SECRET` | BACKEND | SECRET (BLOCKED EXTERNAL -- no account) |
| `EMAIL_PROVIDER` / `EMAIL_FROM_NAME` / `EMAIL_FROM_ADDRESS` | BACKEND | PUBLIC |
| `LICENSING_PRIVATE_KEY_PATH` | BACKEND | points at a SECRET (the key file) |
| `LICENSING_PUBLIC_KEY_PATH` | BACKEND | PUBLIC |
| `MOCK_STORAGE_DIR` | BACKEND | PUBLIC (known gap in production -- `docs/RAILWAY_DEPLOYMENT.md`) |
| `NEXT_PUBLIC_NITE_DSP_API_URL` | WEBSITE | CLIENT BUILD CONFIG / PUBLIC (real value: `https://api.nitedsp.co.uk`) |
| `NITEDSP_BUILD_ENV` | WEBSITE | BUILD (gate flag, not a secret) |

Verified this phase: a real production-configured website build (`NITEDSP_BUILD_ENV=production
NEXT_PUBLIC_NITE_DSP_API_URL=https://api.nitedsp.co.uk npm run build:production`) succeeds, and
the resulting bundle contains zero secrets and zero application-level localhost references (only
Next.js's own internal hostname-parsing library code matches "localhost" as a substring, unrelated
to configuration).
