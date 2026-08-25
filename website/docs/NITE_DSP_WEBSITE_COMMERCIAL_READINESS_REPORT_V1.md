# NITE DSP WEBSITE COMMERCIAL READINESS REPORT V1

Final deliverable consolidating Phases 1–5. Companion documents:

1. `NITE_DSP_WEBSITE_AUDIT_V1.md` — audit of the current site
2. `NITE_DSP_WEBSITE_COMMERCIAL_ARCHITECTURE_V1.md` — IA and page designs
3. `NITE_DSP_CONVERSION_COMMERCIAL_UX_V1.md` — pricing, purchase flow, trust UX

---

## Executive Summary
The NITE DSP website has unusually strong foundations for a pre-launch commercial site: honest boundary disclaimers, a consistent local-first privacy story, an accessibility-documented motion system, and correct Paddle checkout architecture (server-resolved prices, webhook entitlements). Its single largest problem is narrative: the homepage cannot decide whether NITE DSP is a document tool or a sample browser, the company proposition is absent, KENN/Thursday have no owned surfaces, and Buy UIs exist without an intent-capture path while checkout is closed.

## Deliverables Summary
| # | Deliverable | Location |
|---|---|---|
| 1 | Website audit | `NITE_DSP_WEBSITE_AUDIT_V1.md` |
| 2 | UX recommendations | Audit §5 + Architecture §2–6 |
| 3 | New information architecture | Architecture §1 |
| 4 | Page designs (Home, Submit, SLO, KENN, Thursday) | Architecture §2–6 |
| 5 | Component requirements | Architecture §7 |
| 6 | Conversion improvements | Conversion doc §1–3, §7 |
| 7 | Implementation roadmap | Below |

## Implementation Roadmap

### Sprint 1 — Narrative & Intent (P0)
- Homepage restructure: company proposition hero ("NITE DSP creates intelligent tools that simplify complex creative workflows"), product ecosystem band, philosophy/vision/support sections.
- Add `/beta` request page; repoint all Buy CTAs to CTA state machine (`beta-request` today, `buy-live` at launch).
- Rename "View Licensing" CTAs to outcome labels.

### Sprint 2 — Product Pages (P1)
- Submit: six-step Drop→Understand→Review→Prepare→Verify→Receipt workflow section (extend `WorkflowFlow`).
- SLO: reposition to "Find the right sound." with discovery → similarity → audition → DAW handoff; add `/slo` route redirecting `/smart-sample-manager`.
- KENN: new page "Understand your mix." (analysis / diagnosis / recommendations), demo retained with simulation label.
- Unify naming to SLO everywhere in display copy.

### Sprint 3 — Commercial Layer (P1)
- Pricing upgrade: comparison table, FAQ accordion, honest-state cards.
- `/trust` page consolidating local-processing and boundary messaging.
- Support entry points in footer + buy-failure states.

### Sprint 4 — Ecosystem & Launch Readiness (P2)
- Thursday page ("intelligence layer", explicitly not a chatbot).
- `/download` hub wired to entitlement + signed/notarised builds.
- Flip CTA machine to `buy-live`; run claims audit via `scripts/audit-copy.mjs`; full Playwright E2E pass on purchase flow.

## Safety Compliance Statement
All designs enforce: no automatic-submission claims · no guaranteed academic outcomes · no "replaces university systems" · no automatic-mixing claims for KENN · no chatbot framing for Thursday · no privacy/security promises beyond actual local processing and existing legal documents. Website claims match shipping reality as audited on 2026-08-25.

## Ownership Boundaries (restated)
This programme covers website experience, storytelling, conversion flow, pricing presentation, purchase journey UX, demonstrations, and commercial UX only. Core product engineering, DSP algorithms, Submit intelligence logic, and licensing backend implementation remain out of scope; the website consumes the existing `/commerce/checkout` API and webhook entitlement model unchanged.
