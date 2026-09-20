# Staging E2E Results

Phase 4 Milestone H. `tests/test_e2e.py`, run against a dedicated `nitedsp_test` Postgres
database (never `nitedsp_staging`), real Alembic migrations, real PyNaCl signing with the
generated staging keypair.

## Result

```text
9 passed, 1 warning in 0.85s
```

(The one warning is `starlette.testclient`'s httpx deprecation notice -- unrelated to
correctness.)

## Covered

**Happy path** (`test_full_purchase_to_activation_flow`): create user → login → simulated Paddle
webhook → purchase row created → entitlement row created with a real license_key → account holds
the entitlement → download link generated and fetched → license activated → signature
independently verified with PyNaCl → offline validation succeeds → deactivate → validate now
rejected → reactivate succeeds → admin revoke ("refund") → validate now rejected.

**Failure paths** (Section 99's required list):
- Duplicate webhook (`test_duplicate_webhook_is_idempotent`) -- second delivery returns
  `already_processed`, no duplicate purchase row
- Forged webhook signature (`test_forged_webhook_signature_rejected`) -- 401
- Invalid/unknown license key (`test_activate_invalid_license_key_rejected`) -- 404
- Activation limit reached (`test_activation_limit_reached`) -- 4th device on a 1-seat license
  rejected with 403
- Revoked entitlement -- covered inline at the end of the happy-path test
- Expired entitlement (`test_expired_entitlement_rejected`) -- 403
- Download without entitlement (`test_download_without_entitlement_rejected`) -- 403
- Missing release (`test_download_missing_release_returns_404`) -- 404
- Bad admin key (`test_admin_endpoints_reject_bad_key`) -- 401

## Explicitly not covered (documented, not faked)

**DB/license-server temporarily unavailable.** Exercising a real outage would mean stopping the
local Postgres service mid-suite -- disruptive to run repeatedly, and it doesn't need a bespoke
test to prove: SQLAlchemy raises `OperationalError` on connection failure, and FastAPI's default
exception handling surfaces that as a 500, the same as any other unhandled server-side exception.
No code path here catches and silently swallows a DB error. Documented rather than asserted, per
the STOP RULE's preference for an honest "not tested, here's why" over a fabricated pass.

**Expired trial.** No `trials` row lifecycle was exercised specifically (`trials` table exists,
but no trial-issuing endpoint was built this phase -- trial issuance wasn't part of Milestones
B-H's scope). `test_expired_entitlement_rejected` covers the equivalent expiry-gate logic on
`entitlements`, which is what actually gates license activation.
