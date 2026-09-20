# POLAR SPIKE — setup + live-fire plan (D-01)

## What exists (commit `edbd5f4` on `exec/polar-spike`, monorepo — stacks on `exec/cleanup-website`)
- `backend/app/polar_provider.py`: PolarProvider(CommerceProvider), router `/commerce/polar-checkout` + `/commerce/polar-webhook`, idempotent fulfill (Purchase+Entitlement+license email). Verified: imports clean, fail-closed both paths without token/secret, interface holds.
- `website/lib/polar-checkout.ts`: tier-only client mirroring `checkout.ts`.
- NOT done: `main.py` router include (1 line), `npm install @polar-sh/sdk @polar-sh/nextjs` (guardrail), any live call.

## Owner setup (free, ~30 min)
1. polar.sh signup → sandbox organization → organization access token.
2. Sandbox products: Submit intro + regular → IDs into backend env:
   `POLAR_ENV=sandbox`, `POLAR_ACCESS_TOKEN`, `POLAR_WEBHOOK_SECRET`,
   `POLAR_PRODUCT_SUBMIT_INTRO`, `POLAR_PRODUCT_SUBMIT_REGULAR`.
3. Sandbox webhook endpoint → `<backend>/commerce/polar-webhook`; note the exact signature header name + order event names from first delivery into the VERIFY-AT-LIVE-FIRE markers.
4. Wire `polar_router` in `main.py` (include_router, one line) on a clean tree.

## Live-fire matrix (sandbox only, never prod cards)
1. Create checkout → 200 + usable URL → complete with sandbox card → webhook 200 → Purchase+Entitlement rows + license email logged.
2. Duplicate delivery (same order id twice) → second is `duplicate:true`, exactly ONE entitlement.
3. Tampered body / missing signature → 400, no rows.
4. Unknown product id → 200 + `unmapped`, no retry storm.
5. Replayed old event → rejected (add timestamp bound if Polar sends ts; confirm header first).
6. Confirm checkout envelope + customer-email location; tighten `_fulfill_order` if Polar uses customer_id references (Paddle pattern: Customers-API lookup).

## Kill/continue
- Pass all 6 → Polar is charge-ready; decide Paddle-replace vs dual-run.
- Any fail after 1 day of fixes → stay on Paddle (integration already correct); Polar cost was one scaffold commit.
