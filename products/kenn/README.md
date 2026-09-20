# KENN product boundary

This directory is the canonical, single-repository KENN product. The active
UX/backend/plugin implementation is organized by product responsibility; the
pre-existing monorepo runtime is retained under `runtime/legacy/` for audited
compatibility work while callers are migrated to the active backend.

## Canonical layout

- `apps/backend/` — active Python backend and SLO classification hook.
- `apps/frontend/` — active Vue/TypeScript UX.
- `apps/desktop/` and `apps/legacy-web/` — desktop and served-web surfaces.
- `packages/` — chat, mix-review, automix, and shared packages.
- `plugins/` and `integrations/` — VST3/AU and Ableton boundaries.
- `tooling/` — build, evaluation, and verification scripts.
- `docs/` — architecture, handoff, runbooks, and product documentation.
- `runtime/legacy/` — preserved historical runtime and tests; do not add new
  active product code here without recording a migration decision.

The active backend import root is `apps/backend/src/kenn`. Backend ownership
and migration rules are recorded in `BACKEND_OWNERSHIP.md`.

## Data boundary

Only reviewed, tracked source and documentation belong here. Keep credentials,
local databases, generated indexes, build output, model weights, agent
metadata, and unreviewed/licensed corpora local.

This cleanup is reviewed on `cleanup/kenn-final-organization`; `main` remains
unchanged until the CI and ownership review are complete. The former focused
repository remains preserved separately as a rollback/reference point.
