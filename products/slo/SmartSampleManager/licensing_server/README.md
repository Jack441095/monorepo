# Smart Sample Manager — Licensing Backend (DEV/TEST)

This is a **local mock implementation** of the licensing architecture described
in the client (`Source/Licensing/`). It proves the activate → verify →
revalidate → deactivate flow works end to end, using real Ed25519 signing —
it is **not** the production backend, and nothing here should be presented to
a customer.

## What's real here

- Ed25519 signing/verification (via `libsodium`/`PyNaCl`) — the same
  primitive, same key format, a production deployment would use. The client
  (`LicenseManager.cpp`) verifies signatures with `libsodium`'s
  `crypto_sign_verify_detached`, same as it would against a production key.
- The server is authoritative: `/v1/activate` and `/v1/validate` re-derive
  license status from the database on every call and only ever return a
  freshly-signed token for what the database actually says — the client
  cannot upgrade its own license state.
- Device activation limits, revocation, and expiry are enforced server-side
  and covered by the SQLite schema in `server.py`.
- Offline grace period (`check_again_by`, 14 days) is set server-side per
  token and honored client-side when the server is unreachable.

## What's NOT real / still required before shipping

1. **Hosting.** This runs on `localhost:8420` with no TLS. Production needs
   a real domain + HTTPS (e.g. behind Caddy/nginx or a managed platform like
   Fly.io/Render/Railway/AWS). `LicenseManager::serverBaseURL()` must be
   updated to an `https://` URL — the client only ever sends license keys
   and device info in POST bodies, which absolutely must not travel over
   plain HTTP.
2. **A separate production keypair.** Run `generate_keypair.py` again in the
   production environment. The private key must never leave that server —
   in particular, never let it end up in this repo, in a build artifact, or
   in CI logs. Recommended: a secrets manager (e.g. your host's built-in
   secret store, or a dedicated one like Doppler/1Password/AWS Secrets
   Manager), not a plaintext file at all, once this is real.
3. **Swap the client's embedded public key.** `Source/Licensing/LicensePublicKey.h`
   currently holds this dev keypair's public key. Update it to the
   production public key before building a release. (This one *is* meant to
   be public and committed — it's not a secret, just needs to match the
   production private key.)
4. **A real database**, not a single SQLite file with no backups. Postgres
   on whatever host you pick, with actual backups, is the realistic
   production choice once there are paying customers.
5. **Auth on `/v1/admin/licenses`.** Right now anyone who can reach the dev
   server can mint a free license by calling this endpoint — there is no
   authentication on it at all. In production this route must be locked
   down (e.g. only callable server-side from a payment webhook handler,
   never exposed to the public internet directly) — see the payment
   integration point below.
6. **Payment integration.** Nothing here processes payment. The intended
   architecture: a payment provider (Stripe is the common choice, but this
   wasn't already in use anywhere else in this repo, so no assumption is
   made here) → webhook → your backend calls the equivalent of
   `create_license()` server-side. This file deliberately keeps the license
   data model (customer/product/license/activation) decoupled from any
   specific payment provider so that integration is additive, not a
   rewrite.
7. **Rate limiting / abuse protection** on the activate/validate endpoints —
   none exists in this dev version.
8. **Monitoring/alerting** for the production deployment (uptime, error
   rate) — out of scope for this repo, but worth having before customers
   depend on activation actually working.

None of the above is implemented here because each requires an account,
a domain, a hosting decision, or a business decision (which payment
provider) that only Jack can make — this file exists so that decision list
is explicit rather than silently assumed away.

## Running locally

```bash
cd studio/vst3_plugins/SmartSampleManager/licensing_server
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
./.venv/bin/python generate_keypair.py     # once; prints the public key to embed in the client
./.venv/bin/uvicorn server:app --port 8420
```

Create a test license (stand-in for what a payment webhook would do):

```bash
curl -X POST localhost:8420/v1/admin/licenses \
  -H "Content-Type: application/json" \
  -d '{"customer_email":"you@example.com","tier":"pro","max_activations":2}'
```

Then run the client-side integration test against it:

```bash
cd ../  # SmartSampleManager/
./build/TestLicensing <license_key_from_above>
```

`TestLicensing` exercises activate → local reload → revalidate → a
deliberate signature-tamper rejection check → deactivate, and fails loudly
if any step doesn't behave as expected (in particular, it fails hard if a
tampered license is ever accepted).

## API reference

| Endpoint | Purpose |
|---|---|
| `POST /v1/admin/licenses` | Create a license (unauthenticated here — see risk #5 above) |
| `POST /v1/activate` | `{license_key, device_id, device_name}` → signed token, enforces `max_activations` |
| `POST /v1/validate` | `{license_key, device_id}` → fresh signed token if still active |
| `POST /v1/deactivate` | `{license_key, device_id}` → frees the activation slot |

All signed responses have the shape:

```json
{
  "token_json": "<exact canonical JSON string that was signed>",
  "token": { "...": "...", "parsed for convenience" },
  "signature": "<base64 Ed25519 signature over token_json's UTF-8 bytes>"
}
```

The client verifies against `token_json` verbatim rather than re-serializing
`token` — JUCE's JSON writer and Python's `json.dumps` don't produce
byte-identical output, so re-serializing before verifying would make every
legitimately-signed token fail.
