# Paddle Sandbox Validation

# HUMAN ACTION REQUIRED

```text
STATUS: BLOCKED -- no Paddle account (sandbox or otherwise) exists
OWNER:  You
BLOCKS: Sections 15-19 of the Phase 5 master prompt (real sandbox checkout, real
        provider-delivered webhooks, real refund-path testing)
REASON: Creating and verifying a business account (even sandbox) involves KYC/business
        verification this environment cannot complete -- see
        docs/HUMAN_COMMERCIAL_REQUIREMENTS.md
```

## What was validated instead (Phase 4, reconfirmed this phase)

Real HMAC-SHA256 webhook signature verification, real idempotency enforcement (duplicate
`event_id` correctly produces `already_processed`, not a duplicate purchase), and real
purchase→entitlement transaction logic -- all against a self-signed payload matching Paddle
Billing's documented `transaction.completed` schema. This proves the code's logic is correct; it
is explicitly not the same as a real Paddle sandbox account delivering a real webhook to this
server. Section 16's exact instruction ("The previous local simulated/implemented flow is not a
substitute for hitting the real provider sandbox") is accepted as true and not worked around.

## What happens once a Paddle sandbox account exists

1. Set `PADDLE_API_KEY` and `PADDLE_WEBHOOK_SECRET` from the real sandbox account (never
   committed -- `.env` is gitignored).
2. Verify `PaddleProvider.configured` flips to `True` and `create_checkout_url` (currently
   raising `NotImplementedError` deliberately) gets a real implementation against Paddle's
   Checkout API.
3. Run a real sandbox checkout, let Paddle deliver the real webhook, and confirm the same
   purchase→entitlement path that already passes against simulated payloads.
4. Verify product/price ID mapping (Section 17) -- Paddle's `product_id` must map to the
   internal `products.id` slug (`smart-sample-manager`) directly, never by display-name
   matching, which `commerce.py`'s `_handle_transaction_completed` already does correctly
   (`data["items"][0]["price"]["product_id"]`) -- this becomes end-to-end testable only once a
   real Paddle product exists to map from.
5. Replay a real sandbox webhook to confirm idempotency against the real provider, not just the
   simulation (Section 18).
6. Exercise a real sandbox refund and confirm entitlement revocation (Section 19) -- the
   `entitlements.status` transition itself is already implemented and tested
   (`docs/LICENSING_IMPLEMENTATION.md`'s "refund" step in `test_full_purchase_to_activation_flow`);
   only the trigger (a real refund webhook vs. an admin manual revoke) would be new.

None of this is fabricated here. Section 71-72 apply regardless: Paddle is not required for
private beta, and live payments stay off in Phase 5 either way.
