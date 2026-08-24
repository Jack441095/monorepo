# NITE DSP WEBSITE V2.2 — INTERACTIVE PRODUCT DEMONSTRATION LAYER V1 — REPORT

Date: 2026-08-24
Branch: `design/website-v22-interactive-demos` (from `design/website-nextgen-interaction-v1` @ `dfacfe1`)
Boundary: website frontend only. Backend, SLO/Submit/KENN sources, Paddle,
auth, database: untouched. Not merged, not deployed.

---

## 1. Summary

The website now lets visitors **experience the intelligence before
purchasing**. Every demonstration walks the same visible signal path —

    INPUT → ANALYSIS → INTELLIGENCE → RECOMMENDATION → ACTION

— inside a shared hardware frame that always carries an honest label
(`SIMULATION` / `CONCEPT DEMO`), a live phase readout, and a reset control.

What was created:

| Experience | Route | Label | The visitor learns |
| --- | --- | --- | --- |
| The NITE Signal Journey (DISCOVER → ANALYSE → UNDERSTAND → CREATE) | Homepage | n/a (narrative) | "They build precise creative tools — local-first." |
| SLO intelligence demo (upgraded) | Homepage + SLO page | SIMULATION | "I can find and understand my sounds." |
| Submit preparation demo | Products | SIMULATION | "I can prepare important files safely — and I stay in control." |
| KENN mix review demo | Products | CONCEPT DEMO | "I can improve my mixes with intelligent assistance." |

The 60-second success criterion is met by the homepage journey + SLO demo
(what analysis feels like) and the Products demos (what each product is for).

## 2. Architecture — the Signal Demonstration Framework

Reusable, product-agnostic components in `components/demo/`:

| Component | Role |
| --- | --- |
| `useSignalDemo.ts` | Timer-driven phase machine: `idle → scanning → analysis → result` + reset. Full timer cleanup; phase changes are content (they survive reduced motion); no per-frame React state. |
| `DemoShell.tsx` | Hardware chrome: title bar, honesty label chip (mandatory — a demo without `SIMULATION`/`CONCEPT DEMO` cannot be built with this framework), `aria-live` phase readout, reset button, footer disclosure slot, `role="region"` with accessible name. |
| `DemoPipeline.tsx` | The five-stage signal strip; active stage tracks the phase. Labels collapse to dots <640px (no mobile overflow); strip is `aria-hidden` — meaning is announced by DemoShell. |
| `Readout.tsx` | `ReadoutRow`/`ReadoutPanel` with tone glyphs (✓ ! · …) so meaning survives without colour. Confidence-language contract documented in-code. |

Product demos compose the framework: `AudioAnalysisDemo` (SLO, upgraded
in place), `SubmitPrepDemo`, `KennMixDemo`. Homepage journey:
`components/SignalJourney.tsx` — same scroll contract as the existing
WorkflowFlow (passive listeners, rAF-throttled, `--flow` CSS variable,
composited transforms, static full trace under reduced motion).

Interaction states per demo: **Idle → Scanning → Analysis → Result → Reset** —
all reachable by mouse, touch, and keyboard.

## 3. Product mapping

- **SLO** — cryptic filename (INPUT) → waveform scan with violet processing
  trail (ANALYSIS) → transient / frequency range / RMS / character readouts
  (INTELLIGENCE) → classification + three qualitative "acoustic match"
  chips (RECOMMENDATION). No fabricated similarity percentages — matches are
  qualitative, consistent with the demo's illustrative disclosure.
- **Submit** — document chips (INPUT) → scan sweep (ANALYSIS) → findings:
  document type, student/module info detected, filename "Review required"
  (INTELLIGENCE) → "Preparation ready" with flagged item (RECOMMENDATION).
  Messaging is explicit: *Submit prepares; it does not submit automatically.*
- **KENN** — a stereo bounce (INPUT) → dimension meters sweep
  (ANALYSIS) → LOW END "Review recommended", STEREO IMAGE "Healthy",
  DYNAMICS "Suggested" with reasoning (INTELLIGENCE/RECOMMENDATION).
  Messaging is explicit: *KENN assists engineers; it does not replace them.*
