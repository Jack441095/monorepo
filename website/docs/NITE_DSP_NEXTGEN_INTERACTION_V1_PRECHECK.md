# NITE DSP — NEXT-GEN INTERACTION V1 / WEBSITE MOTION V1 — PRECHECK

Date: 2026-08-24
Programme: Website interaction & motion layer (frontend only)
Scope guard: WEBSITE FRONTEND ONLY — no backend, SLO source, Submit source,
KENN source, database, licensing, Paddle, Railway, DNS or infrastructure
files were touched.

## Repository state at start

| Item | Value |
| --- | --- |
| Repo | `NITE_DSP/platform` (website lives at `platform/website`) |
| Remote | `https://github.com/Jack441095/NITE_DSP.git` |
| Starting branch | `design/website-v2-premium` |
| Starting HEAD | `cc4758555ce324bbb10a0d7e13b8c79b818d3853` |
| Dirty state | Clean tree (only untracked `.DS_Store` / `__pycache__` outside website) |
| Worktrees | Single worktree at `platform/` |
| Upstream | `origin/design/website-v2-premium` in sync with HEAD |

The starting SHA matches the recorded Website V2.1 owner-review ending SHA
exactly — the approved V2.1 design source was confirmed current before any
mutation.

## Environment

| Tool | Version |
| --- | --- |
| Node | v26.7.0 (note: x86-64 build under Rosetta 2 — pre-existing environment condition, flagged not fixed) |
| npm | 11.19.0 |
| Next.js | 16.3.0 (Turbopack, App Router) |
| React | 19.2.8 |
| Tailwind CSS | v4 (PostCSS plugin) |
| TypeScript | 5.x |
| Playwright | 1.62.x (chromium project, production webServer on :3100) |

## Baseline gates (before any change)

| Gate | Result |
| --- | --- |
| `npm ci` | PASS (npm install-scripts warnings only, pre-existing) |
| `npm run lint` (eslint) | PASS — 0 problems |
| `npx tsc --noEmit` | PASS |
| `npm run build` (production) | PASS — 26 static routes |
| `npx playwright test` | PASS — 29/29 (18 route smokes + 6 behaviour + 5 checkout) |

## Baseline bundle (measured from `.next/static`)

| Asset | Baseline bytes |
| --- | --- |
| JS (all static chunks) | 621,523 |
| CSS (all static chunks) | 34,931 |

## Audit findings before implementation

1. **No existing motion/pointer system.** No `mousemove`/`pointermove`
   listeners, no rAF loops, no magnetic code anywhere in the website. The
   only animation present: Tailwind `animate-pulse/ping/bounce` utilities in
   the demo, CSS hover transitions, and a global `prefers-reduced-motion`
   kill-switch. Nothing to build on — a new (small) system was required.
2. **Pre-existing Tailwind v4 token bug (fixed in this programme).** The
   stylesheet only mapped `--color-background/foreground` into `@theme`, so
   utilities like `bg-brand-blue`, `text-muted-dim`, `border-brand-violet`,
   `text-brand-red-bright` generated **no CSS at all**. Several surfaces
   silently missed their intended colour (demo transient text, homepage
   violet rule, demo panel backgrounds). Fixed by mapping all brand/semantic
   tokens into `@theme inline` — additive, restores approved design intent.
3. Design tokens for motion existed partially (`--motion-fast/standard/slow`,
   `--motion-easing`); extended rather than replaced.
4. Existing Playwright suite is production-build based (`webServer` builds
   then serves on 3100) — receipts below reflect production output.
5. Next.js 16.3 agent notice honoured: `usePathname`/`use client` docs in
   `node_modules/next/dist/docs` verified before use; patterns mirror the
   existing client components.

## Isolation

Work branch: `design/website-nextgen-interaction-v1` created from
`design/website-v2-premium` @ `cc47585`. No history rewrites, no resets, no
force pushes, no foreign files touched.
