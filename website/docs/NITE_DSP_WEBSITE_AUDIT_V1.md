# NITE DSP WEBSITE AUDIT V1

Scope: `platform/website` (Next.js 16 App Router, React 19, Tailwind CSS 4, Paddle.js).
Audited: 2026-08-25.

## 1. Current State Inventory

### Pages that exist
| Route | Status | Notes |
|---|---|---|
| `/` | Live | Submit-led hero + SLO-heavy mid-page (mixed narrative) |
| `/products` | Live | Flagship Submit, SLO, KENN, Layer Alignment research grid |
| `/products/submit` | Live | Feature grid + honest "Operational Boundary" disclaimer |
| `/products/smart-sample-manager` | Live | SLO product page |
| `/pricing` | Live | Free closed beta + planned £2.99 perpetual licence |
| `/learn` + 6 SLO guides | Live | Getting started, installation, find-similar, Ableton, FAQ, troubleshooting |
| `/technology` | Live | Tech positioning |
| `/support`, `/account`, `/auth/verify` | Live | Support entry, account, magic-link verify |
| `/privacy`, `/terms`, `/eula`, `/refund-policy` | Live | Legal set present |

### Systems that exist
- **Motion system**: `components/motion/` — LightField, Magnetic, Reveal, TiltSurface, WorkflowFlow, StatusDot; documented in `docs/NITE_DSP_WEBSITE_MOTION_V1_*`.
- **Interactive demos**: `SubmitPrepDemo`, `KennMixDemo`, `AudioAnalysisDemo`, `DemoPipeline/DemoShell/Readout` — browser-local simulated walkthroughs.
- **Commerce plumbing**: `lib/checkout.ts` → backend `/commerce/checkout` → Paddle-hosted checkout; buy-intent persistence across sign-in redirect; webhook-authoritative entitlements (`docs/PADDLE_INTEGRATION_AUDIT.md`). `BuyCard.tsx` on pricing.
- **Copy safety**: `scripts/audit-copy.mjs`.
- **E2E**: Playwright configured. **SEO**: sitemap, robots, canonicals, OG image.

## 2. Strengths
1. **Honesty infrastructure is rare and excellent.** Submit's Operational Boundary disclaimer, pricing page's explicit "does not submit work for the user", and demos labelled "illustrative data" build real trust.
2. **Local-first privacy story is consistent** across hero, products, demos, and legal copy.
3. **Motion system is purposeful and accessibility-documented** — Linear/Raycast-grade interaction quality without decorative noise.
4. **Commerce architecture is correct**: server-resolved Paddle price IDs, no client-side price authority, webhook entitlements.
5. **Learn hub for SLO** is genuine content marketing incl. DAW-specific landing content (Ableton).
6. Clean typography tokens, premium dark aesthetic, accessible responsive nav.

## 3. Weaknesses
1. **Homepage has split-brain storytelling.** Hero sells Submit; mid-page sections sell SLO. A visitor cannot tell what NITE DSP *is*. The company line — *"NITE DSP creates intelligent tools that simplify complex creative workflows"* — appears nowhere.
2. **No dedicated Submit workflow visualisation.** Drop→Understand→Review→Prepare→Verify→Receipt is not told as a sequence; features are listed flat.
3. **KENN and Thursday have no owned surfaces.** KENN exists only as a "concept" demo inside `/products`; Thursday is absent entirely.
4. **Pricing page is conversion-thin**: no plan comparison, no FAQ, no objection handling; "View Licensing" CTA label is vague.
5. **Purchase journey dead-ends silently pre-launch**: checkout correctly 503s, but there is no beta-request/waitlist capture from Buy surfaces beyond "contact support".
6. **No cross-product comparison table** anywhere.
7. **Trust/privacy messaging scattered** across disclaimers rather than one credible trust surface.
8. **Naming fragmentation**: "SLO" vs route `/smart-sample-manager` vs "Sample Library Optimiser" — harms recall and SEO.

## 4. Commercial Blockers (ranked)
| # | Blocker | Impact |
|---|---|---|
| B1 | No company-level value proposition on homepage | Every paid click lands confused |
| B2 | Buy UI visible while checkout closed | Frustrated intent, zero capture |
| B3 | No beta-access funnel (apply/waitlist) | Growth engine missing during closed beta |
| B4 | No comparison / FAQ / objections layer | Purchase friction unaddressed |
| B5 | Product naming fragmentation | Weak brand memory, split SEO equity |
| B6 | No Thursday surface | Ecosystem story incomplete |

## 5. UX Opportunities
- Rebuild homepage company-first: proposition → product ecosystem band → one demo per product.
- Submit page: vertical six-step workflow using the existing `WorkflowFlow` pattern.
- Pricing: honest-state primary CTA — "Request beta access" now, flips to Buy via existing `startCheckout()` at launch.
- Consolidated trust surface explaining local processing plainly.
- Unify naming: display name **SLO**, full name "Sample Library Optimiser", keep old slug as redirect.

## 6. Recommended Priorities
1. **P0** Homepage restructure (company proposition first).
2. **P0** Beta-intent capture on all Buy surfaces.
3. **P1** Submit workflow storytelling; SLO/KENN pages aligned to safe positions.
4. **P1** Pricing upgrade: comparison + FAQ + clear CTA states.
5. **P2** Thursday ecosystem page; consolidated trust page; naming unification.

*Claims discipline:* all recommendations preserve honesty boundaries — no automatic submission claims, no guaranteed outcomes, no automatic-mixing claims, no chatbot framing for Thursday.

