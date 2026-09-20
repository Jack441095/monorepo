# SmartSampleManager — Async Plugin Startup

Phase 2, Sections 15-17. Addresses `docs/COMMERCIAL_RELEASE_BLOCKERS.md` P1 #1 (synchronous
ONNX + SQLite init blocks DAW project load).

## What was blocking

`PluginProcessor.cpp`'s constructor called `engine.init()` synchronously — ONNX `Env`/`Session`
construction (including the CoreML execution-provider compile step) ran on whatever thread
constructs the plugin, which for most hosts is the thread doing DAW project load. Per
`docs/REALTIME_SAFETY_AUDIT.md`, this meant DAW project load blocked on disk I/O + ONNX/CoreML
compilation once per plugin instance, worse with multiple instances in one project.

(SQLite cache open, the other half of that finding, was already comparatively fast — `openCacheDb()`
still runs synchronously in the `SampleManagerEngine` constructor, unchanged. It's a local file
open plus a few `PRAGMA`s and `CREATE TABLE IF NOT EXISTS`/additive `ALTER TABLE`s, not a
meaningful stall next to ONNX/CoreML compilation. Not addressed further this pass.)

## New state machine (`Source/SampleManagerEngine.h`)

```cpp
enum class EngineInitState { Uninitialized, Initializing, Ready, Degraded, Failed };
```

- **Uninitialized** — before `initAsync()` is called. Not observable in practice, since
  `PluginProcessor`'s constructor calls `initAsync()` immediately, before the editor (the only
  thing that polls state) can exist.
- **Initializing** — background thread is running `init()`.
- **Ready** — model loaded successfully; `isEmbeddingModelAvailable()` returns true.
- **Degraded** — model failed to load (missing/corrupt file, bad session creation); everything
  *except* embedding-dependent features (find-similar, acoustic dedup signal) stays fully
  functional — scanning, metadata search, browsing, waveform preview, taxonomy. Matches Phase 2
  Section 17's "safe degraded mode" requirement.
- **Failed** — reserved, not currently reachable. Nothing in the current engine setup path can
  fail in a way that leaves *nothing* usable (SQLite open failures already degrade gracefully per
  `docs/DATABASE_HARDENING.md`, ONNX failures degrade to `Degraded` not `Failed`). Kept in the
  enum for a future genuinely-unrecoverable case rather than removed, per the master prompt's own
  explicit state list (Section 16).

## Implementation

`SampleManagerEngine::initAsync()` stores `Initializing`, then `juce::Thread::launch()`s a
fire-and-forget background thread that calls the existing (unchanged) synchronous `init()` and
stores `Ready`/`Degraded` based on the result. `PluginProcessor`'s constructor now calls
`initAsync()` instead of `init()` — returns immediately, UI available right away, model loads in
the background.

### Thread safety

`env`/`session` (the ONNX objects) are constructed on the init thread but read from the
`InferenceWorker` thread (`runInferenceBatch()`) and potentially the message thread
(`isEmbeddingModelAvailable()`). Both read sites now gate on
`engineState.load(std::memory_order_acquire) == EngineInitState::Ready` rather than a raw
`session != nullptr` check. This is the standard "publish a pointer via an atomic flag" pattern:
the release-store in `initAsync()`'s lambda (after `session`/`env` are fully constructed)
synchronizes-with any acquire-load that observes `Ready`, guaranteeing the reading thread sees a
fully-constructed session — without needing a separate lock around every access.

### What happens to work queued before the model is ready

Nothing new required: scanning (`addPathToQueue`), WAV decode, TagLib metadata read/write, and
Ableton taxonomy classification don't touch `session` at all — only the embedding step does.
`docs/ONNX_FAILURE_HANDLING.md`'s new failure model already handles `session` not being ready as
a `FailedRetryable` outcome per-file (not cached, retried on the next scan) — so files scanned
during the brief init window before the model finishes loading simply get retried automatically
once it's `Ready`, with no special-casing needed in this pass.

## UI surfacing (`Source/PluginEditor.cpp`, `timerCallback`)

The existing 60Hz status-label update now prefixes the DAW-sync status text with the engine
state when it isn't `Ready`:

