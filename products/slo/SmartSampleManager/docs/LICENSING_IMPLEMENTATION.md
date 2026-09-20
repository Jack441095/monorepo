# Licensing Implementation

Phase 4 Milestone C. Implementation: `nitedsp/backend/app/licensing.py`.

## Reuse, not replacement (Section 17)

The canonicalization and signing technique is copied literally from `licensing_server/server.py`:
`json.dumps(payload, sort_keys=True, separators=(",", ":"))`, signed with PyNaCl's
`SigningKey.sign()`. The client verifies against the exact `token_json` string, never a
re-serialization -- JUCE's JSON writer orders/spaces differently than Python's, so re-serializing
before verifying would break every legitimately-signed token. `token_json` / `token` / `signature`
response shape matches the dev server exactly (`schemas.SignedToken`).

The only structural difference: the dev server's SQLite `licenses` table becomes the real
`entitlements` Postgres table (looked up by the new `license_key` column -- see
`docs/NITE_DSP_BACKEND_IMPLEMENTATION.md`'s schema-correction note), and `activations` becomes
the real `activations` table with a foreign key to `entitlements.id`.

## Endpoints

- `POST /v1/activate {license_key, device_id, device_name}` -- authoritative-server principle
  preserved: re-derives status from the database every call, enforces `max_activations`,
  reactivates a previously-deactivated device on the same license without consuming a new slot.
- `POST /v1/validate {license_key, device_id}` -- requires an existing non-deactivated activation.
- `POST /v1/deactivate {license_key, device_id}` -- frees the slot.

`offline_grace_period_seconds` (14 days) and `default_max_activations` (3) are unchanged from the
dev server, per Sections 22-23.

## Verified this session (real crypto, not asserted)

Activated 3 devices against a real seeded entitlement; 4th correctly rejected (403, activation
limit). Fetched the issued token over HTTP, then in a **separate Python process** loaded the
staging public key and called `nacl.signing.VerifyKey.verify()` directly against the returned
`token_json`/`signature` -- confirmed the signature is genuinely valid, not just "the server says
so." Deactivate → validate correctly rejects → reactivate correctly succeeds. An admin revoke
(see `docs/COMMERCE_IMPLEMENTATION.md`) was shown to immediately break subsequent `/v1/validate`
calls for that license. All of the above is also captured as automated pytest assertions in
`tests/test_e2e.py`.

## Status

Design-only items from `docs/LICENSE_KEY_LIFECYCLE.md` (production key generation, multi-key
rotation support) remain correctly unimplemented -- no production key exists, no production
secrets store exists, and building rotation support ahead of any key needing rotation would be
speculative work the STOP RULE forbids.
