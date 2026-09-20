# NITE DSP Repository Map

This monorepo is the canonical whole-product NITE DSP platform checkout. It
owns cross-product integrations and the authoritative source for KENN, SLO,
NITE Submit, evaluation, shared services, and platform technology.

## Product locations

- `products/kenn` — canonical KENN product (active apps/packages plus legacy runtime)
- `products/slo` — Smart Sample Manager / SLO product
- `products/nite-submit` — NITE Submit product
- `products/kenn-evaluation` — KENN evaluation and benchmark harness
- `audio-technology/` — shared audio engines and plugin technology
- `backend/`, `website/`, `shared/` — platform services and web surfaces

## Focused KENN collaboration repository

The standalone KENN collaboration/release checkout is:

`/Volumes/Jack_Gandy_1TB_SSD/Nite-DSP/Nite-DSP-Operations/Shenrendao/KENN`

GitHub: `Nite-DSP/colloidal-cyclone`

Its `develop` branch is a focused, portable UX/backend surface. It is not a
mirror of this monorepo and is not authoritative for cross-product platform
work. Selected changes can be promoted there through an explicit PR; the PR
must identify the source commit, tests, and any intentional divergence.

See `PROMOTION_WORKFLOW.md` for the exact handoff rules.

## Canonical KENN layout

The active KENN source is under `products/kenn/apps`, `products/kenn/packages`,
`products/kenn/plugins`, `products/kenn/integrations`, and `products/kenn/tooling`.
The historical monorepo runtime and its tests are retained under
`products/kenn/runtime/legacy/` for comparison and migration. There is no
second active `standalone/` source tree in the canonical repository.

## Exclusions

Builds, dependency downloads, model weights, runtime state, secrets, local
agent metadata, and unreviewed corpora remain local. Source manifests and
reproducible build instructions should be committed instead.
