# NITE DSP INTERACTION V1 / WEBSITE MOTION V1 — BROWSER QA

Runner: Playwright 1.62.x, chromium project (Desktop Chrome), production
build served by the config's `webServer` (`npm run build && npm run start
-- -p 3100`).

## Suite composition

| File | Tests | Covers |
| --- | --- | --- |
| `tests/smoke.spec.ts` (existing) | 24 | 18 critical routes 200s, homepage identity, desktop/mobile nav, WIP-name safety, no localhost/railway links, sitemap, Ableton experimental labelling |
| `tests/checkout.spec.ts` (existing) | 5 | Pricing TBC visible, single primary action, sign-in routing, purchase-param handling |
| `tests/motion.spec.ts` (new) | 6 | Interaction-layer regression contracts (below) |

## New regression coverage (`tests/motion.spec.ts`)

1. **Magnetic CTA retains click navigation** — hover + pointer drift while
   engaged, then click; asserts navigation completes (hit target stable).
2. **Demo scan + disclosure** — selecting a sample resolves its category
   and the "Illustrative workflow simulation" + `SIMULATION` labels remain.
3. **Reduced motion** — content never hidden (opacity > 0.9 on a
   Reveal-wrapped heading), CTA navigates.
4. **Touch/mobile overflow** — 390×844 `hasTouch` context: zero horizontal
   overflow on `/`, `/products`, SLO, `/pricing`.
5. **Nav indicator** — aligns (±8px) with the `aria-current` link centre on
   `/pricing`; state conveyed accessibly.
6. **Console hygiene** — no console/page errors across the three
   high-interaction routes.

Deliberately NOT tested: exact animation coordinates, transform values,
timing — all judged brittle per spec.

## Results

| Run | Result |
| --- | --- |
| Baseline (before programme) | 29/29 PASS |
| Final full suite (35 tests) | **35/35 PASS** (1.9 min) |
| Motion suite stability | 6/6 repeated ×3 (one initial failure cluster was traced to a stale manually-started server being reused against a swapped build — environment artifact, not code) |

## Manual QA matrix

| Route | Mouse | Trackpad | Keyboard | Touch emulation | Reduced motion |
| --- | --- | --- | --- | --- | --- |
| `/` | PASS | PASS | PASS | PASS (static) | PASS |
| `/products/smart-sample-manager` | PASS | PASS | PASS | PASS | PASS |
| `/products` | PASS | PASS | PASS | PASS | PASS |
| `/pricing` | PASS | PASS | PASS | PASS | PASS |
| `/support`, `/learn`, `/account` | PASS (minimal motion) | PASS | PASS | PASS | PASS |

PASS = content complete, no overflow, no clipped focus rings, no console
errors, interactions land.

## Viewport requalification

1440 / 1280 / 1024 / 768 / 390 exercised via capture script
(`scripts/capture-visual-review.mjs`) + manual pass; required review set
(Homepage, SLO, Products @ 1440/768/390) committed under
`docs/motion-review/`. No overflow, no transformed-content escape, no
clipped focus rings observed at any width.
