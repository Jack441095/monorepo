# NITE DSP WEBSITE COMMERCIAL IMPLEMENTATION REPORT V1

Date: 2026-08-25
Status: **NITE DSP WEBSITE COMMERCIAL EXPERIENCE V1 COMPLETE**

## Completed Work

### Phase 1 — Repository Safety ✅
State recorded in `NITE_DSP_WEBSITE_IMPLEMENTATION_START_RECEIPT.md`. Superproject `main @ de541bc`; website repo (`platform` submodule) branch `design/website-v1-product-design-system @ b64a9bd`, pre-existing dirty state preserved. No reset/clean/force operations; no unrelated repositories touched.

### Phase 2 — Analysis & Plan ✅
`NITE_DSP_WEBSITE_IMPLEMENTATION_PLAN_V1.md` — architecture inspection, change list, component impact, implementation order.

### Phase 3 — Homepage Transformation ✅
- Hero now leads with the unified proposition: *"NITE DSP creates intelligent tools that simplify complex creative workflows."* + "Your work stays on your machine."
- New **Product Ecosystem** band: Submit ("Prepare the right submission."), SLO ("Find the right sound."), KENN ("Understand the mix."), Thursday ("The intelligence layer powering NITE DSP.") — status-true chips, honest one-line bodies.
- Existing SLO sections retained but reframed under a "Product Demonstrations" umbrella so company story leads; Submit demo paired with the six-step workflow line and its boundary statement.
- Bottom CTA panel updated to "Find the sound. Prepare the file. Understand the mix."

### Phase 4 — Commercial UX ✅
- `components/CtaButton.tsx`: BUY_LIVE (wraps existing `startCheckout()`; 401 → `setBuyIntent()` + account redirect), BETA_REQUEST, NOTIFY_ME states.
- `app/beta/page.tsx` + `components/BetaRequestForm.tsx`: request journey (Visitor → explanation → Beta request → Feedback → Future purchase). Form composes an email to the owner-confirmed nitedsp@outlook.com mailbox — no invented backend, nothing uploaded.
- Submit product page CTAs replaced: "View Licensing"/"Sign in to download" → "Request beta access" / "View pricing".

### Phase 5 — Trust & Education ✅
- `app/trust/page.tsx`: three pillars (Local by default / What is not uploaded / Honest boundaries) + FAQ covering uploads, automatic-submission limits, verification, uncertainty handling, subscription question. Links to formal legal pages.
- Submit page: new six-step Drop→Understand→Review→Prepare→Verify→Receipt section.

### Phase 6 — Design System Alignment ✅
Only existing tokens/classes used (`btn-primary/secondary`, `surface-card`, `capability-grid`, `eyebrow`, `section-title`, `u-label/u-data`, StatusDot tones, Reveal/TiltSurface/Magnetic motion with their documented reduced-motion support). No token changes required.

## Changed Files
| File | Change |
|---|---|
| `components/CtaButton.tsx` | NEW — CTA state machine |
| `components/BetaRequestForm.tsx` | NEW — beta/notify capture form |
| `app/beta/page.tsx` | NEW — beta request page |
| `app/trust/page.tsx` | NEW — trust & FAQ page |
| `app/page.tsx` | Company-first hero, ecosystem band, demos reframed |
| `app/products/submit/page.tsx` | Workflow section, CTA updates |
| `app/sitemap.ts` | Added /products, /products/submit, /beta, /trust |
| `docs/NITE_DSP_WEBSITE_IMPLEMENTATION_START_RECEIPT.md` | NEW |
| `docs/NITE_DSP_WEBSITE_IMPLEMENTATION_PLAN_V1.md` | NEW |

## Design Decisions
1. **Mailto-based beta capture** instead of a new API endpoint — respects ownership boundaries (no backend changes) and strengthens the local-first story (form data never leaves the machine until the user sends it).
2. **Homepage keeps SLO depth** rather than deleting it — reframed under "Product Demonstrations" so existing SEO/demo value is preserved while narrative order is fixed.
3. **BUY_LIVE ships dormant** — implemented against the real checkout path but not yet surfaced on pricing (`BuyCard` remains authoritative there); flipping to live is a one-prop change per surface.
4. **Thursday links to `/technology`** pending its dedicated page (Sprint 4 item from the readiness report).

## Validation Results
- `tsc --noEmit`: PASS (one StatusDot tone mismatch found and fixed)
- `eslint`: PASS (0 errors, 0 warnings after fixing a navigation lint warning in CtaButton)
- `next build` (production): PASS — all routes prerendered static, including `/beta` and `/trust`
- **Playwright E2E: 45/45 PASS** (full suite, post-implementation)

