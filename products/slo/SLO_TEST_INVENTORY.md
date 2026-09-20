# SLO Test Inventory

## Current audit build finding

The shared `ssm_engine_core_test` / `ssm_engine_core_prod` object-library optimization is currently not link-clean for helper-based engine tests. A clean arm64 Release build reports 13,044 duplicate JUCE symbols in the helper targets, and the fast qualification group exits 2. Direct targets (`TestTaxonomy`, `TestXmpWriter`, `TestCachedReclassification`, and `TestAcousticClassifierParity`) are separate and passed when built.

## Discovery result

- CTest registration: **0 tests** (`ctest --test-dir build-test -N`).
- CMake test/benchmark executables: **31** (26 `ssm_add_engine_test` calls plus
  5 explicit/additional executables).
- Shipped build formats: **3** — AU, VST3, Standalone.
- Direct shell regression runner: `build-test/_run_regression_suite.sh`;
  it selects 8 binaries and deliberately skips `TestLicensing`.
- Python/shell benchmark/release/security tooling is present under
  `SmartSampleManager/tools`, `SmartSampleManager/scripts`, and the model-export
  tree. These are inventoried as direct entry points, not as CTest tests.

## CMake entry points

| Entry point | Type | Safe policy | Purpose |
|---|---|---|---|
| `TestTaxonomy` | pure C++ | Safe | Taxonomy and loop/one-shot logic |
| `TestXmpWriter` | C++/JUCE | Safe synthetic fixtures | XMP sidecar round-trip and non-source mutation |
| `TestLicensing` | C++/network-capable | **Not run** | Requires licensing server and live/dev key; may create license state |
| `TestSampleEngine` | engine integration | Safe only with isolated cache | Scan, metadata and core engine |
| `ClassificationBenchmark` | benchmark | Safe only with isolated cwd/cache/output | Full scan/classification results and perf |
| `TestPathTraversal` | engine security regression | Safe isolated fixtures | Metadata/path traversal defense |
| `TestDuplicateDetection` | engine integration | Safe isolated fixtures | Content-hash duplicate grouping |
| `TestPruneMissing` | engine integration | Safe isolated fixtures | Missing-file pruning and index consistency |
| `TestResilience` | engine recovery | Safe only with isolated cache | Missing model and corrupt DB handling |
| `TestCacheIntegrity` | engine/database | Safe only with isolated cache | Quarantine and user-state preservation |
| `TestMalformedAudio` | engine robustness | Safe isolated fixtures | Corrupt/truncated/zero-byte WAV handling |
| `TestMultiInstance` | concurrency | Safe only with isolated shared fixture DB | Concurrent engine/cache access |
| `TestSortLibraryAsync` | file-operation regression | Safe only with synthetic temp files | Move/cancel/re-entrancy/lifetime |
| `TestEmbeddingQuality` | model integration | Safe isolated cache | PANNs/ONNX embedding quality |
| `TestFindSimilar` | model/search integration | Safe isolated cache | HNSW similarity ranking |
| `BenchmarkScan` | performance harness | Safe only with isolated cache | Scan, rescan, search latency, RSS |
| `TestFavorites` | engine state | Safe isolated cache | Favorites persistence |
| `TestPrecisionBrowserSorting` | UI logic | Safe isolated cache | Browser sorting path |
| `TestHistory` | engine state | Safe isolated cache | Preview history |
| `TestAudioFeatures` | feature extraction | Safe synthetic fixtures | Audio feature values |
| `TestFindSimilarWeighted` | search integration | Safe isolated cache | Weighted similarity |
| `TestTimbreRefinement` | search integration | Safe isolated cache | Timbre/refined similarity |
| `TestReferenceSearch` | model/search integration | Safe isolated cache | Reference-file lookup |
| `TestNearDuplicates` | search integration | Safe isolated cache | Near duplicate detection |
| `TestAutoTagging` | classifier/engine integration | Safe isolated cache | Predicted tags |
| `TestMapClusters` | UMAP/search integration | Safe isolated cache | Map clusters |
| `TestCacheVersionEnforcement` | database regression | Safe isolated cache | Model-version invalidation |
| `TestPersistedCacheHydration` | database/search integration | Safe isolated cache | Reload persisted data |
| `TestSmartCollections` | engine/UI state | Safe isolated cache | Smart collection behavior |
| `TestSafetyRegression` | production-cache guard | Safe | Proves production path is rejected by test consumers |
| `TestAcousticClassifierParity` | classifier parity | Safe | C++ head parity against frozen references |
| `TestCachedReclassification` | cache migration | Safe isolated cache | Legacy cache reclassification |

## Protected/evidence-controlled entry points

Anything whose source, manifest or report is labelled holdout, qualification,
frozen, final, one-shot, AL-001 or AL-002 is not automatically safe. Existing
receipts may be cited, but the audit does not rerun protected truth. AL-001 is a
hard diagnostic only; AL-002 remains **WAITING FOR BLIND REVIEW** unless a formal
ingestion receipt proves otherwise.

## Matrix accounting rule

The final result report counts discovered CMake executables, safe-to-run
executables, pass/fail/blocked/stale outcomes, and protected-not-run separately.
No CTest denominator is substituted for the direct-binary inventory.
