# KENN C++ DSP Phase 0 Receipt

**Completed:** 2026-09-20
**Status:** complete for source restoration and bounded validation

## Outcome

`products/kenn` is now the active canonical KENN product tree for the current
checkout. The interrupted migration was completed from the clean canonical
source tree in `monorepo-collab/products/kenn` at commit `f4a90d2`.

The active backend, plugin, shared package, frontend, desktop, integration, and
tooling sources are present. Generated caches, local databases, training data,
and build output were not copied into the active tree.

Compatibility links now resolve inside the product boundary:

```text
products/kenn/source      -> apps/backend/src/kenn
products/kenn/vst3-plugin  -> plugins/kenn-vst3-au
```

The chat requirements indirection was also repaired to reference the canonical
backend requirements file.

## Validation evidence

| Check | Result |
|---|---|
| bounded Python audio-analysis benchmark (`--long-seconds 5 --workers 2`) | qualified; 5 s mean 171.693 ms, 2 s @96 kHz mean 151.903 ms, 2-worker mean 331.576 ms |
| focused Python tests (`test_audio_analysis.py`, `test_benchmark_audio_analysis.py`) | 11 passed in 1.36 s |
| active backend import smoke | `kenn.core.audio_analysis` imports successfully |
| active backend bytecode compilation | `compileall` passed |
| CMake configure and native test build | passed in `/tmp/kenn-phase0-build.YsvDAj` |
| C++ numerical parity | all checks passed |
| C++ concurrent snapshot stress | 5 sample rates; 0 NaN/Inf or torn reads |
| C++ realtime performance | all 64/128/256/512/1024 buffers passed; 0.041–0.073% realtime budget |

The C++ build emitted upstream JUCE/macOS deprecation and warning diagnostics,
but no build or test failures.

## Known boundaries

- The checked-in `apps/backend/.venv` is a stale interpreter link into the old
  layout. Validation used the system Python 3.13 environment with the canonical
  source root on `PYTHONPATH`; repairing/recreating the product venv is a
  separate environment task.
- A small number of archived docs, Docker recipes, and explicit legacy adapters
  still mention `Audio_Too/studio`. They are not active default imports. The
  active source links and benchmark path no longer depend on that location.
- The full historical backend suite was not used as the Phase 0 gate; the
  focused tests and native checks above are the bounded receipt for this pass.

## Handoff

Phase 0 is complete. The next phase is Phase 1 in
`CPP_DSP_MIGRATION_ROADMAP.md`: implement the JSON benchmark contract, profile
complete Mix Review and representative AutoMix projects, and select one
measured bottleneck for a native spectral vertical-slice POC.
