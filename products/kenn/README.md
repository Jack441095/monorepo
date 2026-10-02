# KENN

`products/kenn` is the canonical KENN product boundary in this monorepo. The
active implementation is self-contained here; the former `Audio_Too` tree is a
preserved reference only and is not a runtime dependency.

Start with [KENN_PLAN.md](KENN_PLAN.md) for the architecture, current work sequence,
acceptance gates and verified progress. It is the sole KENN roadmap. Dated reports
are evidence for their recorded source state; runbooks are operational procedures.

## Canonical layout

- `apps/backend/src/kenn/` — active Python backend, analysis, retrieval, and
  SLO integration;
- `apps/frontend/` — active web UI;
- `apps/desktop/` — desktop companion sources;
- `packages/chat/`, `packages/mix-review/`, and `packages/automix/` — product
  boundaries and local contracts;
- `plugins/kenn-vst3-au/` — JUCE VST3/AU source;
- `packages/common/` — shared native headers and evidence schema;
- `tooling/` — benchmarks, evaluation, and verification;
- `runtime/legacy/` — preserved compatibility runtime; do not add new active
  code there without a migration decision;
- `docs/` — component contracts, research, evidence and operational runbooks.

The compatibility links `source/` and `vst3-plugin/` point into these active
paths so older local commands fail clearly or continue to resolve without
depending on `Audio_Too`.

## Data boundary

Only reviewed source and documentation belong in the canonical product tree.
Keep credentials, local databases, generated indexes, model weights, build
output, and unreviewed/licensed corpora out of the active source boundary.

See `BACKEND_OWNERSHIP.md` for the single active import root and reconciliation
rules.

## Native DSP status

The C++/nanobind path is available behind `KENN_DSP_NATIVE=1` and remains opt-in
pending rights-cleared and cross-platform release evidence. Earlier spectral-only
and later decoder/bulk-metrics measurements cover different implementations;
consult the exact workload and receipt before quoting a speedup. Historical AutoMix
kernels have been recovered as a
standalone archive for requalification, but are not yet wired into the active
worker. Evidence and next gates are tracked in
`docs/research/CPP_DSP_PHASE4_RELEASE_QUALIFICATION.md`.
