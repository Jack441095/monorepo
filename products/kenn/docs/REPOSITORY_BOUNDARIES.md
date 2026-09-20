# Repository Boundaries

This checkout is the focused KENN collaboration and release repository.

It is intentionally smaller than the whole NITE DSP platform. Its purpose is
to give KENN UX/backend collaborators a clear, portable surface without
silently importing every platform product, experiment, corpus, or build
workspace.

## Standalone repository identity

- Local path: `/Volumes/Jack_Gandy_1TB_SSD/Nite-DSP/Nite-DSP-Operations/Shenrendao/KENN`
- GitHub: `Nite-DSP/colloidal-cyclone`
- Canonical branch: `develop`
- Remote: `git@github.com:Nite-DSP/colloidal-cyclone.git`

Use this repository for the standalone KENN backend, frontend, desktop app,
plugin, integrations, packages, SLO classification hook-up, tests, and
collaboration documentation.

## Canonical platform source

The whole-product source of truth is the platform monorepo:

- Local path: `/Volumes/Jack_Gandy_1TB_SSD/Nite-DSP/Nite-DSP-Operations/monorepo`
- GitHub: `Nite-DSP/monorepo`
- KENN path: `products/kenn`
- SLO path: `products/slo`
- Submit path: `products/nite-submit`

The monorepo owns cross-product integrations, shared services, SLO, NITE
Submit, KENN evaluation, and the canonical platform implementation. Its latest
KENN/SLO work is preserved on the `slo/eval-feat-ai-perf-v1` branch until the
test and review gates are complete; it is not currently the default branch.

## Product ownership

SLO, NITE Submit, and KENN evaluation remain separately owned products even
when their source is represented under `products/` in the platform monorepo.
This standalone repository contains the reviewed SLO-to-KENN integration
layer, not an unreviewed bulk copy of those products.

## Promotion rule

This repository is a deliberate collaboration/release surface, not a second
source of truth. Promote changes between repositories by an explicit PR that
names the source commit, scope, tests, and any intentional divergence. Never
copy the entire monorepo into this checkout or reverse-sync it wholesale.

See `docs/PROMOTION_WORKFLOW.md` for the handoff procedure.

## Branch rule

`develop` is the default and collaboration branch for this repository. Keep
`main` as historical context unless a deliberate release process replaces it.
