# SmartSampleManager — ONNX Failure Handling

Phase 2, Sections 18-20. Addresses `docs/COMMERCIAL_RELEASE_BLOCKERS.md` P1 #5 (missing/corrupt
model degrades to filename-hash pseudo-embeddings) and P1 #6 (mid-batch ONNX exception
permanently caches a zero-embedding with no retry).

## What was there before

Two distinct problems in `SampleManagerEngine::runInferenceBatch()`:

1. **No ONNX session at all** (model missing/failed to load): every file got a fake
   "embedding" derived from `std::hash` of its filename — a plausible-looking 512D vector that
   is acoustically meaningless. "Find similar" and duplicate-adjacent features would produce
   confident-looking but fake results with no indication anything was wrong.
2. **A batched `Ort::Session::Run()` exception**: every file in that batch got a 512-float
   all-zero vector, which then got written to the SQLite cache via `upsertCacheEntries()`
   (the `embedding.size()==512` guard let all-zero vectors through — zero is a valid size).
   Next launch, `tryLoadFromCache()` would hit on that row and treat the zero vector as a
   legitimate cached embedding forever, since nothing distinguished "real" from "poisoned."

Both are exactly the "fake intelligence" and "no automatic retry" problems the master prompt's
Section 18-19 call out.

## New model (`Source/SampleManagerEngine.h`)

```cpp
enum class EmbeddingStatus { NotAnalysed, Valid, FailedRetryable, FailedPermanent };
```

`SampleItem` now carries `embeddingStatus` and `embeddingFailureCount`. `embedding` is only ever
meaningful when `embeddingStatus == Valid` — nothing downstream should read it otherwise (and
after this change, nothing does: failed items get `embedding.clear()`, not a fake vector).

## Behavior changes (`Source/SampleManagerEngine.cpp`, `runInferenceBatch`)

- **Missing/failed model** (`session == nullptr`): every needing-inference item is marked
  `FailedRetryable` (or `FailedPermanent` past the retry threshold) with `embedding` cleared.
  No pseudo-embedding is ever generated. `SampleManagerEngine::isEmbeddingModelAvailable()` is a
  new public accessor (`session != nullptr`) so the editor can surface this state to the user —
  the actual UI wiring for a persistent "similarity search unavailable" banner is deferred to the
  async-startup/state-machine work (Section 15-17 of the master prompt), since that's the natural
  place a degraded-mode indicator belongs; this pass only removes the fake-data generation and
  exposes the accessor.
- **Mid-batch `Ort::Session::Run()` exception**: since a batched failure doesn't identify which
  file caused it, every file in that batch is marked `FailedRetryable` (or `FailedPermanent`),
  `embedding` cleared — no zero-vector is ever produced or cached.
- **Retry escalation**: `embeddingFailureCount` increments on each failure; at
  `kMaxEmbeddingFailuresBeforePermanent` (3), status becomes `FailedPermanent` — stops retrying a
  file that's genuinely broken (corrupt audio, unsupported format) on every future scan, while
  still surfacing that it failed rather than silently dropping it.

## Cache behavior (`upsertCacheEntries`, `tryLoadFromCache`)

- **`FailedRetryable` rows are never written to the cache.** No row (or the previous good row, if
  any) is left in place, so the next scan's `tryLoadFromCache()` naturally misses and the file is
  reprocessed — retry with zero extra bookkeeping. **Scoping note**: because retryable failures
  aren't persisted, `embeddingFailureCount` resets to 0 across app relaunches — the 3-strike
  escalation to `FailedPermanent` happens within a session's repeated scan attempts on the same
  file, not cumulatively across every launch ever. A more invasive cross-session counter (reading
  prior failure count on a cache miss) was considered and deferred — it would require the normal
  decode-and-retry path in `prepareFile()` to consult the cache even on a miss, a larger change
  than this pass's scope justified without a build agent free to validate a riskier refactor.
- **`FailedPermanent` rows are written** (`embedding_status` + `embedding_failure_count`
  columns, `embedding` bound `NULL`, never a placeholder vector) so a genuinely broken file stops
  being retried on every future launch, not just within one session.
- **`Valid` rows are written as before**, plus the new status/failure-count columns (status=1,
  count=0).
- **Cache read logic**: `FailedRetryable` status (or any well-formed-but-not-Valid,
  not-FailedPermanent status) is treated as a cache **miss** — forces reprocessing.
  `FailedPermanent` is a cache **hit** with `embedding` left empty — stops reprocessing.
  `NULL` status (pre-migration cache rows) is treated as legacy-Valid, gated on the embedding
  blob actually being present and the right size, for backward compatibility with caches written
  before this column existed.

## Schema (additive migration, `openCacheDb()`)

```sql
ALTER TABLE sample_cache ADD COLUMN embedding_status INTEGER;
ALTER TABLE sample_cache ADD COLUMN embedding_failure_count INTEGER;
```

## What was NOT changed this pass

- **UI surfacing of "similarity search unavailable."** `isEmbeddingModelAvailable()` exists and
  is correct, but no editor code calls it yet — deferred to the async-startup/engine-state-machine
  work (Milestone C's next item), which is the natural place a persistent degraded-mode indicator
  belongs rather than bolting a one-off warning onto the current synchronous-init editor.
- **Cross-session failure-count accumulation** — see the scoping note above.
- **A "retry now" user action** — not requested by the master prompt's P1 list; the automatic
  next-scan retry already covers the common case (user reopens the app or manually rescans).

## Verified this pass

Rebuilt `SmartSampleManager_Standalone` plus all 8 engine-linked regression test targets
(`TestSampleEngine`, `TestPruneMissing`, `TestFindSimilar`, `TestEmbeddingQuality`,
`TestDuplicateDetection`, `TestTaxonomy`, `TestXmpWriter`, `TestPathTraversal`) — all compiled
and linked cleanly, **all 8 ran and passed with exit code 0, zero new failures** compared to the
Phase 1 baseline in `docs/TEST_COVERAGE_AUDIT.md`.

## Not yet done (Milestone D follow-up)

Dedicated tests for the failure paths themselves (missing model, corrupt model, batched-inference
exception, retry escalation to `FailedPermanent`, cache-miss-on-retryable) were not added this
pass — the existing 8 tests confirm no regression to the success path, but don't directly exercise
the new failure states. Flagged for Milestone D alongside the other new-test additions in
`docs/COMMERCIAL_RELEASE_BLOCKERS.md`.
