# NITE DSP Backend Implementation

Phase 4 Milestones B-D, F-G. Real, running code at `Audio_Too/nitedsp/backend/` -- FastAPI +
SQLAlchemy + Alembic + PostgreSQL + PyNaCl, per `docs/PHASE_4_PLAN.md`'s stack decision.

## Structure

```text
nitedsp/backend/
  app/
    config.py       Env-driven Settings (Pydantic) -- no domain/secret ever hardcoded
    database.py      SQLAlchemy engine/session/Base
    models.py        ORM models -- see docs/NITE_DSP_DATABASE_SCHEMA.md, 1:1 except license_key addition below
    security.py      Token hashing, itsdangerous signed session + download tokens
    email.py         "console" provider (logs instead of sending -- no email account yet)
    schemas.py       Pydantic request/response models
    auth.py          Magic-link auth + session cookie
    licensing.py     activate/validate/deactivate -- real Ed25519 via PyNaCl
    commerce.py       Paddle webhook handling, sandbox-only
    downloads.py     Signed download URLs against local mock storage
    admin.py         Fail-closed admin operations + audit log
    main.py          FastAPI app, CORS, router wiring
  migrations/         Alembic, two real migrations applied against nitedsp_staging
  scripts/generate_staging_keypair.py
  staging_keys/       gitignored, generated locally
  mock_storage/        gitignored, stands in for real object storage
  tests/              pytest suite against a dedicated nitedsp_test database
```

## Correction to the Phase 3 schema

`entitlements` needed one addition beyond `docs/NITE_DSP_DATABASE_SCHEMA.md`: a `license_key`
column (unique, opaque, customer-facing -- four hyphenated 8-hex-char groups). Phase 3's schema
didn't include it because the schema doc focused on the commercial data model; the client's
`LicenseToken::licenseKey` field (`docs/LICENSE_KEY_LIFECYCLE.md`) needs *something* to look
entitlements up by, distinct from the internal UUID primary key. Added via a second Alembic
migration (`34e889215e56_add_entitlement_license_key.py`), applied cleanly against the real
staging database.

## What's genuinely verified (not just written)

Every one of the following was exercised against the real local `nitedsp_staging` Postgres
database and a real generated Ed25519 staging keypair, via live HTTP requests during this
session, then again via the automated `tests/test_e2e.py` suite (9/9 passing) against a separate
`nitedsp_test` database:

- Two Alembic migrations applied cleanly; all 11 tables (+ `alembic_version`) confirmed present
  via `psql \dt`
- Magic-link request → verify → session cookie → `/auth/me` → replay-rejected
- License activate (3 devices) → limit-reached (4th rejected) → validate → deactivate → validate
  now rejected → reactivate → signature cryptographically verified with PyNaCl `VerifyKey`
  independent of the server process
- Paddle webhook: valid signature → purchase + entitlement created → forged signature rejected
  (401) → replayed event_id → `already_processed`, no duplicate row
- Download: entitlement required (403 without one) → signed URL → fetch succeeds → tampered
  token rejected → Download row recorded
- Admin: fail-closed with no key configured (503) → wrong key rejected (401) → issue/revoke/
  audit-log all confirmed via direct `psql` queries, and a revoke was shown to immediately break
  license validation

## Known limitations (correctly out of scope this phase)

- No real Paddle account exists, so the webhook payloads are self-signed simulations matching
  Paddle Billing's documented schema -- not payloads actually delivered by Paddle's servers.
- No production secrets store exists (`docs/HUMAN_COMMERCIAL_REQUIREMENTS.md`), so there is no
  production Ed25519 key and none was generated -- the staging key is unrelated to any future
  production key.
- `commerce.py`'s `create_checkout_url` deliberately raises `NotImplementedError` rather than
  faking a checkout session, since real checkout creation needs a live Paddle sandbox account.
