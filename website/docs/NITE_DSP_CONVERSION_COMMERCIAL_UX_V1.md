# NITE DSP CONVERSION & COMMERCIAL UX V1

Covers Phase 3 (conversion experience) and Phase 4 (commercial UX). Grounded in the existing Paddle integration (`lib/checkout.ts`, backend `/commerce/checkout`, webhook entitlements).

---

## 1. CTA Strategy

Single CTA state machine used everywhere (`CtaButton`):

| State | Condition | Label | Action |
|---|---|---|---|
| `buy-live` | checkout enabled | "Buy now — £3" | `startCheckout()`; if 401, persist via `setBuyIntent()` then sign-in redirect |
| `beta-request` | current closed beta | "Request beta access" | → `/beta` form |
| `notify-me` | product pre-beta (KENN, Thursday, SLO public) | "Notify me" | email capture |

Rules: exactly one primary CTA per viewport; secondary is always "View pricing" or "Read the docs"; CTA labels state what happens next (never "View Licensing").

## 2. Pricing Page Design
- **Hero**: "One price. Yours to keep." Retain £3 perpetual positioning and closed-beta truth.
- **Comparison table** (`ComparisonTable`): rows = Platform, Local processing, Account required, Price model, Status; columns = Submit / SLO / KENN.
- **Plan card**: Closed Beta (Free, invitation-only, current) vs Perpetual Licence (£3, planned). Explicit: no subscription for V1.
- **FAQ accordion**: Is it a subscription? (No.) Does Submit upload my documents? (No — local processing.) Will Submit submit my work? (No — you submit; we help you prepare.) What macOS version? (13+, Apple Silicon.) Refunds? (Link to `/refund-policy`.)
- **Boundary line retained verbatim** from current page.

## 3. Purchase Flow (target)
```
Buy now → startCheckout() [server resolves Paddle price ID]
        → Paddle hosted checkout
        → webhook entitlement on backend
        → account shows licence
        → /download serves signed, notarised build
```
Pre-launch variant:
```
Request beta access → /beta form → manual invitation flow (existing closed beta)
```
Failure UX: reuse existing error mapping (401 sign-in, 503 honest "Checkout isn't open yet" with beta fallback link).

## 4. Onboarding & Download Journey
- Post-purchase/invitation → `/download`: latest build, checksum note, EULA acknowledgement, link to `/learn/smart-sample-manager/getting-started` equivalent for Submit.
- First-run principles (documented for product team, not website scope): no account wall before value; sample file to try safely.

## 5. Trust Messaging & Privacy Explanation (`/trust`)
Plain-language page, three pillars:
1. **Local by default** — documents and audio processed on your machine; demos run in your browser.
2. **Honest boundaries** — every product states what it does not do (link each Operational Boundary).
3. **Straightforward commerce** — Paddle as merchant of record; perpetual licence; refund policy linked.
No security certification claims unless actually held.

## 6. Support Entry Points
- Persistent footer links (Support, Refund policy, EULA).
- Contextual: pricing FAQ links to Support; download page links to troubleshooting guides.
- Buy-failure errors include Support link.

## 7. Measurement Plan (recommendation)
Track: hero CTA click-through, demo engagement depth, `/beta` submissions, buy-intent set/consumed rate, checkout starts vs completions (Paddle side), pricing FAQ expansion events.
