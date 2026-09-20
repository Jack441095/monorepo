# KENN backend ownership

The single Git repository is the canonical collaboration surface. This file
prevents new code from quietly landing in the preserved legacy tree.

## Active collaboration surface

| Concern | Current path | Status |
|---|---|---|
| KENN HTTP/backend app | `apps/backend/src/kenn/` | Active; scoped suite passes |
| SLO classification adapter | `apps/backend/src/kenn/core/slo_classification_adapter.py` | Active |
| SLO artifact intake/manifest | `apps/backend/src/kenn/core/slo_artifact_*.py` | Active |
| KENN frontend | `apps/frontend/` | Active |
| Desktop/plugin/Ableton surfaces | `apps/`, `plugins/`, `integrations/` | Active; validate per platform |

New UX, backend, SLO-hook, and collaboration work must target these active
paths on the cleanup branch (and, after review, `main`).

## Existing platform runtime

`runtime/legacy/kenn/` is the pre-existing monorepo runtime package. It remains
preserved for comparison and platform integration work, but it is not the
active UX backend. Do not add a parallel implementation there without
recording the reason and the intended merge path.

## Reconciliation rule

Reconcile overlapping modules by contract rather than by file timestamp. The
minimum set is:

- `server.py` and route registration;
- session memory and feedback persistence;
- retrieval/index paths;
- SLO classification and artifact contracts;
- plugin/Ableton handoff;
- package requirements and import roots.

The final state must have one documented active backend import path. Generated
indexes, model weights, private corpora, and runtime state remain local and
must not be used as merge inputs.

## Current validation

From `products/kenn/apps/backend`:

```bash
PYTHONPATH=src .venv/bin/pytest -q src/kenn/tests
```

Validated result: **1,256 passed, 12 skipped**. The skips are optional
MLX/model tests, explicitly gated when the local Apple Silicon model is
unavailable.
