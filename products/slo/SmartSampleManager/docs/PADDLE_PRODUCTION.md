# Paddle Production

Phase 6, Sections 51-57, 96-97. Distinct from `docs/PADDLE_SANDBOX_VALIDATION.md` (Phase 5) --
this covers what happens *after* sandbox validation succeeds, on the path to real money.

## Status: BLOCKED EXTERNAL at every stage

No Paddle account of any kind exists yet (sandbox or production). Nothing in this document has
been executed. Per Section 20/56/57's explicit instructions, none of it is simulated as if it
had.

## Sandbox → production sequence (for when a sandbox account exists)

1. Real sandbox checkout → real webhook delivery → verified signature → purchase → entitlement
   → account → download → activation (Section 51's full loop) -- `commerce.py`'s logic is
   already written and unit-tested against simulated payloads matching Paddle's documented
   schema, but has never received an actual Paddle-originated webhook.
2. Product/price ID mapping (Section 52) -- verify Paddle's real product/price IDs map to the
   internal `smart-sample-manager` slug directly (`_handle_transaction_completed` already reads
   `data["items"][0]["price"]["product_id"]`, never a display name).
3. Webhook security under real conditions (Section 53) -- HMAC verification, duplicate delivery,
   malformed events, wrong secret, unknown product, transaction atomicity -- all logic exists
   and is unit-tested (`tests/test_e2e.py`, `tests/test_concurrency.py`); needs re-confirming
   against Paddle's actual delivery behavior once reachable.
4. Real sandbox concurrency (Section 54) -- Phase 5.6's database-backed idempotency fix
   (`UNIQUE (provider, provider_event_id)`, insert-first-not-check-first) should survive real
   provider retry/replay behavior; this needs confirming against the real thing, not just
   `ThreadPoolExecutor`-simulated concurrency.
5. Refund sandbox flow (Section 55) -- exercise a real sandbox refund, verify purchase status,
   entitlement status, and audit trail; the entitlement-revocation code path is already tested
   (`tests/test_e2e.py`'s "refund" step, currently triggered via admin revoke, not a real refund
   webhook).
6. Chargeback/dispute handling (Section 56) -- no code path distinguishes a dispute from an
   ordinary refund yet; needs building once Paddle's actual dispute event shape is known (not
   guessed here).

## Production separation (Section 96)

`PADDLE_API_KEY`/`PADDLE_WEBHOOK_SECRET` are read from environment only, never committed
(`nitedsp/backend/.env.production.example` shows them as empty placeholders). Sandbox and
production would use entirely separate Paddle accounts/keys by Paddle's own design -- nothing in
this codebase conflates the two.

## Live payment hard gate (Section 57, 97)

**Live Paddle is not enabled and will not be enabled without a `docs/LIVE_COMMERCE_GO_NO_GO.md`
report and explicit human approval.** No such report exists yet -- see that document's current
(not-ready) status.
