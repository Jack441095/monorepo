# SLO Perf & Realtime Pass — Findings V1 (2026-09-16)

Scope: full-codebase sweep of the SmartSampleManager engine/plugin for correctness bugs and
realtime/performance issues, then implementation of the approved findings. "SLO" here is the
product (Sample Library Optimiser); no formal availability-SLO definitions exist in this repo.

## 1. FFT packed-spectrum misread — RETRACTED (false positive)

A source scan flagged `analyzeAudioProperties()` and `computeMelSpectrogram()` for reading
interleaved complex bins (`fftData[2k]` / `fftData[2k+1]`, k = 0..N/2) as if the FFT output were
packed. **Verified against the vendored JUCE 8 source that the SLO code is correct.**

- JUCE 8 `FFT::performRealOnlyForwardTransform(data)` defaults
  `onlyCalculateNonNegativeFrequencies = false`, i.e. it produces the *standard interleaved*
  layout `[Re0, Im0, Re1, Im1, ...]` for bins 0..N-1 (buffer sized `fftSize * 2`).
- AppleFFT (`fetchcontent/juce-src/modules/juce_dsp/frequency/juce_FFT.cpp`, `mirrorResult`,
  ~lines 483-495) explicitly converts vDSP's packed half-complex output back to standard bins;
  FFTW (r2c + mirror), Intel (Dfti RToCCS + mirror), and the Fallback engine all produce the same
  standard layout. Every JUCE engine variant therefore matches the read pattern.
- Reads at k = N/2 stay in-bounds (`fftSize * 2` buffer).

Consequences: **no DSP change, no `kFeatureAnalysisVersion` bump** (avoids forcing a full-library
re-analysis), no behavior change.

## 2. UMAP predicate/index desync (BUG-02) — FIXED

`runFullUMAP()` sized its fixed flat buffer with `hasUsableEmbedding()` but wrote coordinates back
with `!s.isProcessed`. A failed/retryable/permanent embedding attempt leaves `isProcessed == true`
with the embedding cleared (see `docs/ONNX_FAILURE_HANDLING.md`), so those samples were *skipped*
while sizing the buffer and then *counted again* when writing back — OOB read of `embedding2d` and
coordinates stamped onto the wrong sample.

Fix:
- New header-declared free function `collectUmapEligibleSamples(std::vector<SampleItem>&)`
  (`Source/SampleManagerEngine.h`, `Source/SampleManagerEngine.cpp`) returning pointers to exactly
  the `hasUsableEmbedding` set, in stable order. Defined at global scope (the nearby helpers live
  in an anonymous namespace; the declaration must be the same entity the tests bind to).
- `runFullUMAP` now drives the flat-buffer build **and** the 2D write-back from that single set;
  ineligible samples keep their pre-existing coordinates.
- Regression test `TestUmapEligibility` (`Source/test_umap_eligible_main.cpp`) pins the predicate
  with synthetic items: Valid+full-safe-buffer eligible; FailedRetryable/FailedPermanent/Valid-with-
  empty/short/NaN-buffer/not-processed all excluded; source order preserved.

## 3. PluginProcessor cross-thread data races (BUG-03) — FIXED

`dawBpm`/`isDawPlaying` were plain members written on the audio thread (playhead fetch in
`processBlock`) and read on the message thread (`playSample`, getters). `pendingQuantizedStart`/
`pendingReaderSource`/`pendingPlaySampleRate` were read on the audio thread and written on the
message thread — a genuine data race.

Fix (`Source/PluginProcessor.h` / `PluginProcessor.cpp`):
- `dawBpm` → `std::atomic<double>`, `isDawPlaying` → `std::atomic<bool>` (relaxed loads/stores;
  getters use `.load()`). `lastBeatPosition` stays a plain double (audio-thread-only).
- The three pending members are replaced by a single lock-free handoff:
  `struct PendingPlayback { juce::AudioFormatReaderSource* reader; double sampleRate; }` published
  via `std::atomic<PendingPlayback*>`. Message thread publishes with `exchange()` and retires any
  superseded unconsumed handoff; audio thread `peek`-decides whether the beat boundary / loop-jump
  condition is met, then `exchange(nullptr)` only when it must start; `stopSample()`/destructor
  cancel via `exchange(nullptr)`.

## 4. Unbuffered audition playback (RT-01) — FIXED

`AudioFormatReaderSource` was fed directly from disc decode inside the audio callback's
`getNextAudioBlock()`. Each preview reader is now wrapped in `juce::BufferingAudioReader` with a
dedicated `juce::TimeSliceThread` ("SLO Audition Pre-Read", started in the processor constructor,
stopped in the destructor and `releaseResources`-safe), so the callback pulls from an in-memory
buffer. `setReadTimeout` is left at JUCE's default 0 — the callback never blocks; an underrun plays
silence.

## 5. `detectKeyFromAudio` dead branch + stale comment — CLEANED (behavior-neutral)

A "Nyquist is packed at index 1" special case was dead (the `binHz > min(2000, nyquist)` gate
always excludes bin N/2). Removed it and the misleading comment; all bins now use the standard
interleaved read. No output change.

