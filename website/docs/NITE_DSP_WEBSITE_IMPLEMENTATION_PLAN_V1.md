# NITE DSP WEBSITE IMPLEMENTATION PLAN V1

Authority: `NITE_DSP_WEBSITE_AUDIT_V1.md`, `NITE_DSP_WEBSITE_COMMERCIAL_ARCHITECTURE_V1.md`, `NITE_DSP_CONVERSION_COMMERCIAL_UX_V1.md`, `NITE_DSP_WEBSITE_COMMERCIAL_READINESS_REPORT_V1.md`.

## Current Architecture
- Next.js 16 App Router / React 19 / Tailwind 4 via PostCSS; design tokens in `app/globals.css` (Palette A/B/C themes, motion tokens, `.panel/.chip/.kbd` primitives).
- Motion: `components/motion/` (LightField, Magnetic, Reveal, TiltSurface, WorkflowFlow, StatusDot) with reduced-motion support documented.
- Demos: `SubmitPrepDemo`, `KennMixDemo`, `AudioAnalysisDemo` (browser-local, labelled simulated).
- Commerce: `BuyCard.tsx` (Paddle.js init + buy-intent), `lib/checkout.ts` (`startCheckout`, server-resolved prices), backend `/commerce/checkout`, webhook entitlements.
- Routes: home, products (+submit, smart-sample-manager), pricing, learn hub, technology, support, account, auth/verify, legal set.
- Support contact: nitedsp@outlook.com (owner-confirmed mailbox).

## Required Changes (this programme)
| # | Change | Files |
|---|---|---|
| 1 | CTA state machine: BUY_LIVE / BETA_REQUEST / NOTIFY_ME | new `components/CtaButton.tsx`; used on home, submit, pricing |
| 2 | Homepage transformation: company proposition hero + product ecosystem band | rewrite sections of `app/page.tsx` |
| 3 | Beta request journey | new `app/beta/page.tsx`, `components/BetaRequestForm.tsx` (mailto-based — no invented backend) |
| 4 | Trust page: privacy, local processing, data boundaries, FAQ | new `app/trust/page.tsx` |
| 5 | Submit workflow storytelling (six steps) | extend `app/products/submit/page.tsx` |
| 6 | Sitemap/nav coverage for new routes | `app/sitemap.ts`, `components/SiteHeader.tsx` |

Explicitly NOT changed: product logic, demo internals, checkout API contract, legal pages' claims.

## Component Impact
- `CtaButton` (new, client): wraps `startCheckout()` for BUY_LIVE; links to `/beta` for BETA_REQUEST; NOTIFY_ME renders disabled-with-context link to `/beta`. Reuses `btn-primary/btn-secondary` classes and `Magnetic`.
- `page.tsx`: hero copy replaced (company-first); SLO-heavy mid-sections retained but reframed under a "Product demonstrations" eyebrow so the company story leads.
- `SiteHeader`: unchanged nav labels (Products/Pricing already cover new pages via existing IA); no new top-level nav to avoid clutter.
- No changes to globals.css tokens — Phase 6 alignment achieved by using existing tokens only.

## Implementation Order
1. CtaButton → 2. Beta page/form → 3. Homepage → 4. Submit workflow section → 5. Trust page → 6. Sitemap → 7. Validate (lint, typecheck, production build) → 8. Final report.

## Validation Plan
`npm run lint`, `npx tsc --noEmit`, `npm run build` inside `platform/website`. Playwright e2e not run in this session (no browser guarantee in environment); manual route checks via build output.
