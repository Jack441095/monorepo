# NITE DSP Security Model (Design Review)

Phase 3, Section 82. **Reviews the design of the commercial infrastructure specified this phase
— nothing described here is deployed, so this is a design-time security review, not an audit of
running infrastructure.** Will need re-review once anything is actually deployed (a design review
cannot catch deployment-specific misconfiguration).

## Authentication (`docs/NITE_DSP_ACCOUNT_ARCHITECTURE.md`)

- Passwordless magic-link primary path removes an entire class of risk (password database
  compromise, credential stuffing against reused passwords) that a typical email/password system
  carries.
- Rate limiting on the link-request endpoint prevents both email-bombing and brute-force token
  guessing.
- Email enumeration protection (identical response regardless of account existence) prevents
  using the login flow to discover which emails have accounts.
- **Residual risk**: magic links are only as secure as the customer's email account. This is an
  accepted, standard tradeoff for passwordless auth at this product's scale — not a gap unique to
  this design.

## Licensing (`docs/PRODUCTION_LICENSING_ARCHITECTURE.md`, `docs/LICENSE_KEY_LIFECYCLE.md`)

- Client-side Ed25519 verification design already independently confirmed sound across Phase 1
  and Phase 2 audits — not re-litigated here.
- **The one hard finding, already flagged and unresolved**: the dev server's admin license-
  minting endpoint has zero authentication. This is explicitly called out as the P0 item that
  must never reach production as-is — the production design routes license issuance exclusively
  through the verified-webhook path or an authenticated admin session, never a public endpoint.
  Confirmed by direct source read this session (`server.py`), not assumed from prior docs.
- Production private key handling follows the correct order of operations: no key is generated
  until a real secrets-management environment exists (Section 20's explicit stop condition,
  honored — no key has been generated).

## Webhooks (`docs/PAYMENT_FLOW.md`)

- Cryptographic signature verification before any payload is trusted.
- Idempotency via a database uniqueness constraint (`UNIQUE (provider, provider_event_id)`), not
  application-logic-only deduplication that could have a race condition — the constraint is
  enforced at the database layer, which is the correct place for a guarantee this important.
- Transaction-safe entitlement creation (purchase + entitlement created atomically) prevents a
  partial-failure state where a purchase is recorded but no entitlement exists, or vice versa.

## Account authorization vs. admin authorization (Section 69)

Deliberately designed as separate systems: a customer's NITE DSP Account session
(`docs/NITE_DSP_ACCOUNT_ARCHITECTURE.md`) has no path to any admin capability
(license-minting, entitlement revocation, viewing other customers' data). Admin tooling
(Section 68, not yet designed in detail — flagged as a future pass, not needed for the core
commercial flow this phase covers) requires its own, separately-authenticated session with no
shared code path to customer login.

## Signed downloads (`docs/DOWNLOAD_ARCHITECTURE.md`)

- Entitlement check happens before a signed URL is ever generated — an unauthenticated or
  unentitled request never reaches object storage.
- Signed URLs are short-lived (minutes, not hours/days), limiting the window a leaked URL could
  be reused or shared.
- Release immutability (once published, `storage_key` cannot change) prevents a compromised
  release pipeline from silently swapping a legitimate installer for a malicious one without it
  being a visible, auditable new-version event.

## Installer integrity (`docs/MACOS_RELEASE_PROCESS.md`, `docs/INSTALLER_ARCHITECTURE.md`)

- Code signing + notarization (once Apple Developer credentials exist) gives macOS Gatekeeper's
  own integrity verification for free — not something this project needs to reimplement.
- `checksum_sha256` stored per release record gives an independent verification path beyond
  code-signing alone.
- **Not yet implemented**: no signing has actually happened (blocked on credentials), so this
  section describes the design's soundness, not a verified deployed state.

## Update API (`docs/DOWNLOAD_ARCHITECTURE.md`)

- Deliberately returns no credentials or direct storage URLs — only a link to the (separately
  entitlement-gated) download page. A compromised or spoofed update-check response can at worst
  mislead a user about version numbers, never leak a download credential, since none is ever
  present in that response.

## Storage permissions

Object storage (once provisioned) should use a private bucket with access only through the
signed-URL mechanism — never a publicly-listable/publicly-readable bucket. Not yet provisioned,
so this is a requirement for whoever sets up the hosting, not a verified current state.

## Secrets handling

Every secret this phase's design introduces (production Ed25519 private key, Paddle API
credentials, database credentials, transactional email API key) is designed to live only in a
production secrets manager, never in the repository, client, or CI logs — consistent with the
existing dev-key discipline already correctly followed in `licensing_server/` (gitignored dev
key, ephemeral per-CI-run keypair for tests).

## What this review does NOT cover

- Anything about SmartSampleManager's own client-side realtime-safety/memory-safety work — that's
  `docs/REALTIME_SAFETY_AUDIT.md`/`docs/ASYNC_STARTUP.md`'s domain, already reviewed extensively
  in Phase 2, unrelated to the commercial-infrastructure security surface this document covers.
- A penetration test or live vulnerability scan — impossible against infrastructure that doesn't
  exist yet. Re-review required once anything here is actually deployed.

## Status

**Design review only, through Phase 3.** No commercial infrastructure was deployed at that point.

## Phase 4 update