```text
Loading AI model... | DAW Sync: 120.0 BPM [STOPPED] | Map: 0 samples
Similarity search unavailable (model failed to load) | DAW Sync: ...
```

Deliberately non-alarming wording for the `Degraded` case (per Section 17's "never silently
pretend acoustic intelligence is working," but also "show a clear non-alarming user message") —
states what's unavailable without implying the whole plugin is broken.

## What was NOT changed this pass

- **SQLite open** — still synchronous in the `SampleManagerEngine` constructor; not a measured
  problem, see above.
- **A richer degraded-mode UI** (e.g. disabling the "Find Similar"/duplicate-detection buttons
  outright while `Degraded`, rather than just a status-text note) — the buttons still work
  today, they'll just act on samples that never get a `Valid` embedding (an empty result, not a
  crash, per `docs/ONNX_FAILURE_HANDLING.md`). Disabling them outright is a small additional UI
  change that wasn't required to fix the P1 startup-blocking bug and is left as a follow-up
  polish item, not a correctness or safety issue.

## A real regression found and fixed during this pass

The first version of this change set `engineState` to `Ready`/`Degraded` only inside
`initAsync()`'s lambda wrapper, not inside `init()` itself. Since every `Test*` binary calls
`init()` directly (synchronously, not via `initAsync()`), `engineState` stayed at
`Uninitialized` forever for all of them — so `runInferenceBatch()`'s new
`engineState == Ready` gate always took the "model unavailable" branch even though the model
had actually loaded successfully, clearing every embedding (per `docs/ONNX_FAILURE_HANDLING.md`'s
new failure model). That alone would just mean broken embeddings, but two existing functions
(`rebuildHnswIndexFull()`, `runFullUMAP()`'s `flatEmbeddings` fill loop) assumed every
`isProcessed` sample had a real 512-float embedding and read/passed `embedding.data()`
unconditionally — with `embedding` now empty, this read out of bounds and **crashed 4 of 8
regression tests with SIGSEGV** (confirmed via a macOS crash report + `atos` symbolication,
faulting inside `hnswlib::addPoint`/Eigen's UMAP internals on garbage pointers).

Two fixes:

1. **Root cause**: moved the `engineState.store(Ready/Degraded, ...)` calls from `initAsync()`'s
   wrapper into `init()` itself, so any caller — direct or via `initAsync()` — leaves `engineState`
   correct.
2. **Defense in depth**: `rebuildHnswIndexFull()`, `placeNewSamplesIncrementally()`, and
   `runFullUMAP()` no longer assume `isProcessed == true` implies a valid embedding — each now
   explicitly checks `embedding.size() == 512` (via a shared `hasValidEmbedding` predicate in
   `runFullUMAP()`) before touching `embedding.data()`, skipping samples without a valid
   embedding rather than reading out of bounds. This is real latent-bug hardening independent of
   the `engineState` fix: any future code path that leaves `isProcessed` true with a
   non-`Valid` embedding (which is now an expected, documented state per
   `docs/ONNX_FAILURE_HANDLING.md`) would have hit the same class of crash.

Caught before being reported as done — this doc originally claimed "no regression" based on an
incomplete first test run; re-verified after the fix with a full 8/8 pass, confirmed via log
output that real 512D embeddings are produced again (`TestEmbeddingQuality`'s cosine-similarity
assertions passing, `TestSampleEngine`'s "Embedding dimension: 512" line present).

## A second, more serious regression found later the same session: use-after-free

While implementing dependency bundling (`docs/RUNTIME_DEPENDENCY_STRATEGY.md`), a **clean** VST3
build started reliably segfaulting during JUCE's own moduleinfo-generation build step
(`juce_vst3_helper`, which loads the just-built plugin to introspect it). Root-caused via a real
crash report + `lldb`/`atos` symbolication: the crash was inside ONNX Runtime's static
operator-schema registry, on a background thread named `"anonymous"` — the thread
`initAsync()` spawns via `juce::Thread::launch()`.

Two hypotheses were tested and ruled out first (both real, defensible engineering guesses, both
wrong): a concurrent-`initAsync()` race (fixed with a mutex around Env/Session construction —
didn't help) and a missing macOS autorelease pool around the CoreML EP's Objective-C calls
(wrapped in `JUCE_AUTORELEASEPOOL` — didn't help either). Both fixes were kept since they're
independently correct hardening, but neither was the actual cause.

**The real cause**: `juce::Thread::launch()` is fire-and-forget — nothing in
`SampleManagerEngine` ever waited for it. If the engine is destroyed while `init()` is still
running on that thread (exactly what happens when a short-lived introspection tool constructs
the plugin, queries it, and destroys it quickly — but this is not tooling-specific; any host
that briefly instantiates-then-removes a plugin instance could hit the same window), the
background thread goes on touching `env`/`session`/`engineState`/`modelPath` on a destroyed
object. That's a genuine use-after-free, and ONNX Runtime's static registry (shared,
process-wide, non-trivial internal state) is exactly the kind of memory that reliably shows
corruption from this class of bug.

**Fix**: `initAsync()` now starts an engine-owned `std::thread` (member `initThread`) instead of
an unmanaged `juce::Thread::launch()`. `~SampleManagerEngine()` joins it as the very first thing
it does — before touching anything `init()` might still be using — matching the same
"wait for background work before tearing down what it touches" pattern the destructor already
used for `scanPool`/`inferenceWorker`/`metadataWriteWorker`.

## A third round: systematic sweep for the same bug class

After finding the same unmanaged-thread use-after-free pattern twice (once via a reproduced
crash, once proactively in `reorganizeSamplesAsync()` — see `docs/SORT_LIBRARY_BACKGROUND.md`),
the codebase was searched systematically for every other instance of the same *general* risk
class: a callback capturing `[this]` that crosses a real async boundary (a background thread, a
timer delay, a modal dialog result) with no lifetime tie back to the object it touches.

**`grep`-confirmed zero remaining unmanaged thread spawns** (`juce::Thread::launch()`/raw
`std::thread(...)`) outside the two already fixed. But a related pattern was still present:
**7 identical `juce::MessageManager::callAsync([this](){ ... })` sites in
`SampleManagerEngine.cpp`**, all touching `onUpdate` after the delay, and **4 sites in
`PluginEditor.cpp`** (a search-debounce timer, two 1.5s "revert button text" timers, and a modal
confirmation-dialog callback) doing the equivalent for a `juce::Component`.

Both are exactly the same underlying bug shape as the thread-based ones — `onUpdate` fires from
multiple worker threads throughout a scan and a host can destroy the plugin (or close the editor)
at any time — just via JUCE's message-queue/timer mechanisms instead of raw threads, which can't
be "joined" the same way. Fixed with JUCE's own idiomatic tools for exactly this problem:

- **Engine side**: added `JUCE_DECLARE_WEAK_REFERENCEABLE(SampleManagerEngine)` and consolidated
  all 7 duplicated call sites into one `notifyUpdateNow()` helper that captures a
  `juce::WeakReference<SampleManagerEngine>` instead of a bare `this`, checking `.get() !=
  nullptr` before touching the (possibly-destroyed) object. Also removed 6 copies of duplicated
  code in the process.
- **Editor side**: wrapped each of the 4 sites with `juce::Component::SafePointer<
  SmartSampleManagerAudioProcessorEditor>`, the Component-specific equivalent, including the
  `reorganizeSamplesAsync()` completion callback in `startSortLibrary()` (which itself crosses a
  real async boundary — a large sort can run for seconds, well within a plausible
  editor-closed-mid-operation window).

None of these were ever observed to crash — found by pattern-matching against the two bugs that
*did* crash, not by another reproduction. Fixed proactively rather than waiting for a third
incident.

## Verified this pass

Rebuilt `SmartSampleManager_Standalone`, `SmartSampleManager_VST3`, `SmartSampleManager_AU`, and
all 12 engine-linked regression test targets from a clean state — clean compile (0 real
compiler errors, confirmed via `grep -c "error:"` on the raw build log rather than trusting a
misleading pipe exit code), **all 12 tests pass, exit code 0, zero leak warnings**. The VST3
moduleinfo-generation crash that originally motivated this whole investigation no longer
reproduces across multiple clean rebuilds.
