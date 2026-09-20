# Commerce Implementation

Phase 4 Milestone D. Implementation: `nitedsp/backend/app/commerce.py`. Sandbox-only throughout
-- Section 95: no code path here can charge a real card. `paddle_api_key` defaults to empty
(no Paddle account exists yet -- `docs/HUMAN_COMMERCIAL_REQUIREMENTS.md`), which puts
`PaddleProvider` into a documented mock mode; `create_checkout_url` raises `NotImplementedError`
rather than fabricating a checkout session.

## Webhook signature verification (real crypto, genuinely testable without a Paddle account)

Implements Paddle Billing's actual documented scheme: HMAC-SHA256 over `"{ts}:{raw_body}"`, header
format `Paddle-Signature: ts=<unix>;h1=<hex>`, constant-time comparison
(`hmac.compare_digest`). This is real, independently-verifiable cryptographic logic -- it doesn't
need a live account to be correct, only a shared secret, which `PADDLE_WEBHOOK_SECRET` provides
locally.

## Webhook processing (`POST /webhooks/paddle`)

1. Verify signature -- 401 if invalid.
2. Idempotency check against `webhook_events.(provider, provider_event_id)` UNIQUE constraint
   (`docs/NITE_DSP_DATABASE_SCHEMA.md`) -- a replayed event returns `already_processed` without
   reprocessing.
3. On `transaction.completed`: creates (or reuses) the `users` row by email, a `purchases` row,
   and an `entitlements` row with a freshly generated `license_key` -- the same purchase→
   entitlement transaction Phase 3 designed.
4. Processing errors are persisted on the `webhook_events` row (`processing_error`) rather than
   silently dropped, surfaced via `GET /admin/webhooks/failed`.

## Verified this session

A self-signed simulated `transaction.completed` payload (matching Paddle's documented schema)
was POSTed with a correct signature: purchase + entitlement + a working, activatable license_key
were created, confirmed via direct `psql` query and by successfully calling `/v1/activate` with
the resulting key. A forged signature was correctly rejected (401). The same event replayed
returned `already_processed` with no duplicate purchase row (confirmed via `COUNT(*) = 1`). All
three cases are also automated in `tests/test_e2e.py`.

## Explicitly not done (correctly, per Section 95 / STOP RULE)

Real Paddle API calls (checkout creation, real webhook delivery from Paddle's servers) --
requires a live sandbox account that does not exist yet
(`docs/HUMAN_COMMERCIAL_REQUIREMENTS.md`).
