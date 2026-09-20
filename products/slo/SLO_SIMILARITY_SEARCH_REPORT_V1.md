# SLO Similarity Search Report V1

**Purpose:** verify "Find Similar" is genuinely useful, with real test runs, not just code presence.

## Method

512D PANNs embeddings (ONNX inference), backed by `hnswlib` (approximate nearest-neighbor, header-only, v0.8.0 pinned) for fast search and `umappp` (v3.3.2) for incremental out-of-sample layout as new samples are added — a real, established similarity-search stack, not a placeholder.

## Test run (this pass, fresh rebuild + direct execution)

| Test | Result |
|---|---|
| `TestFindSimilar` | **PASS** |
| `TestFindSimilarWeighted` | **PASS** |
| `TestNearDuplicates` | **PASS** |
| `TestEmbeddingQuality` | **PASS** — real production pipeline output confirmed meaningful: *"two kicks cluster together and are clearly separated from sustained noise"* through the actual `dr_wav` decode -> engine resampler -> ONNX inference chain, not a synthetic/mocked embedding. |
| `TestTimbreRefinement` | **PASS** |
| `TestReferenceSearch` | **PASS** |

All 6 tests exit 0 when run directly (the `ssm_qual_intelligence` CMake target only builds them — running each binary is what actually proves pass/fail, consistent with this session's established practice).

## What this does and doesn't prove

**Proves**: the embedding space genuinely separates acoustically distinct content (kicks vs. noise) using the real decode-through-inference pipeline a user's scan would actually run, not a shortcut. Near-duplicate detection, weighted similarity, timbre refinement, and reference-search all have dedicated, passing regression coverage.

**Doesn't prove** (not something a unit test can establish, flagged honestly rather than assumed): whether "find kicks like this one" *feels* creatively useful to a producer in real use, whether result speed is subjectively fast enough during actual sound-hunting, or whether specific query types from the spec ("show me darker impacts," "show me shorter versions," "show me similar 808s") work well end-to-end — those queries combine similarity search with attribute/taxonomy filtering (Bright/Dark, duration, subtype), which are each independently tested but weren't exercised together as a single combined query in this pass. Worth a manual pass once there's a running UI to test against, not fabricated here.

## Verdict

Similarity search's backend is real, tested, and produces acoustically meaningful results on the actual production pipeline — not a demo. The open item is combined query UX (similarity + taxonomy/attribute filters together), which is a UI/integration question (Task 6), not a backend gap.