- **Thursday** — intentionally absent (internal layer; homepage must never
  name it — enforced by the existing smoke suite).

Claim-safety notes:
- Submit's products-page card was aligned to the owner's V2.2 definition
  ("Submission Preparation Intelligence" — local document intelligence and
  safe submission preparation), replacing the previous "Autonomous Version
  Management" copy. Status remains conservative: "In Development".
- KENN's card still reads "Audio Classification Engine" (established copy);
  the mix-review demo is framed strictly as a CONCEPT DEMO. If KENN's
  public positioning is now "AI audio engineering assistant", the card copy
  should be updated in a follow-up — flagged, not silently changed.
- SLO claims unchanged: private beta, local analysis, read-only beta
  qualification wording all preserved. Demo disclosure footer preserved
  verbatim.

## 4. Performance

- Dependencies added: **0**. No WebGL, no canvas.
- Bundle (raw `.next/static` bytes, production build):
  - JS: 660,707 → **652,749** (−7,958 — the framework *replaced* duplicated
    demo logic; net negative)
  - CSS: 45,829 → **52,817** (+6,988 — journey + demo styling)
- All routes remain fully static prerendered.
- Runtime: phase machines are timeout-driven (3 timers per run, cleaned up);
  meters/scan visuals animate via CSS transitions on transform/width set at
  phase boundaries — no per-frame React state; scroll journey is passive +
  rAF-throttled like the existing signal tracks.
- Mobile: pipeline labels collapse to dots <640px; demos verified at zero
  horizontal overflow on 390px (automated).

## 5. Accessibility

- Demos are `role="region"` with accessible names; phase readouts are
  `aria-live="polite"`; sample/document selectors use `aria-pressed`.
- Pipeline strip is decorative (`aria-hidden`); all meaning has text
  equivalents (phase readout + readout rows).
- Confidence language only: Detected / Suggested / Review required /
  Waiting. Glyphs (✓ ! · …) carry meaning without colour.
- Keyboard: every demo runs from focus + Enter (automated test).
- Reduced motion: phase progression is content and still completes; the
  journey trace renders full; decorative transitions collapse via the
  global reduced-motion layer (automated test).
- Focus-visible, skip link, tab order unchanged. WCAG 2.2 AA posture held.

## 6. Testing

New `tests/demo.spec.ts` (10 tests) — all passing; full suite
**45/45 PASS** (24 smoke + 5 checkout + 6 motion + 10 demo):

1. Homepage journey renders four stages
2. SLO demo resolves with acoustic matches + labels intact
3. SLO demo reset returns to idle
4. Submit simulation reaches "Preparation ready" with honest framing
5. Submit flags a second document differently
6. KENN concept demo produces explainable suggestions
7. Demos are keyboard operable
8. Reduced motion still reaches results
9. No horizontal overflow on mobile (/, /products)
10. No console/page errors on demo routes

Existing tests untouched and green (incl. the homepage rule that KENN and
Thursday are never named there).

## 7. Visual review

Committed captures: `docs/motion-review/home-v22-1440.jpg`,
`products-v22-{1440,768,390}.jpg`. Demos read as miniature NITE DSP
instruments — same hardware chrome, palette, and signal language as the
site; idle states are calm and composed (static-quality rule holds).

## 8. Future improvements

1. Update KENN card copy if "AI audio engineering assistant" is now the
   official positioning (flagged above).
2. Give Submit its own product page hosting the demo (currently lives on
   /products).
3. Audio-backed SLO demo (opt-in Web Audio synthesis of the illustrative
   waveforms) — still fully local, still disclosed.
4. Persist "last explored demo" via localStorage for returning visitors.
5. Consider wiring the reserved `.energy-seam` CSS into the demo section
   hand-offs now that more sections exist.

## 9. Verdict

**A — EXCEPTIONAL / READY FOR OWNER REVIEW** for this programme's scope:
the site now demonstrates the technology honestly, accessibly, and within
performance budget, with zero new dependencies and a net-negative JS delta.