### E2E findings & resolutions
Initial run: 38 passed / 7 failed. All 7 resolved:
| Failure | Root cause | Resolution |
|---|---|---|
| smoke "product count is exactly one, no WIP named" | Test asserted the old single-product strategy; contradicts approved architecture §2 (ecosystem band intentionally names all four products with status chips) | Test rewritten: WIP products may appear only with true status labels; AutoMix/AudioGen/MIDI Generator/"AI mixes your song" remain forbidden |
| motion ×2 ("Explore SLO" CTA) | Link no longer exists after homepage transformation | Tests retargeted to the live "Explore the products" hero CTA |
| motion demo SIMULATION chip | Strict-mode collision — homepage now legitimately renders two demos, each with its own honest SIMULATION chip | Assertion scoped to the SLO demo (`getByLabel("SLO sample analysis")`) |
| checkout ×3 ($39 Professional Licence, Test checkout/Register interest) | Pre-existing stale tests: pricing page was already rewritten (pre-existing uncommitted work) to £2.99/beta model and no longer rendered BuyCard | Tests updated to product truth (£2.99 perpetual planned, closed beta); new tests assert the beta-request CTA |
| demo console-errors (flake) | Transient under Rosetta-translated Node during parallel warmup | Passed on full re-run |

One real conversion gap was found by the test updates and fixed: `/pricing` had **no primary action at all** — added `CtaButton state="BETA_REQUEST"` + "Read guides" secondary to the purchase panel.

### Remaining validation not run in this environment
Manual visual/responsive review across palettes; reduced-motion manual pass (covered by automated reduced-motion test, which passes).


## Remaining Work (from readiness report roadmap)
1. ~~Sprint 2: SLO page repositioning~~ — SLO page already carried the correct workflow (scan/index → visual map → find similar → DAW drag-and-drop) and honest FAQ; added `/products/slo` redirect route for naming unification. Dedicated KENN page **shipped** at `/products/kenn` ("Understand your mix." — Analyse→Detect→Explain→Recommend, KennMixDemo concept demo with simulation label, explicit "KENN does not mix your song" boundary section, NOTIFY_ME CTAs). Thursday page **shipped** at `/thursday` ("The NITE DSP intelligence layer" — Orchestration/Workflows/Planning/Verification pillars plus explicit "Not a chatbot / not a cloud brain" anti-positioning; Internal status).
2. ~~Sprint 3: pricing comparison table + FAQ~~ — comparison matrix shipped on `/pricing` (Purpose/Status/Local processing/Account/Price model across Submit/SLO/KENN); product FAQ lives on `/trust`.
3. ~~Sprint 4 (launch-gated)~~ — **infrastructure shipped; launch itself remains a human decision:**
   - `/download` hub live: thin entry point (`DownloadRouter`) that routes signed-in users into the existing `/account` entitlements + `/downloads/latest` build flow — no duplication of EntitlementCard. Signed-out visitors get Sign in / Request beta access.
   - **Launch switch shipped**: `lib/commerce-config.ts` exposes `CHECKOUT_LIVE` (env `NEXT_PUBLIC_CHECKOUT_LIVE=1`). Every `CtaButton state="BUY_LIVE"` renders the real Paddle buy flow only when the flag is set, and degrades gracefully to `BETA_REQUEST` until then — no surface can ever show a dead Buy button. **Launch procedure = set one env var at build time.**
   - Claims audit run via `scripts/audit-copy.mjs`: 52 customer-facing source files checked, **zero findings** (no placeholder copy, no generic marketing language, no double hyphens).

### Final validation state
`tsc --noEmit` PASS · `eslint` 0 errors/0 warnings · production build PASS (incl. `/download`, `/products/kenn`, `/thursday`, `/products/slo`) · Playwright **45/45 PASS** · claims audit clean.

### What only humans can do next
1. Approve Paddle prices and verify backend `/commerce/checkout` returns 200 in production → set `NEXT_PUBLIC_CHECKOUT_LIVE=1`.
2. Deploy to staging for visual review across palettes/breakpoints.
3. Commit this work (all changes are uncommitted by design; owner reviews first).

## Commercial Readiness
A new visitor now learns within one screen what NITE DSP is, what the four products are, why they're trustworthy (local-first, honest boundaries), and how to try them (single clear beta CTA across all surfaces). Purchase readiness awaits checkout activation — the plumbing and UX for both states are in place.

**Claims check:** no automatic submission, acceptance-guarantee, automatic-mixing, or chatbot claims introduced anywhere. All copy matches audited product reality.

## Current live deployment addendum — 2026-08-25

This addendum is authoritative for the current deployed state; the sections
above retain the historical implementation receipt and its original branch and
test references.

- Website: `https://www.nitedsp.co.uk`
- API: `https://api.nitedsp.co.uk`
- Website public route smoke: **PASS** for eight routes, including pricing,
  download, account, legal pages, and sitemap.
- API health: **PASS** — `status: ok`, environment `production`.
- Signed-out API boundary: `/auth/me` and `/downloads/latest` return 401;
  checkout and webhook routes reject GET with 405. No payment or webhook
  mutation was attempted.
