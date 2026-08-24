# NITE DSP WEBSITE MOTION V1 — BROWSER QA

Full receipt: `docs/NITE_DSP_NEXTGEN_INTERACTION_V1_BROWSER_QA.md`
(same programme). V2.1 motion-pass summary:

- Runner: Playwright 1.62.x chromium, production webServer (build + serve
  on :3100), fullyParallel.
- Suite: 24 smoke + 5 checkout (existing) + 6 motion (new) = **35 tests**.
- Result: **35/35 PASS** (baseline before programme: 29/29 PASS).
- New coverage: magnetic CTA click-while-engaged, demo scan + disclosure,
  reduced-motion content visibility + CTA, touch/mobile overflow (390px,
  hasTouch) on 4 routes, nav indicator alignment + aria-current, console
  hygiene on high routes. No tests bind to exact animation coordinates.
- Manual matrix: mouse / trackpad / keyboard / touch emulation /
  reduced-motion across Homepage, SLO, Products, Pricing, Support,
  Learn, Account — **PASS** everywhere (utility routes minimal by design).
- One flaky cluster during development was traced to a stale
  manually-started server reused against a swapped build (environment
  artifact); suite green on fresh webServer, repeated ×3.
- Screenshots: 1440/768/390 for Homepage, SLO, Products committed at
  `docs/motion-review/`; motion recordings (5 WebM, local only) at
  `docs/motion-review/video/`.
