# NITE DSP INTERACTION V1 / WEBSITE MOTION V1 — PERFORMANCE

## Architecture

- **One** `pointermove` listener and **one** `requestAnimationFrame` loop
  for the entire site (`lib/motion.ts`). Components subscribe; the loop
  parks itself at zero subscribers and on `document.hidden`.
- Per-frame work is exclusively `transform` writes to element refs and CSS
  custom properties. **No React state updates on pointer movement.**
- Element-scoped listeners (magnetic/tilt/demo band) attach only to a
  handful of flagship surfaces and are removed on unmount.
- No CSS `filter: blur()` on animated elements — soft falloff is baked
  into radial gradients.
- IntersectionObserver disconnects after one-shot reveals; the workflow
  scroll listener is passive + rAF-throttled and cleans up on unmount.
- Grain animates a composited `transform` on a fixed pseudo-element
  (no background-position repaints).

## Dependencies

| Added | Count |
| --- | --- |
| Runtime deps | **0** (`@paddle/paddle-js`, `next`, `react`, `react-dom` unchanged) |
| Dev deps | **0** |

Considered and rejected: Framer Motion / GSAP (unnecessary — every effect
here is CSS-variable + rAF expressible), Lenis (scroll-jacking prohibited),
Three.js (prohibited).

## Bundle delta (production build, `.next/static` bytes)

| Asset | Before | After | Delta |
| --- | --- | --- | --- |
| JS | 621,523 | 660,707 | **+39,184 raw (≈ +38.3 KB, +6.3%)** |
| CSS | 34,931 | 45,829 | **+10,898 raw (≈ +10.6 KB, +31%)** |

Raw bytes, pre-compression; typical gzip/brotli transfer impact estimated
≈ 10–12 KB JS + 2–3 KB CSS. All routes remain fully static prerendered
(26 routes, ○ Static). Machine copy: `docs/nextgen_interaction_performance.json`.

## Runtime observations

- All 26 routes remain static; zero server-side work added.
- Hydration: deterministic — every motion component renders identical
  markup server/client; capability gating happens post-hydration via
  matchMedia. `suppressHydrationWarning` added to `<html>` for the
  pre-paint `js`-class script. **No hydration warnings observed** in test
  runs (console-error assertion in `tests/motion.spec.ts`).
- Console: automated check across `/`, `/products`, SLO page — zero
  console errors / page errors.
- Frame budget: pointer effects are transform/opacity-only (compositor
  path). Light fields skip work when off-screen. No long tasks introduced
  by the interaction layer in test runs; formal long-task telemetry was
  not captured (no profiling harness in repo) — recorded as a limitation.
- Environment caveat: this machine runs an x86-64 Node under Rosetta 2
  (Next.js warns at startup). Pre-existing condition, unaffected by this
  programme; production deploys run on Railway linux/x64.

## Power management

- Shared rAF loop parks when tab hidden or no active subscribers.
- Light fields no-op outside ±80px of viewport.
- Demo band listeners only active while pointer is over the waveform.

## Cleanup

Every listener/rAF/observer is removed on unmount (audited per component;
Playwright navigation across routes shows no accumulated errors).
