# SmartSampleManager — UMAP Persistence

Phase 2, Sections 21-23. Addresses `docs/COMMERCIAL_RELEASE_BLOCKERS.md` P1 #3 (full UMAP
recompute on every app launch) and the small-library UMAP error documented in
`docs/SEARCH_QUALITY_AUDIT.md`.

## Schema (`Source/SampleManagerEngine.cpp`, `openCacheDb()`)

```sql
ALTER TABLE sample_cache ADD COLUMN umap_x REAL;   -- NULL until a projection has run for this row
ALTER TABLE sample_cache ADD COLUMN umap_y REAL;
CREATE TABLE IF NOT EXISTS cache_meta (key TEXT PRIMARY KEY, value TEXT);
```

`cache_meta` currently holds one key, `umap_layout_version`, compared on every `openCacheDb()`
call against `kUmapLayoutVersion` (a constant in `SampleManagerEngine.cpp`). A mismatch — meaning
the embedding model or the UMAP algorithm/parameters changed since the layout was computed —
wipes every `umap_x`/`umap_y` value in one `UPDATE ... SET umap_x = NULL, umap_y = NULL` and
records the new version, so a stale layout can never silently mix with a freshly-computed one.

## Invalidation triggers implemented

| Trigger | Mechanism |
|---|---|
| Embedding model or UMAP algorithm/params change | Bump `kUmapLayoutVersion`; `cache_meta` version-check wipes all positions on next launch |
| A sample's audio content changes (different mtime/size) | `tryLoadFromCache()` won't hit at all (its match check already requires exact mtime+size), so that sample re-embeds and gets `umapPositionFromCache = false` — forces it into the "not fully cached" path, so it participates in a real projection |
| Explicit rebuild (`clearCache()`) | Already deletes the whole cache file, `umap_x`/`umap_y` included |
| Corruption | Handled by the SQLite hardening pass (`docs/DATABASE_HARDENING.md`) — a quarantined DB gets a fresh schema, no stale positions to worry about |
| Prune (`pruneMissingFiles()`) | Does **not** invalidate the surviving samples' positions — their embeddings and content didn't change, only their index in the in-memory vector shifted (see `docs/COMMERCIAL_RELEASE_BLOCKERS.md`'s already-fixed HNSW/prune desync). The forced rebuild it triggers now uses this same skip-if-cached path, so a prune no longer forces a full UMAP recompute either — just the (cheap) HNSW index rebuild |

## Skip logic (`SampleManagerEngine::runUMAPInternal`)

Before running the expensive `umappp` computation, checks whether **every** currently-processed
sample already has `umapPositionFromCache == true` (set in `tryLoadFromCache()` when its
`umap_x`/`umap_y` columns are non-null). If so, `runFullUMAP()` is skipped entirely — only the
(fast, O(N log N)-ish) `rebuildHnswIndexFull()` runs, since the HNSW similarity index itself
isn't persisted and needs rebuilding regardless of whether the *visual* layout changed.

If even one processed sample lacks a cached position (a fresh scan, a partially-cached library,
or a version-bump wipe), the full projection runs for everyone, exactly as before — this pass
doesn't attempt partial/mixed recomputation, which would risk visually incoherent layouts (new
points placed relative to a UMAP run that never saw them).

New positions (from either a full run or the existing incremental placement path) are written
back via a new `persistUmapPositions(startIdx)` — a single batched `UPDATE` transaction keyed by
path — immediately after they're computed, so the *next* launch benefits.

## Small-library short-circuit (`runFullUMAP`)

Below `kMinSamplesForUmapProjection` (5) processed samples, `umappp::initialize()` is skipped
entirely and points are placed on a small deterministic circle instead (`SampleManagerEngine.cpp`,
`runFullUMAP()`). This directly fixes the documented `UMAP error: requested number of singular
values cannot be greater than the smaller matrix dimension` log line from
`docs/SEARCH_QUALITY_AUDIT.md`, which was reproducible at `nobs=2`. Note this only affects the
*visual* canvas position — `findSimilarSamples()`/duplicate detection use the embeddings and
HNSW index directly, never x/y, so search quality for tiny libraries is unaffected either way.

## Verified this pass

Rebuilt `SmartSampleManager_Standalone`, `TestSampleEngine`, `TestPruneMissing`,
`TestFindSimilar`, and `TestEmbeddingQuality` (Debug) — all compiled and linked cleanly, all 4
executed regression tests passed with **zero new failures**. Real log output from this session's
test run directly confirms both new behaviors firing correctly:

```text
TestEmbeddingQuality: [INFO] UMAP layout fully restored from cache -- skipping recompute.
TestPruneMissing:     [INFO] Library has fewer than 5 samples -- using a simple placement instead of a full UMAP projection.
TestFindSimilar:      [INFO] Library has fewer than 5 samples -- using a simple placement instead of a full UMAP projection.
```

(The `TestEmbeddingQuality` skip-recompute line fires because these test binaries share the same
on-disk cache DB across runs within a session — a real demonstration of cross-launch persistence,
not a synthetic check.)

## Not yet done (Milestone D follow-up)

A dedicated regression test asserting the skip-vs-recompute decision itself (e.g. two engine
instances against the same cache, second one measurably skipping `runFullUMAP`) was not written
this pass — the existing tests above incidentally exercised and confirmed the real behavior, but
a purpose-built test with an explicit assertion (not just a log-line eyeball check) belongs in
Milestone D alongside the other new-test additions.
