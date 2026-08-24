# NITE DSP WEBSITE MOTION V1 — PRECHECK

This programme was executed jointly with NITE_DSP_NEXTGEN_INTERACTION_V1
(one implementation, two requirement sets). Full precheck receipt:
`docs/NITE_DSP_NEXTGEN_INTERACTION_V1_PRECHECK.md`.

Summary:

- Repo `NITE_DSP/platform`, website at `platform/website`.
- Starting branch `design/website-v2-premium` @ `cc4758555ce324bbb10a0d7e13b8c79b818d3853`
  (verified equal to the recorded V2.1 owner-review SHA), clean tree,
  single worktree, remote `origin` = github.com/Jack441095/NITE_DSP.
- Environment: Node v26.7.0 (Rosetta x86-64 — pre-existing), npm 11.19.0,
  Next 16.3.0 (Turbopack), React 19.2.8, Tailwind v4, Playwright 1.62.x.
- Baseline gates all PASS: `npm ci`, lint, `tsc --noEmit`, production
  build (26 static routes), Playwright **29/29**.
- Audit: **no pre-existing motion system** (no pointer listeners, no rAF,
  no magnetic code) — nothing to build on, so the restrained system in
  DESIGN_SPEC was created. One pre-existing bug found and fixed: Tailwind
  v4 brand tokens were never mapped into `@theme`, so `bg-brand-blue`-class
  utilities generated no CSS (additive fix, restores approved intent).
- Work branch `design/website-nextgen-interaction-v1`; no resets, no force
  pushes, no foreign files touched; backend/SLO/Submit/KENN untouched.
