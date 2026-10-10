# Commerce runbook

How we find and fix failed money webhooks and unsent purchase emails. All
endpoints below need the admin key (`X-Admin-Key` header).

## Unsent purchase confirmations

A dead mail provider during fulfilment leaves the licence committed but the
confirmation email unsent. The webhook still returns 200, so Stripe treats
the event as delivered and does not retry it on its own. Completed purchases
wait for a later duplicate delivery replay, an admin resend, or this sweep.
Refunded and disputed purchases stay out of the retry backlog; the resend
endpoint rejects them so a stale recovery job cannot mail a stored licence.

1. List the backlog (partial index `ix_purchases_unsent_confirmation` keeps
   this cheap as sent rows accumulate):
   `GET /admin/purchases/unsent-confirmations`
2. Fix the mail provider first, then resend each row with its stored licence
   key: `POST /admin/purchases/{purchase_id}/resend-confirmation`
3. Repeat step 1 until it returns `[]`. For a large backlog, call
   `sweep_unsent_confirmations(limit=...)` in `app/stripe_commerce.py` from a
   cron job or a shell instead of clicking each row. Keep the sweep limited to
   completed purchases; resolve a refund or dispute before any manual resend.

## Failed webhooks

1. `GET /admin/webhooks/failed` lists events whose `processing_error` is set.
2. Look up the purchase by Stripe Checkout session ID:
   `GET /admin/purchases/search?provider_order_id=...`
3. Refund or dispute: the webhook already sets `purchase.status` to
   `refunded` (full refund) or `disputed`. Revoking the licence is a manual
   decision, never automatic:
   - If the buyer keeps the product, resolve the purchase status with an
     operator before resending; the endpoint rejects refunded or disputed rows.
   - Revoke the licence if the refund stands:
     `POST /admin/entitlements/{entitlement_id}/revoke` with a reason.
     Find the entitlement id in the `purchases/search` response.

## Downgrade guard

Never downgrade past `e7a1b2c3d4f5` while
`GET /admin/purchases/unsent-confirmations` is non-empty. That migration
holds `confirmation_email_sent_at`, the only record of which licences still
owe a confirmation email -- dropping the column destroys the backlog, and
dropping `ix_purchases_unsent_confirmation` blinds the sweep that finds it.
Drain the sweep to zero first, then downgrade.