## 6. Per-click full-library deep copy in the audition path (P-2) — FIXED

Every audition click called `engine.getSamples()`, which deep-copies the whole sample vector
(each `SampleItem` carries a 512-float embedding vector) under `dbLock`, just to read one BPM field
in `prepareReaderSource()`. At a 100k-item library that is hundreds of megabytes of allocation per
click.

Fix:
- New engine accessor `SampleManagerEngine::getSampleBpm(const std::string&)` — a no-copy locked
  linear scan returning that one field (0.0 when not catalogued).
- `prepareReaderSource()` uses it instead of iterating a `getSamples()` copy.
- Deliberately **not** the O(1) `pathToIndex` lookup: `reorganizeSamples()` rewrites `filePath`
  in place without updating the index (only prune/hydration rebuild it), so a map lookup would miss
  every post-sort path. The linear scan preserves today's exact semantics; the deep copy was the cost.

## 7. Swallowed SQLite write failures — FIXED

Every cache write path discarded its `sqlite3_step()`. On a real failure (disk full,
I/O error, constraint/contention), favorites/preview-history/collections/tag-overrides and
batch cache rows were silently dropped, and the batch writers even kept their transactions open
and then `COMMIT`ted a partial result — or, for `restoreUserState()`, committed half a salvaged
user's state after a cache rebuild with nothing logged.

Fix (behavior on the success path unchanged — only diagnostics and failure handling changed):
- New file-local `logWriteStep(db, stmt, what)` runs `sqlite3_step()`, logs a non-`SQLITE_DONE`
  rc with `sqlite3_errmsg()`, and returns the rc so callers keep their success semantics.
- All single-statement user writes now route through it: `setFavorite` (add/remove),
  `recordPreview` + the history-trim `sqlite3_exec`, `createSmartCollection`,
  `deleteSmartCollection`, `applyUserTagOverride`, and both `resetTaxonomyToAuto` statements.
- The batch writers (`upsertCacheEntries`, `persistUmapPositions`, `restoreUserState`,
  `resetTaxonomyToAuto`) now count failed writes and `ROLLBACK` the whole batch on any failure
  (logged) instead of committing a partial result; they `COMMIT` as before when everything is
  `SQLITE_DONE`.

## 8. UMAP flat-matrix size overflow at scale — FIXED

`runFullUMAP()` sized its working buffers with `int` products:

```cpp
int ndim = 512;
std::vector<double> flatEmbeddings(ndim * nobs);      // int * int
std::vector<double> embedding2d(nobs * 2, 0.0);        // int * 2
```

`512 * nobs` overflows `int` past ~4.19M eligible samples and `nobs * 2` past ~1.07B —
both reachable by the scale tiers this path exists to serve. When it overflows, the
negative `int` is converted to a huge `size_t`, so the vector constructor throws
`bad_alloc` (or worse) on the message thread instead of failing cleanly. Fixed by computing
both lengths in `size_t` and adding an explicit guard for the `int nobs` narrowing that
`umappp` requires (skip + log rather than wrap). Width is now tied to
`AcousticClassifier::pannsDim` (which `hasSafeEmbeddingBuffer()` already guarantees the
embedding length equals) instead of a magic `512`.

## Deferred: P-1 decode amplification — investigated, not a safe quick fix

The scan path opens a file up to three times, but they are **semantically distinct**, not
accidental duplication:

1. `loadAndResampleWaveform(filePath, 32kHz, 160000, &contentHash, &duration)` — the
   5-second, resampled PANNs model input; its returned buffer is also what the content hash
   and duration are computed from.
2. `analyzeAudioProperties(filePath)` — a full-length decode at the **original** sample rate
   for the R2 feature set (and `originalSampleRate`/`originalChannels`/`originalBitDepth`).
3. A bounded **≤20s** tempo-view decode, paid only when no trusted BPM metadata/filename
   token exists (an existing, commented trade-off).

Folding (2) into (1) would compute the R2 features at 32 kHz instead of the source rate and
would drop the original-format fields the classifier evidence relies on — a feature-value
change, not a pure refactor. Reusing (1) for (3) is impossible without changing the
content-hash input (the hash covers the returned buffer, so widening its target would change
every existing hash and break duplicate detection). A safe P-1 needs per-feature parity
proof and a hash-independent decode split; that is its own change with its own validation,
so it is left explicit here rather than attempted blind.

## 9. ASan/UBSan preset (`SSM_SANITIZE`) — ADDED (dev-only)

A new `ssm-sanitize` configure/build preset plus an `SSM_SANITIZE` CMake option (default **OFF**,
so every existing preset is unchanged) instruments only this project's targets — engine core,
JUCE-tier consumers, tests/benchmarks, and the plugin — with `-fsanitize=address,undefined`.
The in-tree JUCE tier and the imported ONNX Runtime stay uninstrumented, keeping ASan focused on
our code.

