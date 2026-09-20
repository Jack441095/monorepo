# NITE DSP — Commercial Platform Architecture (Design Only)

Phase 2, Sections 46-57. **Design document — nothing here is implemented or deployed.** No live
payments, no production database, no production licensing key. Per the master prompt's explicit
instruction: "Phase 2 should DESIGN the commercial platform. Do not start accepting real money."

## Governing constraint

**SmartSampleManager is the only product being commercialised right now.** This architecture
must support future NITE DSP products without exposing, packaging, or referencing any of them
(KENN, AutoMix, AudioGen, MIDI Generator, stem separation, etc. — see `docs/COMMERCIAL_SCOPE.md`).
The initial production catalogue contains exactly one product.

## Data model

```text
users
    id, email, password_hash / auth_provider_id, created_at

products
    id, slug ("smart-sample-manager"), name, status ("active" | "hidden"),
    current_version

purchases
    id, user_id, product_id, provider ("paddle" | ... ), provider_order_id,
    amount, currency, purchased_at, refunded_at (nullable)

entitlements
    id, user_id, product_id, purchase_id, license_type ("perpetual" | "subscription"),
    max_activations, revoked_at (nullable), created_at

activations
    id, entitlement_id, machine_id, activated_at, deactivated_at (nullable),
    last_seen_at

releases
    id, product_id, version, channel ("dev" | "beta" | "stable"),
    platform ("macos" | "windows"), published_at

downloads
    id, release_id, user_id (nullable for anonymous trial downloads), downloaded_at

webhook_events
    id, provider, event_type, payload_json, received_at, processed_at (nullable)
```

**Relationships use stable IDs, never hardcoded product assumptions.** `entitlements.product_id`
is a foreign key like any other row — nothing in this schema encodes "SmartSampleManager" as a
special case. Adding `product_id = "future-product-b"` later requires zero schema changes, only a
new `products` row (deliberately not created yet — see `docs/COMMERCIAL_SCOPE.md`'s "do not add
WIP products to the database" rule).

## NITE DSP Account (not "SmartSampleManager Account")

A customer creates one account (`users` table above) that can eventually own entitlements to
multiple products. The initial UI, even though only one product exists:

```text
NITE DSP ACCOUNT
    My Products
        Smart Sample Manager — Licensed — [Download] [Manage Activations]
```

Not "Smart Sample Manager Account" — the authentication/account layer must never be named or
architected as product-specific, since retrofitting a shared-account system after a
single-product one already has real users is exactly the kind of rebuild this design phase
exists to avoid.

## Entitlement flow

```text
USER
  ↓ (Merchant of Record checkout — see docs/COMMERCE_PROVIDER_DECISION.md)
PURCHASE
  ↓ (webhook_events row created, then processed)
PRODUCT (looked up by webhook payload's product identifier)
  ↓
ENTITLEMENT (created server-side only, never client-callable)
  ↓
ACTIVATIONS (one per machine, up to entitlement.max_activations)
```

The generic entitlement layer (`entitlements`, `activations`) carries no SmartSampleManager-
specific fields (no `max_library_size`, no `embedding_model_version`, nothing product-shaped) —
product-specific behavior belongs in the client, keyed off `product_id` + whatever `features`
list the license token carries (see below), not in the shared commercial schema.

## Licensing service (NITE DSP Licensing Service)

Preserves the existing Ed25519 client architecture verified sound in Phase 1
(`docs/LICENSING_PRODUCTION_GAP.md`) — **no cryptography rewrite**. The production transition:

| Gap (from Phase 1) | Production requirement |
|---|---|
| `localhost:8420`, no TLS | Real hosting behind HTTPS (see hosting note below) |
| Dev keypair generated ad hoc | Real production keypair, generated once, in the production environment only |
| Single SQLite file | Postgres (or equivalent) with backups |
| No admin-endpoint auth | Entitlement creation callable **only** from the payment webhook handler (server-to-server), never a public endpoint |
| No rate limiting | Add to `/v1/activate`/`/v1/validate` |
| No monitoring | Basic uptime/error alerting once real customers depend on it |

### Product-scoped license tokens

Extend the existing token schema with a `product_id` field, so a future multi-product NITE DSP
account can hold one license file containing multiple product entitlements, or the client can
request per-product tokens — either is compatible with this addition. Concept:

```json
{
  "schema_version": 2,
  "product_id": "smart-sample-manager",
  "entitlement_id": "ent_...",
  "license_type": "perpetual",
  "machine_id": "...",
  "issued_at": "...",
  "check_again_by": "...",
  "features": []
}
```

`schema_version` bump (Phase 1's token had no `product_id`) — the client's
`LicenseManager::verifyAndDecode` (per `docs/LICENSING_PRODUCTION_GAP.md`, architecturally
sound as-is) would need a small field addition, not a rewrite, when this is actually
implemented. **Not implemented this pass** — this section documents the schema evolution path.

### Private key management

The production Ed25519 private key must never exist in: git, client source/binary, installer,
CI logs, website frontend, developer documentation. **Recommended (provider-neutral)
requirement**: a managed secrets store (the specific provider depends on where the licensing
service is hosted — see below) that the licensing service reads from at process startup, never
from a file checked into any repository. Key generation happens once, directly in the production
environment, by a human with direct access to that environment (see
`docs/HUMAN_COMMERCIAL_REQUIREMENTS.md`) — this cannot be automated by this codebase.

## Hosting (design-level, no provider commitment yet)

Not decided this pass — a specific PaaS/VPS choice is a cost/ops decision for you, not an
architecture question this document needs to resolve. Requirements the choice must satisfy:
HTTPS out of the box or via a standard reverse proxy, Postgres availability (managed or
self-hosted), a secrets-manager equivalent, and support for a background worker or scheduled job
(for eventual rate-limiting/monitoring). Flagged in `docs/HUMAN_COMMERCIAL_REQUIREMENTS.md` as a
"REQUIRED BEFORE SALE" human action.

## Commerce abstraction (interface only, no implementation)

```text
interface CommerceProvider {
    createCheckout(product_id, customer_email) -> checkout_url
    verifyWebhook(headers, body) -> WebhookEvent
    retrieveOrder(order_id) -> Order
    refundOrder(order_id) -> RefundResult
    getCustomerPortalUrl(customer_id) -> url
}
```

The backend's entitlement-creation logic calls this interface, never a specific provider's SDK
directly — swapping Merchant of Record providers later (or adding a second one) means writing a
new implementation of this interface, not touching `entitlements`/`activations` logic. See
`docs/COMMERCE_PROVIDER_DECISION.md` for the actual provider recommendation — this interface is
provider-agnostic by design regardless of which one is chosen.

## Trial architecture (design only)

Recommended: 14-day full-featured trial, gated client-side by an unsigned local timestamp file
(simplest, matches the existing offline-first licensing design) rather than a server round-trip
requirement. **Trial expiry must never delete**: the sample library database, preferences,
metadata, or samples — the existing `docs/PLUGIN_STATE_ARCHITECTURE.md`/cache-DB design already
keeps all of that local and license-independent, so this is naturally satisfied by not building
any trial-expiry logic that touches those paths. Purchasing converts the installation by simply
replacing the trial flag with a real activated license — same binary, no reinstall.

## What Phase 3 would need to actually build

This document defines the target shape. Phase 3 (not started) would need to: stand up the
production database and hosting, generate and securely store the production keypair, implement
the `CommerceProvider` interface for the chosen provider, build the webhook handler, build the
NITE DSP account UI/API, and wire the client's license-check flow to the new token schema. None
of that is started — this is architecture only, per this phase's explicit scope.
