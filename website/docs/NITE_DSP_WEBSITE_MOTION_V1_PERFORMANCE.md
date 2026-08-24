# NITE DSP WEBSITE MOTION V1 — PERFORMANCE

Full receipt: `docs/NITE_DSP_NEXTGEN_INTERACTION_V1_PERFORMANCE.md`
(same programme). V2.1 motion-pass summary:

- DEPENDENCIES ADDED: **0** (Framer Motion / GSAP / Lenis / Three.js
  considered and rejected — documented in the full receipt).
- BUNDLE DELTA (raw, `.next/static`): JS 621,523 → 660,707 B
  (**+38.3 KB**, ≈ 12 KB compressed); CSS 34,931 → 45,829 B
  (**+10.6 KB**, ≈ 3 KB compressed). All 26 routes still static.
- RUNTIME PERFORMANCE: transform/opacity/CSS-variables only; one shared
  pointer listener + one rAF loop for the whole site; loop parks at zero
  subscribers and on `document.hidden`; light fields skip offscreen work;
  no layout properties mutated on pointer movement; no React state updates
  per frame. Target platform: Apple Silicon Mac — interactive effects are
  compositor-path by construction; formal frame-rate telemetry not captured
  (recorded as limitation; no 60fps claim made without evidence).
- HYDRATION WARNINGS: none observed (deterministic markup; gating is
  post-hydration; `suppressHydrationWarning` on `<html>` for the js-class
  bootstrap).
- CONSOLE WARNINGS: zero console/page errors on high-interaction routes
  (automated assertion).
- LONG TASKS: none observed in test runs; no long-task telemetry captured.
- CLEANUP: all listeners/RAFs/observers removed on unmount; route
  navigation accumulates nothing (error-free multi-route test run).
- MACHINE COPY: `docs/website_motion_v1_performance.json`.
