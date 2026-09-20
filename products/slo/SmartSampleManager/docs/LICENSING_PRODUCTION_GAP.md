# SmartSampleManager — Licensing Production Gap

Phase 1, Section 24. Distinguishes the plugin-side licensing architecture (sound) from the dev/test licensing server (not production-ready) and lists exactly what's missing before real customers depend on it. Source: `Source/Licensing/`, `licensing_server/README.md`, `licensing_server/server.py`, verified by direct code audit (not just docs).

## Plugin-side client — architecturally sound, verified

- No private key ships client-side (`Source/Licensing/LicensePublicKey.h` holds only the public verification key).
- Ed25519 signature verification (`LicenseManager::verifyAndDecode`) checks against the exact `token_json` bytes the server signed, not a re-serialized object — correct handling of the JSON-serializer-mismatch trap the server's own README warns about.
- Real offline grace period: server stamps `check_again_by` (14 days), client honors it both fresh-off-network and loaded-from-disk-with-no-contact.
- Corrupted or tampered local license files fail closed (`notActivated`/`invalid`), never crash, never silently elevate.
- Network calls have an 8s timeout and degrade to the cached token's own grace-period judgment on failure — no blocking, no crash.
- Confirmed zero licensing call sites anywhere in `processBlock` — no realtime-thread coupling.

**This part does not need rework before shipping.** The gaps are all deployment/infrastructure, listed below.

## What's real in the dev server (`licensing_server/`)

- Genuine Ed25519 signing/verification via libsodium/PyNaCl — same primitives production would use.
- Server-authoritative: `/v1/activate`/`/v1/validate` re-derive status from the DB every call.
- Device activation limits, revocation, expiry enforced server-side, covered by the SQLite schema.
- 14-day offline grace period set server-side and honored client-side.

## What's missing before any real customer depends on this (from `licensing_server/README.md`, verified against `server.py`)

| Gap | Detail | Blocks |
|---|---|---|
| Hosting/TLS | Runs on `localhost:8420`, no TLS. `LicenseManager::serverBaseURL()` currently defaults to `http://localhost:8420` | Any real activation — license keys and device info must never travel over plain HTTP |
| Production keypair | Current dev keypair was regenerated during this audit (see below) with no production separation | Must run `generate_keypair.py` in a real production environment; private key must never touch this repo, a build artifact, or CI logs |
| Client public key swap | `Source/Licensing/LicensePublicKey.h` must be updated to the production public key before building a release binary | Build process |
| Real database | Single SQLite file, no backups | Postgres (or similar) with real backups once there are paying customers |
| Admin endpoint auth | `POST /v1/admin/licenses` has **no authentication** in dev — anyone who can reach the server can mint a free license | Must be locked down to only be callable server-side from a payment webhook handler, never exposed publicly |
| Payment integration | Nothing in this repo processes payment (confirmed: no Stripe/payment-provider code found anywhere in the whole `Audio_Too/` tree) | The entitlement flow itself — `create_license()`-equivalent must be called from a webhook, not exposed directly |
| Rate limiting | None on activate/validate endpoints | Abuse protection |
| Monitoring/alerting | None (explicitly out of scope for this repo per the README) | Operational confidence once customers depend on activation working |

## Note on this audit's own key regeneration

During this pass, the dev server's private signing key (`licensing_server/keys/signing_key.private`) was found to be absent on this machine — only the matching public key was embedded in the client, an orphaned reference to a key nobody had locally. A fresh dev keypair was generated (`generate_keypair.py`) and the client's embedded dev public key (`Source/Licensing/LicensePublicKey.h`) was updated to match, so local dev/test activation flows are runnable again. **This is uncommitted, dev-only, and reversible** (`git checkout -- Source/Licensing/LicensePublicKey.h` restores the prior placeholder value) — flagging it here so it isn't mistaken for a production key decision. It changes nothing about the production gaps above.

## Not evaluated in this pass

Payment provider selection (Stripe/Paddle/Lemon Squeezy/FastSpring), Merchant-of-Record decision, and live checkout integration are explicitly deferred per the master prompt's Phase 1 scope ("Do not yet integrate checkout") — see Phase 29-31 of `prompts/Website_commercial_samplemanager.txt` for when those become relevant.
