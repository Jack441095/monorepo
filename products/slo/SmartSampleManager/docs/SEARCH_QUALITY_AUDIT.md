# SmartSampleManager — Search / Similarity Quality Audit

Phase 1, Sections 7-10. Covers metadata search, HNSW similarity search, and the UMAP visual map. Based on source-code reading (this app has no text-query "semantic search" — similarity is driven entirely by acoustic embeddings and metadata filters, not natural-language queries, so Phase 6's "dark punchy kick"-style prompt evaluation doesn't apply to the current feature set as built).

## What exists today

- **Metadata/taxonomy search**: filename, BPM, key, instrument type (existing DSP-feature classifier), Ableton category/subcategory/tags (`AbletonTaxonomy`), loop-vs-one-shot.
- **Acoustic similarity ("find similar")**: PANNs Cnn10 512D embeddings → HNSW nearest-neighbor search.
- **Visual similarity map**: UMAP 2D projection of the embedding space, rendered via `SampleCanvas`/`QuadTree`.
- **Duplicate detection**: content-hash grouping (separate from similarity search, see the data-stack audit).

## Embedding-based similarity — verified working correctly

Confirmed via a real, non-synthetic regression test (`TestFindSimilar`, `TestEmbeddingQuality`) using actual kick-drum and noise-texture WAV fixtures through the full production pipeline (dr_wav decode → engine's own resampler → ONNX inference, not a shortcut): `real_kick_b` correctly ranks as the most similar sample to `real_kick_a` (measured cosine similarity 0.989) over an unrelated sustained-noise texture (0.669-0.670) — a strong, unambiguous separation. The query sample is correctly excluded from its own results, and an unknown file path returns no results rather than crashing.

This is real evidence the core embedding-similarity mechanism works acoustically as intended, not just structurally.

## Real gap found and fixed this pass: prune/HNSW desync

Before this audit, `pruneMissingFiles()` never invalidated or rebuilt the HNSW index. Because hnswlib labels are positional indices into the `samples` vector at build time, and `std::vector::erase` shifts every later element down, a "find similar" query issued after any file removal could silently resolve to **the wrong sample** — not just fail to exclude the deleted one, but return acoustically unrelated results under a confident-looking ranking. This is the kind of bug that erodes trust in a paid product's headline feature without ever crashing or showing an error.

**Fixed**: `pruneMissingFiles()` now flags a forced full HNSW/UMAP rebuild and wakes the coordinator thread (`SampleManagerEngine.h`'s new `forcedUmapRecomputePending`, `SampleManagerEngine.cpp`). A new regression test (extended `TestPruneMissing`) confirms `findSimilarSamples()` never returns a just-pruned file and only ever returns currently-tracked samples after a prune on an already-bootstrapped library. See `docs/REALTIME_SAFETY_AUDIT.md`'s sibling data-stack findings and `docs/COMMERCIAL_RELEASE_BLOCKERS.md`.

**Residual limitation, not fixed**: there is a small window between the prune completing and the forced rebuild finishing (the rebuild runs asynchronously on the coordinator thread, typically well under a second) during which a `findSimilarSamples` call could still see the stale index. Given prune is a deliberate, infrequent user action, this is a low-probability window; a fully synchronous guard would require blocking the caller until the rebuild completes, which risks UI stalls proportional to library size — not a proportionate trade for this pass. Flagged as P2.

## UMAP visual map — practical scale ceiling

No hardcoded item-count limit exists in the code, but the *behavioral* ceiling is real: the 2D projection is **never persisted to disk** (no x/y columns in the SQLite cache schema), so a full `O(N)`-ish UMAP recompute (VP-tree build + 200 epochs) runs **once per app launch** regardless of how many samples are already cached — even if every embedding came from the SQLite cache and ONNX was never touched. For a library of a few thousand samples this is likely fast; for a 100k+ item library (a figure referenced elsewhere in the engine's own comments), a full recompute on every launch is a real, unavoidable startup cost as currently built. **Not fixed in this pass** — persisting x/y coordinates and skipping the full recompute when nothing changed is a legitimate scope-sized feature, not a quick fix. Flagged as P1 in `docs/COMMERCIAL_RELEASE_BLOCKERS.md`; directly relevant to "what library size does this product actually support," which matters for commercial claims.

Within a session, incremental placement (avoiding a full recompute after every scan batch) is well designed and does not need changes.

## Small-library edge case (observed, not previously documented)

Running the new prune regression test surfaced a real, pre-existing (not introduced by this pass) log line: `UMAP error: requested number of singular values cannot be greater than the smaller matrix dimension` when a forced full recompute runs against a very small sample set (2 items, in the test's case). It does **not** crash — `findSimilarSamples()` still returns correct, safe results (empty or well-formed) — but the underlying UMAP projection silently fails for that recompute. This would affect any user with a tiny library (a handful of samples) opening the app, not just the prune path. Worth a user-facing check (e.g. skip/short-circuit UMAP below some minimum sample count, show existing samples in the canvas without a projection) before release, but is LOW severity given it fails gracefully. P2.

## Recommendation

Do not build a new AI research effort (semantic text search, LLM-based tagging) before launch, per the master prompt's own Phase 6 guidance — the existing embedding-based "find similar" is demonstrably good, and the real gaps here are engineering completeness issues (index staleness on delete, no persisted projection for fast cold starts), not search quality/relevance issues.
