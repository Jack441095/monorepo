# NITE DSP Licensing Service — Production Architecture (Design Only)

Phase 3, Sections 17-24. **Design document — nothing here is deployed.** Transitions the
existing dev-only `licensing_server/` (verified against `server.py` directly this pass, not
assumed) toward a production-quality **NITE DSP Licensing Service**. Per Section 17's explicit
instruction: **the Ed25519 cryptographic architecture is not being rewritten** — Phase 1/2 both
confirmed the client-side design (`Source/Licensing/LicenseManager.cpp`) is sound. This document
covers the deployment/operational gap only.

## What's real in the dev server today (verified against `licensing_server/server.py`)

- Ed25519 signing/verification via libsodium/PyNaCl — same primitives production would use.
- Server-authoritative `/v1/activate`/`/v1/validate`/`/v1/deactivate` endpoints.
- `max_activations` default of **3**, enforced server-side (`server.py:209-212`).
- `OFFLINE_GRACE_PERIOD_SECONDS = 14 * 24 * 60 * 60` — a real, already-implemented 14-day offline
  grace period, honored both client-side (fresh-off-network and loaded-from-disk) per
  `docs/LICENSING_PRODUCTION_GAP.md`'s Phase 1 audit.
- **`POST /v1/admin/licenses` has zero authentication** — confirmed still true this pass. This is
  the one item that must never reach production as-is (Section 19).

## Production requirements (Section 18)

```text
HTTPS only              -- TLS termination at the hosting provider/reverse proxy
Authenticated internal
  license issuance       -- see "Admin endpoint security" below
Production database      -- Postgres (shared instance with the commercial schema --
                             docs/NITE_DSP_DATABASE_SCHEMA.md -- not a separate DB technology)
Secure signing key
  management               -- see docs/LICENSE_KEY_LIFECYCLE.md
Backups                    -- see docs/PRODUCTION_BACKUP_RECOVERY.md
Rate limiting                -- on /v1/activate and /v1/validate, abuse/brute-force protection
Structured logging            -- activation/validation events, no secrets logged
Monitoring                     -- activation failure rate, API error rate
Activation limits                -- already implemented (3), see "Activation limits" below
Deactivation                       -- already implemented, self-service (Section 23 requirement met)
Revocation                          -- entitlements.status = 'revoked' (docs/NITE_DSP_DATABASE_SCHEMA.md)
Offline grace                        -- already implemented (14 days), preserved as-is
Entitlement validation                 -- server re-derives status from entitlements table every call,
                                           matching the existing "server-authoritative" design
Product awareness                       -- license tokens gain a product_id field -- see
                                           docs/LICENSE_KEY_LIFECYCLE.md's schema_version bump
```

## Admin endpoint security (Section 19) — the one hard requirement

```text
CURRENT (dev):  PUBLIC CLIENT → POST /v1/admin/licenses → LICENSE CREATED   (no auth at all)

PRODUCTION:     PAYMENT WEBHOOK (Paddle) → verified signature → TRUSTED SERVER-SIDE
                HANDLER → internal call to license-issuance logic → ENTITLEMENT + LICENSE
                CREATED

                Admin/support tooling (Section 68) calls the same internal issuance logic
                through its own separately-authenticated admin session -- never through a
                publicly reachable endpoint.
```

The public internet must never be able to reach a code path that mints a license. This is a
straightforward requirement to implement correctly (move the endpoint behind
server-to-server-only network rules, or remove the public HTTP endpoint entirely in favor of a
function called directly from the webhook handler) — not implemented this pass because there is
no production server to implement it on yet, but the requirement itself is unambiguous and
should be the first thing built when deployment starts.

## Activation limits (Section 23)

**Recommendation: keep the existing 3 active computers.** Justification specific to this
product, not a generic default: SmartSampleManager is a desktop production tool, and 3
matches the realistic pattern of a single producer's own hardware (main studio machine, laptop,
maybe a home setup) without being generous enough to enable casual license sharing. The dev
server already implements this exact limit — no change needed, just carrying it forward.

Self-service deactivation is **already implemented** (`POST /v1/deactivate`) — satisfies
Section 23's explicit requirement without new work.

## Machine recovery (Section 24)

For lost laptop / dead SSD / motherboard replacement / OS reinstall / new computer: the existing
self-service deactivation already covers the common case (deactivate the old machine from the
NITE DSP Account UI, activate the new one — no support ticket needed). The one gap: **if the old
machine is physically inaccessible** (stolen, dead, can't boot), the customer can't run the
client-side deactivation. Recommended policy: allow self-service deactivation of *any* of a
customer's own activations from the NITE DSP Account web UI (not just from the client itself) —
this requires the account backend to expose a "deactivate this machine" action tied to
`activations.id`, calling the same server-side deactivation logic the client uses. Already
representable in the existing schema (`docs/NITE_DSP_DATABASE_SCHEMA.md`'s `activations` table)
without a data-model change — just a second UI entry point into the same backend operation.

## Offline license behavior (Section 22)

**Preserve exactly as-is** — the 14-day grace period is a real, tested, customer-friendly design
already in place. No constant phone-home behavior exists today and none should be introduced;
the client already degrades gracefully to the cached token's own grace-period judgment on
network failure (`docs/LICENSING_PRODUCTION_GAP.md`).

## What changes vs. what's preserved

| Aspect | Dev server today | Production |
|---|---|---|
| Cryptography | Ed25519, sound | **Unchanged** |
| Hosting | `localhost:8420`, no TLS | Real hosting, TLS |
| Database | SQLite | Postgres (shared with commercial schema) |
| Admin endpoint | Public, unauthenticated | Internal-only, called from verified webhook/admin session |
| Activation limit | 3 | **Unchanged** |
| Offline grace | 14 days | **Unchanged** |
| Signing key | Dev keypair, regenerated ad hoc | Production key, generated once in a real secure environment — see `docs/LICENSE_KEY_LIFECYCLE.md` |

## Status

**Design only.** No production server, database, or signing key exists. Deployment is gated on
the production hosting account in `docs/HUMAN_COMMERCIAL_REQUIREMENTS.md`.
