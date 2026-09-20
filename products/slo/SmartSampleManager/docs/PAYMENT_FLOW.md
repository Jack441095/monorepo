# NITE DSP Payment Flow (Design Only)

Phase 3, Sections 27-32. **Design document — no live or sandbox payment integration exists.**
Builds on `docs/COMMERCE_PROVIDER_DECISION.md` (Paddle) and
`docs/NITE_DSP_DATABASE_SCHEMA.md`'s `purchases`/`entitlements`/`webhook_events` tables.

## Sandbox before live (Section 27)

Every flow below is designed to be built and tested in Paddle's sandbox/test mode first. Real
charges are explicitly out of scope for this phase — per the master prompt's own Section 27/87,
that's Phase 4, and only after: the product is distributable (still blocked on Apple Developer
credentials + clean-machine test), legal pages exist (blocked on legal review), licensing works
(architecture designed, not deployed), downloads work (designed, not deployed), refund path works
(designed below, not tested against a real account), and you explicitly approve going live.

## Purchase flow (Section 29)

```text
CUSTOMER
    ↓ clicks "Buy" on the product page
CHECKOUT
    ↓ Paddle-hosted checkout (never a custom card-entry form -- Section 29's
      "never store raw payment card information" is satisfied by construction,
      since NITE DSP's own servers never see card data at all)
PAYMENT PROVIDER (Paddle)
    ↓ processes payment, then fires a webhook
VERIFIED WEBHOOK
    ↓ NITE DSP backend verifies Paddle's webhook signature before trusting
      the payload at all -- see "Webhook security" below
PURCHASE RECORD
    ↓ INSERT INTO purchases ... ON CONFLICT (provider, provider_order_id) DO NOTHING
      (idempotent -- duplicate webhook delivery never creates a duplicate row)
ENTITLEMENT
    ↓ INSERT INTO entitlements (user_id, product_id, purchase_id, license_type='perpetual', ...)
    ↓ license token issued via the (now-internal, never-public) issuance logic
      in docs/PRODUCTION_LICENSING_ARCHITECTURE.md
CUSTOMER
    sees the new entitlement immediately in their NITE DSP Account -- no
    manual step, no support ticket, no polling required on the customer's end
```

**Critical correctness point (Section 29)**: `/purchase/success` (the URL Paddle redirects the
browser to after checkout) is **never** treated as proof of purchase. It's a UX convenience (show
a "thanks, check your email" message) — the actual entitlement is only ever created by the
verified webhook, which arrives server-to-server and can't be spoofed by a customer manipulating
their browser's redirect URL.

## Webhook security (Section 30)

```text
Incoming webhook
    ↓ Verify Paddle's cryptographic signature (HMAC or their documented scheme --
      exact mechanism per Paddle's current API docs at implementation time)
    ↓ Reject anything that doesn't verify -- log and drop, never process
    ↓ INSERT INTO webhook_events (provider, event_type, provider_event_id, payload_json)
      ON CONFLICT (provider, provider_event_id) DO NOTHING
    ↓ If the insert was a no-op (row already existed) -- this is a duplicate
      delivery, already processed, return 200 OK and do nothing further
    ↓ If the insert succeeded (first time seeing this event) -- process it
      inside a database transaction: create/update the purchase row AND the
      entitlement row atomically, then mark webhook_events.processed_at
    ↓ If processing fails partway -- the transaction rolls back, processed_at
      stays null, and the row is eligible for a retry (either Paddle's own
      webhook retry, or a scheduled job that re-processes unprocessed rows)
```

This directly satisfies Section 30's mandatory list: cryptographic verification, idempotency
(the `UNIQUE (provider, provider_event_id)` constraint), event persistence (every webhook is
stored, not just acted on and discarded), duplicate protection, transaction-safe entitlement
creation, and a retry path via the unprocessed-events query already indexed in the schema
(`idx_webhook_events_unprocessed`).

## Refunds (Section 31)

```text
Paddle refund event received (webhook)
    ↓
UPDATE purchases SET status='refunded', refunded_at=now() WHERE provider_order_id = ...
    ↓
UPDATE entitlements SET status='suspended' WHERE purchase_id = <that purchase>
```

**Recommendation: `suspended`, not `revoked`, on refund.** Suspended means the license stops
validating (client sees `invalid` on next check, respecting the existing offline-grace design
until then) but the historical record is fully preserved — if a refund is later reversed
(disputed, customer re-purchases, goodwill reinstatement), the entitlement can be flipped back to
`active` without recreating anything. `revoked` is reserved for a deliberate, permanent
revocation (e.g. confirmed fraud/chargeback abuse), which is a one-way door by design.

No row is ever deleted — matches Section 31's explicit "do not delete historical records."

## Chargebacks (Section 32)

Handled as their own event type, distinct from a normal refund, since a chargeback (initiated by
the customer's bank, often adversarial/fraud-related) carries different weight than a customer-
requested refund. Same mechanical path (`entitlements.status='suspended'`), but the audit trail
(`purchases.status='disputed'`, preserved `webhook_events` row) distinguishes *why* — relevant if
a pattern of chargebacks from one customer needs manual review before ever re-activating that
account's entitlements.

## Commerce abstraction (Section 28) — provider-agnostic interface

```typescript
interface CommerceProvider {
    createCheckout(productId: string, customerEmail: string): Promise<{checkoutUrl: string}>;
    verifyWebhook(headers: Headers, rawBody: string): WebhookEvent | null;  // null if signature invalid
    retrieveOrder(orderId: string): Promise<Order>;
    retrieveCustomer(customerId: string): Promise<Customer>;
    refundOrder(orderId: string): Promise<RefundResult>;
    createCustomerPortalUrl(customerId: string): Promise<string>;
}
```

All entitlement-creation/refund logic in the backend calls this interface, never Paddle's SDK
directly — a future second provider (or a second MoR if Paddle's terms change) means writing a
new implementation of this interface, not touching `entitlements`/`purchases` logic anywhere
else.

## What's explicitly not built this pass

No Paddle account exists (human action — `docs/HUMAN_COMMERCIAL_REQUIREMENTS.md`), so nothing
above has been implemented against a real API, sandbox or otherwise. This document is the
sequence/schema/security design ready to implement once that account exists.

## Status

**Design only.**
