# SLO / SmartSampleManager — Build-System Optimisation Measurements

Date: 2026-08-22 · Branch: `engineering/build-system-optimisation` · Host: Apple M3, 8 cores, 16 GB RAM, project volume = external 1 TB SSD.

## Baseline (measured on the pre-refactor graph)

All four existing build trees are `CMAKE_BUILD_TYPE=Release` + Unix Makefiles,
i.e. `juce::juce_recommended_lto_flags` (full `-flto`, compile+link) was active
on **every** target including all Test/Benchmark executables, and every JUCE
module was compiled once per consuming target.

| Measurement | Value |
|---|---|
| `SampleManagerEngine.cpp` (≈4.9 k lines) object copies in `build-test/` | **28** |
| Engine-core fan-out after touching the engine TU (`make -n`) | ~56 compiles + 29 full-LTO links |
| JUCE module `.o` files duplicated across test targets in `build-test/` | 464 |
| No-op incremental build of one test target | 0.6 s |
| Rebuild one test target (`TestFavorites`) incl. clearing tree staleness | **484 s** |
| Touch engine TU → rebuild ONE consumer (`TestFavorites`) | **828 s** (~14 min; only 86 s CPU ⇒ I/O/memory-bound LTO link) |
| Build-tree disk usage | `build-test/` 2.3 GB · `SmartSampleManager/build-test/` 1.4 GB · `build-r4c-production-lineage/` 1.5 GB · UX worktree tree 2.2 GB |
| FetchContent `_deps/` per tree | 883 MB (JUCE 376 MB src + 107 MB build tool, dr_libs 223 MB, Eigen 138 MB) |

## Root causes addressed

1. Five shared engine TUs copy-pasted into ~22 executable source lists.
2. Full `-flto` applied to never-shipped test binaries in Release.
3. Per-target duplication of JUCE module compilation for tests linking the
   same module set with identical definitions.
4. Four ad-hoc multi-GB build trees with no policy; FetchContent re-fetched
   per tree.

## Changes (this branch)

- `ssm_engine_core_prod` / `ssm_engine_core_test` OBJECT libraries: shared
  engine TUs compiled exactly **twice** per configuration instead of ~22×
  (prod variant preserves the no-`SSM_TEST_BINARY` semantics that
  `TestSafetyRegression` depends on). Plugin target untouched.
- Declarative helpers `ssm_add_engine_test()` /
  `ssm_add_engine_core_prod_consumer()` replace ~20 hand-restated target
  blocks; target names unchanged.
- LTO tiers: `SSM_ENABLE_LTO` (default ON — plugin behaviour unchanged) and
  `SSM_TEST_LTO` (default OFF — tests skip full LTO; RC parity via preset).
- Presets `ssm-dev` / `ssm-qualification` / `ssm-release-candidate` with a
  shared `_cache/fetchcontent` dependency cache and canonical out-of-tree
  root `_build/`.
- Selective qualification groups (`ssm_qual_fast_regression`,
  `ssm_qual_cache`, `ssm_qual_classification`, `ssm_qual_intelligence`,
  `ssm_qual_ui`, `ssm_qual_full`).
- `TestAcousticClassifierParity` resolves fixtures from
  `SMART_SAMPLE_MANAGER_SOURCE_DIR` first — out-of-tree trees now work
  end-to-end (previously an in-tree-only constraint).
- CI workflow switched to the same preset/graph; stale in-tree rationale
  replaced.

## Candidate results (qualification tier, Release)

See final report in the programme thread; this file is updated with the
numbers as gates complete.

### Seeding a new machine/tree's dependency cache

Copy only the `*-src` directories of a populated `_deps` into
`_cache/fetchcontent`. Copying `-subbuild`/`-build` directories does NOT work:
their `CMakeCache.txt` embed absolute paths and CMake aborts relocation
(observed). Subbuilds are regenerated and pinned tags verified locally.
