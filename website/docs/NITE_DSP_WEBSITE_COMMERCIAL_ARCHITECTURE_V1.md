# NITE DSP COMMERCIAL WEBSITE ARCHITECTURE V1

Companion to `NITE_DSP_WEBSITE_AUDIT_V1.md`. Defines information architecture, page designs and component requirements. All copy below is approved-safe language.

---

## 1. Information Architecture

```
/                        Homepage (company-first)
/products                Ecosystem overview (all four products, status-true)
/products/submit         Submit product page        [LIVE — enhance]
/products/slo            SLO product page           (redirect from /smart-sample-manager)
/products/kenn           KENN product page          [NEW]
/thursday                Thursday ecosystem page    [NEW]
/pricing                 Pricing + comparison + FAQ [ENHANCE]
/beta                    Beta access request        [NEW]
/download                Post-purchase download hub [NEW]
/trust                   Trust & privacy            [NEW]
/learn, /support, /account, legal routes             [KEEP]
```

## 2. Homepage Design

**Goal:** communicate *"NITE DSP creates intelligent tools that simplify complex creative workflows."*

| Section | Content | Components |
|---|---|---|
| Hero | Company proposition H1; sub: "From document preparation to mix understanding — local-first software for creative professionals."; CTAs: Explore products / View pricing; platform strip "macOS · Local processing · Apple Silicon" | `LightField`, `Magnetic` |
| Product ecosystem | Four cards: Submit (Beta), SLO (Private Beta), KENN (In development), Thursday (Internal) — status chips honest, each links to owned page | `StatusDot`, `TiltSurface` |
| Interactive demonstrations | One demo per flagship: `SubmitPrepDemo`, SLO similarity demo, `KennMixDemo`; caption: "Simulated walkthroughs with illustrative data — runs entirely in your browser" | existing demo shell |
| Trust & privacy | Three statements only: files stay local; no account needed for core workflows; claims match shipping reality. Link to `/trust` | static |
| Design philosophy | 4 principles: clarity over cleverness · privacy by architecture · purposeful motion · professional workflow fit | static |
| Company vision | Short paragraph on building a coordinated intelligence layer across tools (Thursday teaser) | static |
| Support/resources | Learn guides, Support, refund policy links | static |
| Bottom CTA panel | "Find the sound. Prepare the file. Understand the mix." → pricing | `cta-panel` |

## 3. Submit Product Page

Positioning H1: **"Prepare your work. Verify your files. Submit with confidence."**

Sections:
1. Hero + CTAs (Request beta access → `/beta`; View pricing).
2. **Workflow section** — six steps rendered as vertical `WorkflowFlow`:
   - **Drop** — add a PDF locally; nothing is uploaded.
   - **Understand** — Submit reads structure and metadata in memory.
   - **Review** — flagged fields and uncertainties shown for your approval.
   - **Prepare** — confirm corrections before anything is written.
   - **Verify** — naming and format checks against your chosen pattern.
   - **Receipt** — a safely named copy is saved; your original is untouched.
3. Feature grid (existing FEATURES, retained).
4. Live demo (`SubmitPrepDemo`) with simulation disclaimer.
5. **Operational Boundary** disclaimer (retain verbatim spirit): does not submit work; cannot guarantee department-specific rules; always run a final manual check.
6. FAQ teaser linking to pricing FAQ.

## 4. SLO Product Page

Positioning H1: **"Find the right sound."**

Sections: hero → **Sample discovery** (local indexing, feature extraction from audio signal) → **Similarity search** ("query all acoustically matching files in your local database") → **Audition workflow** (browser/map/split views, side-by-side compare) → **DAW handoff** (drag into Ableton Live and other DAW timelines) → capabilities grid (reuse homepage CAPABILITIES incl. "100% Offline Inference") → status band: private beta, gated while licensing/distribution evidence completes → link to Learn hub.

## 5. KENN Product Page

Positioning H1: **"Understand your mix."**

Sections: hero → **Analysis** (measures spectral balance, transients, tonal characteristics) → **Diagnosis** (explains what it observes and why it may matter) → **Recommendations** (suggested areas to address — you make the changes) → `KennMixDemo` labelled concept/simulated → status: in development.

Forbidden framing: never "AI automatically mixes your music", never autonomous-mix guarantees. KENN explains; the engineer decides.

## 6. Thursday Page

Positioning H1: **"The NITE DSP intelligence layer."**

Sections: what Thursday is (coordination of workflows and specialised agents across NITE DSP products) → **Orchestration** (routes work between tools) → **Workflows** (repeatable multi-step pipelines) → **Verification** (outputs checked before handoff) → status: internal infrastructure, powers future product coordination.

Explicit anti-positioning line: "Thursday is not a chatbot. It is infrastructure."

## 7. Component Requirements

| Component | Purpose | Source |
|---|---|---|
| `ProductEcosystemCard` | Status-true ecosystem card w/ CTA | New (composes StatusDot, TiltSurface) |
| `WorkflowFlow` (vertical variant) | Six-step Submit journey | Extend existing |
| `ComparisonTable` | Pricing/product matrix | New |
| `FaqAccordion` | Accessible disclosure list | New (native `<details>` acceptable) |
| `BetaRequestForm` | Intent capture pre-checkout | New |
| `CtaButton` state machine | states: buy-live / beta-request / notify-me | Wrap `startCheckout()` + `setBuyIntent()` |
| Existing demos | Reused as-is with disclaimers | Keep |

## 8. Copy-Safe Language Register
- Allowed: prepare, verify, review, explain, analyse, recommend, coordinate, local-first.
- Prohibited: automatic submission · guaranteed academic success · replaces university systems · AI mixes your music automatically · chatbot (for Thursday) · any unverified security certification claims.
