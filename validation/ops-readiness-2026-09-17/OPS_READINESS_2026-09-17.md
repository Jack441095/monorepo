# OPS READINESS — can this business sell software? (2026-09-17)

Method: code + configs + commands only. Money-path traced hop-by-hop per product
(website → maturity switch → backend → provider → webhook → rows → license →
delivery → in-product enforcement → refund). Full register: `OPS_GAPS.csv`
(15 gaps). No secrets printed. Nothing modified outside this dir.

## 1. Executive summary

**CAN-CHARGE table:**

| Product | Charge today? | Single blocker |
|---|---|---|
| Submit | NO — closest (~2 wks) | G-03 signing/notarisation + G-02 credential + G-06 key UI |
| SLO | NO | G-01 JUCE purchase (then G-09 licensing-server prod + pricing) |
| DiskSweep | NO | G-08/G-10: no artifact, no pricing surface, no enforcement |
| KENN | NO | G-08/G-10: no pricing, no enforcement, unsigned pkg |
| Paraphrase | PARTIAL (free works; no payment seam) | G-08: stub unlock, pay-what-you-like copy |
| Bundle | NO | All of the above + R-11 asset quarantine |

**Top 5 money-blockers:** G-01 JUCE purchase (blocks flagship) · G-02 live credential (blocks everything) · G-03 Submit signing (blocks first £1) · G-06 in-product enforcement (keys are souvenirs) · G-05 refund-revoke (every refund needs the founder).
**The one decision:** buy JUCE now or sequence Submit-first revenue to fund it — everything else is buildable in parallel.

**What's genuinely strong:** the backend commerce core is well-built (HMAC, idempotent webhooks proven by test, fail-closed catalog, 106 green); the website cannot show a dead Buy button (maturity switch + beta fallback); auth is passwordless magic-link with ecash-grade session handling; downloads are entitlement-gated with 15-min signed URLs; Client-Work is cleanly separated (zero code imports); telemetry posture is clean (Plausible disclosed, nothing in shippables).

## 2. Money-path traces (abridged; hops cited)

**Submit path:** `CtaButton BUY_LIVE` (pricing/page.tsx:125) → `CHECKOUT_LIVE` gate (commerce-config.ts:15-18, currently false → beta fallback) → `startCheckout` POST /commerce/checkout (checkout.ts:28) → 401→buy-intent→/account→auto-resume (account/page.tsx:248-253) → backend requires session, resolves tier→price IDs (commerce.py:490-505) → **503: paddle_checkout_enabled=false, IDs empty** ⛔ → (if configured) Paddle URL → webhook → Purchase+Entitlement+license email → account page shows key + `GET /downloads/latest` (entitlement-gated) → signed 15-min fetch → **app never asks for the key** (OpenEntitlement, Settings.swift:147-156) ⛔ → refund records-only, manual revoke (commerce.py:337-338, admin.py:167-182).
**SLO path:** no priced surface (beta/waitlist only) → LicenseManager complete but unwired (LicenseManager.h:5-18) → licensing server localhost-only → JUCE unpurchased ⛔.
**DiskSweep/KENN:** interest → waitlist (KENN) / nothing (DiskSweep) → no artifact signature, no enforcement ⛔.
**Paraphrase:** free rewrites work; unlock stub returns false; payment seam future.

## 3. Findings → see OPS_GAPS.csv (G-01..G-15 with RICE + DoD).

## 4. Plans

**FIRST-SALE (Submit, ~2 wks, £1 of real revenue):** G-02 sandbox credential → sandbox live-fire (R-07 matrix) → G-03 sign+notarise+parity → G-06 Submit key entry + validate-on-start → flip CHECKOUT_LIVE in sandbox → test purchase → prod credential + LEGAL_RELEASE gates → public £3. DoD: stranger's card → key → download → activated app → purchase row.
**REPEATABLE-SALES:** G-05 refund policy (auto-revoke or SLA manual) + wire refund email → G-12 diagnostics bundle → G-07 trial/beta policy → G-11 one deploy path → weekly reconciliation ritual (payouts vs Purchase rows vs refunds; 30 min).
**SCALE (100→10k seats):** MoR absorbs tax (Paddle/Polar) · inference stays on-device (£0 marginal) · support load is the cliff (diagnostics + guides first) · fraud/abuse (rate limits exist; review at 1k) · second product only after Submit repeats hands-free for a month.

## 5. Owner-decision register
1. JUCE purchase: now vs after Submit revenue? (Recommend: price it this week; sequence Submit first if >£2k.)
2. MoR: Paddle vs Polar (Recommend: Polar sandbox spike already staged; keep Paddle fallback; decide on live-fire numbers.)
3. Pricing: confirm £3 Submit; set SLO/KENN/DiskSweep prices or explicit free/beta.
4. Refunds: auto-revoke vs manual SLA (Recommend: manual 24h SLA to start; automate at 10 refunds/mo).
5. Support channel: inbox vs tracker (Recommend: inbox + diagnostics bundle until 50 tickets/mo).
6. Trial strategy: time-boxed trials vs beta waves vs none (Recommend: beta waves; trials need G-07 build).
7. Bundle: after individual repeat sales only (kill if WTP <£30).
8. Deploy pick: one path per env (Recommend: backend Railway-Dockerfile, website Railway-Nixpacks).

## 6. Cost ledger (marginal + fixed; invoices UNVERIFIED — confirm Railway/Render)
- Per seat: 5% + 50¢ MoR fee · £0 inference (on-device) · ~£0 email/storage at beta scale · license delivery £0 (rows + email).
- Fixed/mo: backend host + website host + DB (Neon EU) + Plausible ≈ small two-figure £ (verify invoices) · Apple Developer £99/yr (needed for G-03) · JUCE one-time (G-01).
- No 10x cliff: costs scale with transactions, not usage. Support time is the real cliff — hence G-12 first.

## Appendices
A. Commands: 3 parallel source-only audits + targeted greps; no builds, no live calls, no *.md trusted.
B. Files: ~40 code/config files across website/lib+app, backend/app, Submit/SLO/DS/KENN sources, infra configs.
C. Strengths to protect: fail-closed commerce, no-dead-Buy switch, entitlement-gated downloads, telemetry cleanliness, Client-Work separation, idempotent webhooks.
D. Explicit unknowns: live provider behavior (needs secrets), invoice amounts, Apple identity state beyond readiness JSON, real refund volume, KENN/SLO price points.