- `-fno-sanitize=alignment` is set: header-only **hnswlib** (compiled into our TUs) does a
  deliberate misaligned label store at `hnswalg.h:1203`, which UBSan flags. arm64 tolerates
  unaligned access, so this is third-party noise that would otherwise mask findings in our code.
- UBSan recover is left on (ASan still hard-aborts on memory errors), so unrelated pre-existing UB
  cannot turn a run into a false test failure.

Validation: `ssm-sanitize` configures and builds clean, and 15 tests were run under it — the
audition/duplicate/persistence/scale set (`TestRtDeadlineStress`, `TestDuplicateDetection`,
`TestUmapEligibility`, `TestFavorites`, `TestPersistedCacheHydration`, `TestCacheIntegrity`,
`TestCacheVersionEnforcement`, `TestSmartCollections`, `TestCorrectionLog`, `TestMapClusters`,
`TestNearDuplicates`, `TestSortLibraryAsync`, `TestPathIndexIntegrity`, `TestPruneMissing`,
`TestSafetyRegression`) — **15/15 pass with 0 sanitizer reports**.

## Deferred: `dbLock` held across the whole UMAP/HNSW/persist pass — documented, not changed

`runUMAPInternal()` (SampleManagerEngine.cpp:5455) takes `dbLock` and then holds it across
`runFullUMAP()` (kNN + 200 UMAP epochs) and `rebuildHnswIndexFull()` and
`persistUmapPositions()` — i.e. seconds to minutes of work at scale. During that window anything
that needs `dbLock` stalls, including the audition BPM lookup (`getSampleBpm`) that a click on the
message thread performs.

It is **not** a one-line "unlock it" change:

- `runFullUMAP()` collects raw `SampleItem*` into `eligible` and writes `s->x/s->y` back through
  those pointers. A concurrent `samples.push_back()` (the scan worker's batch commit, also under
  `dbLock`) can reallocate the vector and invalidate every pointer. The lock is what currently
  keeps those pointers stable.
- `reorganizeSamples()` (sort) and prune erase/reorder `samples` under the same lock; if the lock
  were dropped mid-project, any index-based write-back could target the wrong row.

A safe version needs (a) a snapshot of the embeddings under the lock, (b) the heavy compute
lock-free, (c) write-back under the lock keyed by an identity that survives append, plus (d) a
`generation`/version guard that abandons the write-back if `samples` was structurally mutated
(erase/reorder) during the compute. That is its own design with its own concurrency test, so it is
recorded here as a scoped follow-up rather than changed blind. No behavioral change was made.

## Verification

- Fresh `_build/ssm-dev` Debug build (see Build-environment note): full build exit 0, no errors.
- `TestRtDeadlineStress` (real processor, 2000 callbacks @ 512/44.1kHz, `playSample()` stress every
  100th): **0/2000 deadline misses, 0 allocations in all 2000 tracked callbacks** — the new
  handoff + buffering keeps the tracked callback allocation-free.
- Fully re-verified after the P-2 change in both `ssm-dev` (Debug) and `ssm-qualification`
  (Release) builds: full regression suite passes in both (43 executables; only `TestLicensing`
  exits non-zero, and only because it requires a `<license_key>` argument — a manual/
  license-server-backended tool, not a self-contained regression). `TestRtDeadlineStress` still
  reports 0/2000 deadline misses with 0 allocations.
- The SQLite write-path change was re-verified the same way: full builds in both presets and the
  full 43-test regression pass in Debug and Release (persistence-heavy tests — `TestFavorites`,
  `TestHistory`, `TestSmartCollections`, `TestCorrectionLog`, `TestCachedReclassification`,
  `TestCacheIntegrity`, `TestPersistedCacheHydration` — included).
- The UMAP overflow fix was verified in Debug (full build + 43/43, including
  `TestUmapEligibility` and `TestMapClusters`). A direct test of the overflow branch itself is
  not practical (it would need >4.19M samples × 512 floats ≈ 8.6 GB); the guard is defensive and
  the normal path is covered by the existing UMAP/cluster tests.
- The `SSM_SANITIZE` preset was verified independently under ASan+UBSan (see §9); all shipped
  presets were re-confirmed to configure with the option OFF (Debug configure exit 0).

## Build-environment note (2026-09-16)

The tree was relocated from `/Volumes/Jack_Gandy_1TB_SSD/NITE_DSP/products/...` to
`.../Nite-DSP/Nite-DSP-Operations/monorepo/products/...`, so **every** pre-existing build directory
in and around the product (`build/`, `build_arm64*`, `_build/*`, and the FetchContent `-build`/
`-subbuild` caches under `../_cache/fetchcontent`) carries a stale CMake cache and must be
regenerated. The `-subbuild`/`-build` FetchContent dirs were removed and the pristine `-src` trees
reused; this pass used a fresh `/opt/homebrew/bin/cmake --preset ssm-dev` configure. The default
`cmake` on PATH is the Intel-Rosetta Homebrew build and cannot drive this arm64 tree (xcrun
architecture mismatch) — use `/opt/homebrew/bin/cmake` for all configure/build/test commands.