Deployment has now begun -- to local staging only (`docs/STAGING_DEPLOYMENT.md`), never to a
public or production environment. Real security-relevant behavior confirmed this phase, not just
designed:

- Magic-link tokens are stored hashed (SHA-256), never in plaintext; verified via direct
  Postgres query that only the hash is ever persisted.
- Session and download tokens are `itsdangerous`-signed with distinct salts; tampering with
  either was confirmed to be rejected (`docs/AUTH_IMPLEMENTATION.md`, `docs/DOWNLOAD_IMPLEMENTATION.md`).
- Webhook signatures use real HMAC-SHA256 verification with constant-time comparison
  (`hmac.compare_digest`); a forged signature was confirmed rejected
  (`docs/COMMERCE_IMPLEMENTATION.md`).
- Admin endpoints are fail-closed: confirmed 503 with no key configured, 401 with a wrong key --
  the direct fix for the exact "zero auth" gap `docs/PRODUCTION_LICENSING_ARCHITECTURE.md`
  flagged in the dev licensing_server's `POST /v1/admin/licenses`.
- CORS is an explicit single-origin allow-list with `allow_credentials=True`, never a wildcard.

Still design-only / not yet applicable: production secrets storage (no production environment
exists -- `docs/HUMAN_COMMERCIAL_REQUIREMENTS.md`), TLS (no hosting/domain).

## Phase 5 update

Rate limiting (flagged as a gap above) is now implemented: an in-process fixed-window limiter
(`app/rate_limit.py`) on magic-link request (5/5min), magic-link verify (10/5min), license
activate (20/min), license validate (60/min), downloads (30/min), and the admin-key check
itself (10/min, covering every admin endpoint uniformly since it's applied inside
`require_admin`). Verified live against the dev server: a 6th magic-link request within the
window correctly returned 429. Documented limitation: this is per-process, in-memory state --
correct for the current single-process local deployment, but would need a shared store (Redis)
before running multiple backend workers/instances in production.

Also added this phase: a migration-reversibility bug was found and fixed via a real
backup/restore + up/down/up migration rehearsal against local Postgres (see
`docs/PHASE_5_FINAL_SYNTHESIS.md`) -- an unnamed unique constraint made the license_key
migration's `downgrade()` impossible to execute. Fixed by naming the constraint explicitly.
Caught before any real customer data could exist against the old migration.

CSRF/cookie-across-real-HTTPS-origins (Section 49) remains unverified -- requires real hosted
staging, which doesn't exist yet (`docs/HOSTED_STAGING_DEPLOYMENT.md`).

## Phase 5.5 update

**Two real concurrency bugs found and fixed** (`tests/test_concurrency.py`, run against real
parallel database connections, not synthetic): (1) `licensing.py`'s `/v1/activate` had a
check-then-act race allowing concurrent requests to exceed `max_activations` -- fixed with
`SELECT ... FOR UPDATE` row-locking the entitlement during the check+insert sequence; (2)
`commerce.py`'s webhook idempotency check had the same shape of race -- fixed by claiming the
`event_id` via the database's own `UNIQUE (provider, provider_event_id)` constraint
(insert-and-commit first, catch `IntegrityError` for a concurrent duplicate) instead of a
SELECT-then-INSERT check. Both verified under real `ThreadPoolExecutor`-driven concurrent load
against Postgres.

**Production config now fails closed**: `config.py`'s `_validate_production_config` refuses to
start with `environment=production` if any of `nite_dsp_public_url`/`nite_dsp_api_url` still
point at localhost, `session_secret`/`admin_api_key` are still dev defaults/empty,
`licensing_private_key_path` still points at the staging keypair, or `database_url` still points
at a local staging/test database. Verified: fails with a full list of every violation; starts
cleanly in normal development mode. The website has an equivalent guard
(`check-production-config.mjs`) gating `npm run build:production`.

**`/health` and `/ready` endpoints added**, the latter checking real database connectivity.
Verified against an actual Postgres outage: `/ready` correctly returns 503 while `/health` stays
200 (liveness vs. readiness correctly separated); a real API call during the outage fails
predictably (500, no corrupted rows); both recover automatically once Postgres returns, with no
API process restart needed.

**Packaging-level finding, not application-level, but security-relevant**: the Homebrew
dependency-bundling gap described in `docs/PHASE_5_5_FINAL_SYNTHESIS.md` meant a shipped release
build could have silently required Homebrew-installed libraries to be present and *trusted* at
their original locations -- not a vulnerability in the traditional sense, but exactly the kind
of "works on my machine, fails/behaves differently on a customer's" gap that undermines the
integrity guarantee code-signing exists to provide. Fixed this phase.

## Phase 6 update

One real finding: `commerce.py`'s webhook-failure handler returned the raw Python exception text
(`str(exc)`) in the HTTP response body to the calling webhook sender -- not customer-facing, but
still an external caller that shouldn't see internal exception detail (potential DB/internal
state leakage). Fixed: the response now returns a generic "Webhook processing failed" message;
full detail is still persisted server-side (`webhook_events.processing_error`, visible only via
the fail-closed admin endpoint) for real debugging. Checked all other `HTTPException` call sites
in the backend for the same pattern -- none found. FastAPI's default (non-debug) exception
handling was also confirmed to not leak tracebacks for genuinely unhandled exceptions (`debug`
is not set on the `FastAPI()` app instance).
