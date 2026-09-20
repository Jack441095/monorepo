# SLO Full Test Results V1

## Status

The test matrix distinguishes current audit execution from existing repository evidence. The canonical CMake inventory contains 31 test/benchmark executables plus four qualification groups and plugin targets. CTest is not the project runner (`ctest -N` reported zero tests); qualification is driven by CMake custom targets and direct executables.

## Current audit execution

| Surface | Result | Evidence |
|---|---|---|
| Clean Release configure | PASS | arm64, Release, install-after-build OFF, test LTO OFF |
| Clean Release full qualification build | FAIL | `TestAudioFeatures` and `TestAutoTagging` link with 13,044 duplicate JUCE symbols because JUCE modules are present in both the target and `ssm_engine_core_test` |
| Existing taxonomy test | PASS | `build-test/TestTaxonomy` |
| Existing XMP writer test | PASS | `build-test/TestXmpWriter` |
| Existing production cache guard | PASS | `build-test/TestSafetyRegression`; DB size/mtime unchanged |
| Existing classifier parity binary | BLOCKED | stale `build-test` did not contain the binary |
| Filename-invariance benchmark | BLOCKED | stale benchmark failed engine initialization; no result JSON produced |
| Licensing | NOT RUN | requires authorized server/key state |
| Ableton Live | NOT QUALIFIED | no authorized GUI/host validation evidence |
| Debug build | NOT RUN | release build and external host/distribution gates take precedence |

## Fresh clean-target results before aggregate failure

- `TestTaxonomy`: PASS.
- `TestCachedReclassification`: PASS; 1,000 isolated mock rows, 8,738.14 files/sec.
- `TestXmpWriter`: PASS.
- `TestAcousticClassifierParity`: PASS; max logit error 3.16e-06, max probability error 2.97e-07, all V4-H gating checks passed.
- `ClassificationBenchmark`: link did not produce a usable executable before the aggregate failure; filename-invariance remains blocked.
- Helper-based engine targets (`TestAudioFeatures`, `TestAutoTagging`, `TestPathTraversal`, `TestDuplicateDetection`, `TestPruneMissing`, `TestSafetyRegression`, and the fast group’s other helper targets): build/link failure due 13,044 duplicate JUCE symbols against the shared engine core.

The direct targets `TestTaxonomy`, `TestXmpWriter`, `TestCachedReclassification`, and `TestAcousticClassifierParity` do not use the failing helper linkage shape and built/ran successfully.

## Existing regression coverage

The wired suite covers taxonomy, XMP, path traversal, duplicate detection, prune-missing, resilience, cache integrity, malformed audio, multi-instance, async sort, embedding quality, find-similar, benchmark scan, favorites, history, smart collections, audio features, intelligence targets, cache version enforcement, persisted hydration, classifier parity, cached reclassification, precision sorting, and the production cache safety guard.

## Interpretation

The project has substantial native regression coverage, but coverage is not the same as qualification. Missing or blocked evidence includes a fresh complete matrix, host validation, clean-machine installation, long soak, RT timing instrumentation, production licensing, and blind classifier review.

## Follow-up qualification run — 2026-09-14

The existing arm64 `build/` native binaries were executed directly (CTest is
not wired for this project): **46 of 47 direct test binaries passed**. The one
non-pass was the end-to-end licensing activation binary, which requires an
authorized integration key; its self-contained URL-policy mode passed. This is
an environment/credential gate, not a bypass or a production-policy change.

The Python classification benchmark suite now reports **273 passed**, including
strict-blind label-import validation, low-end attribute redundancy auditing,
and research-manifest SHA-256 identity matching. The research OOD energy
experiment remains intentionally unclaimed until a cache covering the complete
paired manifest is available.

The suite subsequently reports **277 passed** after adding the read-only
research-input preflight and ground-truth manifest-builder tests. A 795-row
candidate manifest has been assembled from reviewed labels (731
known, 64 explicit rejection/OOD rows); its receipt preserves the five missing
frozen-head classes and thin-family limitations rather than silently collapsing
fine-grained labels.

A disposable SQLite cache was then generated from the verified PANNs archive.
The preflight matched **795/795** rows with no embedding or hash failures. A
real runner invocation loaded 731 known and 64 OOD rows, then stopped at the
metadata gate before fitting; no scorecard was emitted. This validates the
research plumbing while keeping the incomplete taxonomy evidence unclaimed.

The current full suite reports **312 passed**. It also covers the taxonomy-gap
queue-aware local review state, fail-closed owner-decision importer,
duplicate-safe manifest merger, and deterministic review-batch selector. Batch
01 contains 120 rows with representation from all 13 candidate option groups.

The supplemental queue has an independent 120-row batch 02 spanning 12 option
groups and 62 collections; it is also review-only until owner decisions are
entered.

An advisory CLAP pass over master batch 01 completed 120/120 files with zero
decode errors. Its option-filtered receipt contains 115 advisory candidates;
all rows remain owner-review-required and the receipt records uncalibrated,
read-only safety state.

The arm64 `TestAudioFeatures` target was rebuilt after the naming/tempo change
and passed. It now verifies one-shot `B Major` presentation as `B`, preserves
the full mode for loops, suppresses stale BPM suffixes for non-loop names, and
recovers a synthetic 120-BPM click loop without selecting its 60-BPM harmonic.

A 40-row production scan over copied real-corpus samples produced
`_artifacts/slo_tempo_real_corpus_audit_v1.json`: zero exact-120 values and
zero non-loop/nonzero-BPM leaks after the post-ML normalization pass.

The tempo detector was then upgraded to a multi-band onset envelope and the
native test was extended with layered 90 and 174 BPM bass-plus-subdivision
fixtures. `TestAudioFeatures` passes all 120/90/174 cases. A fresh 40-row
production rescan is recorded at
`_artifacts/slo_tempo_real_corpus_audit_v2.json`: zero exact-120 values and
zero non-loop/nonzero-BPM leaks. This is a detector/regression improvement,
not a claim that acoustic tempo is always identifiable; ambiguous
notated-versus-felt meters still require metadata or abstention.

The native benchmark now has a `tempo` mode that evaluates short and long
temporal views side by side. Production tempo analysis uses the same bounded
20-second long view and accepts acoustic BPM only when it agrees with the
5-second view within 2 BPM. Filename parsing also covers explicit loop-plus-key
tempo conventions such as `Loop_110_Fm` while rejecting bare loop indices. The
updated copied-corpus receipt is `_artifacts/slo_tempo_real_corpus_audit_v4.json`;
its 120 BPM value is backed by an explicit filename token rather than a
default.

The `tempo` evaluator's aggregate denominator is now restricted to files with
duration at least two seconds, an explicit loop path/name signal, and a
plausible filename BPM. Numeric BPMs on one-shots are retained as diagnostic
rows but cannot inflate or distort acoustic-tempo accuracy claims.