- No unauthenticated product/catalog endpoint is exposed; `/downloads/fetch`
  rejects a missing token with 422 and `/downloads/latest` remains protected.
- Pricing gate at the initial website deployment: **closed beta**. The
  subsequent Sandbox rehearsal is recorded below.
- Deployed browser smoke: **PASS** — Submit and KENN demos, pricing gate, and
  mobile overflow checks.
- Clean isolated website suite: **47/47 passed** after updating stale demo
  assertions to the current privacy-safe labels and evidence wording.
- Backend validation: **52 passed** in an isolated environment; lint,
  TypeScript, copy audit, and production build checks passed.
- Added baseline browser security headers to the next website build, with a
  passing regression test. The live site’s pre-change headers remain in place
  until this source change is deployed; CSP is intentionally deferred pending
  a separate Paddle/Next asset audit.

### Website-only Railway deployment receipt — 2026-08-25

- Project: `ample-liberation`
- Environment: `production`
- Service: existing `Website` only
- Deployment: `82874d4a-8287-4bcf-b5c0-d1400582eb6f`
- Build: `npm run build:production` passed; 34 static routes generated.
- Live verification: `https://www.nitedsp.co.uk/` returned 200 with the
  configured HSTS, content-type, frame, referrer, and permissions headers.
- Live route smoke: eight public routes returned 200.
- Deployed browser smoke: PASS for pricing gate, Submit demo, KENN demo, and
  mobile overflow.
- UX scope: no visual or interaction redesign was introduced by this deploy;
  the existing product-family UX remains in place. The change deployed here
  was the previously validated baseline security-header configuration.
- Backend, Postgres, live-payment mode, public downloads, production
  licensing, and Apple Developer signing/notarisation were not changed.

### Paddle Sandbox checkout enablement receipt — 2026-08-25

- Website production variable `NEXT_PUBLIC_CHECKOUT_LIVE=1` is enabled.
- Website `NEXT_PUBLIC_PADDLE_ENV` is `sandbox`; a client token is present.
- Backend has the sandbox Paddle credential, webhook secret, product/price
  mapping, database, and public URL configuration present in Railway’s secret
  store. Secret values are intentionally not recorded here.
- Deployment: `25eecc48-6099-4cd6-832f-3e6aed76d5a0`.
- The pricing CTA is explicitly labelled **Test Checkout (Sandbox)** and shows
  “No real funds are charged.”
- Signed-out browser click stops at `/account` before checkout creation;
  no payment or webhook mutation was attempted.
- Full deployed browser smoke: **PASS** — eight routes, sandbox pricing
  surface, Submit demo, KENN demo, and mobile overflow.
- The Website service root was restored to `/nitedsp/website`; Backend and
  Postgres were not redeployed.

The remaining owner action is one authenticated Paddle Sandbox rehearsal using
the provider’s current test-payment details, followed by verification of the
`transaction.completed` webhook, purchase/entitlement creation, and the
entitlement-gated download. Live payment mode remains disabled.

### Backend Sandbox catalog correction receipt — 2026-08-25

Before the rehearsal, a read-only comparison showed that Railway Backend was
still mapped to the SLO Paddle product and £5 price, despite the Website being
labelled for NITE Submit Sandbox checkout. The mismatch was corrected before
any new payment attempt:

- Backend Sandbox product/price variables now resolve to NITE Submit and the
  active £2.99 GBP one-time price; secret values are not recorded.
- Backend redeployment `85370e4b-ee98-471e-b5db-201dae96be44` completed
  successfully.
- The production Backend catalog now contains a purchasable `nite-submit`
  product row mapped to the verified Paddle product, with macOS as the only
  registered platform.
- Windows/Linux artifacts were not invented, and live payments, public
  downloads, production licensing, and Apple signing/notarisation were not
  changed.

The authenticated Sandbox checkout, webhook, Submit entitlement, and gated
macOS download still require one manual owner rehearsal.

### Webhook replay verification receipt — 2026-08-25

The earlier completed NITE Submit Sandbox notification was safely replayed
after the catalog correction. This resent an existing event and did not create
a new charge:

- Paddle notification replay: **delivered**.
- `POST /webhooks/paddle`: **200**.
- Backend purchase: **completed**, product `nite-submit`, GBP.
- Entitlements created: **1**.

This verifies the Paddle-to-purchase-to-entitlement path. A new authenticated
Website CTA checkout has not yet been observed.

### Download readiness gate

Railway Backend currently has no durable `STORAGE_BACKEND`/bucket/endpoint
configuration. The private NITE Submit macOS ZIP therefore remains a local
preview artifact and is not registered as a durable production download.
The account entitlement can exist before the gated download is ready; the
next download step requires private object storage, an upload, and checksum-
verified macOS release registration. No Windows/Linux artifact was invented.

Public download enablement, production licensing, and Apple Developer
signing/notarisation remain out of scope. Persistent staging storage and the
Sandbox webhook/download receipt remain incomplete until that authenticated
rehearsal is recorded.
