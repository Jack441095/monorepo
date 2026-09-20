# SmartSampleManager — Realtime Safety Audit

Phase 1, Section 4-5, 19-20. Source-code audit of everything reachable from the audio callback, the UI thread, plugin startup, and multi-instance state. One CRITICAL finding was fixed during this pass (see below); everything else is documented as-is.

## 1. Realtime audio callback (`processBlock`, `PluginProcessor.cpp`)

**Before this audit:** `processBlock`'s quantized-audition-start path called `startSamplePlaybackInternal()` directly from the audio thread, which opened a file (`formatManager.createReaderFor`), heap-allocated an `AudioFormatReaderSource`, and iterated a full lock-protected deep copy of the entire sample database (`engine.getSamples()`) to resolve BPM — all on the realtime thread. **CRITICAL.** This is exactly the class of bug that produces audible dropouts and can fail an AU/VST3 host's realtime-safety validation.

**Fix applied:** File I/O, allocation, and the BPM lookup now happen in `prepareReaderSource()`, called from `playSample()` on the message thread — whether or not a quantized start is pending. `processBlock` now only does a cheap pointer handoff (`startPreparedPlayback`) at the beat boundary: `std::move` an already-open reader into `readerSource`, call `transportSource.setSource()`/`start()`. No filesystem access, no heap allocation for a new reader, no `dbLock` acquisition on the audio thread anymore.

**Residual, accepted risk:** `startPreparedPlayback` still calls `readerSource.reset()` on the *previous* reader, and `transportSource.setSource()` itself may do bounded internal work (JUCE's `AudioTransportSource` can allocate a `ResamplingAudioSource` wrapper). This was already true of the pre-fix code in the *non-quantized* play path (called from the message thread there, and still called from the audio thread here) and is not resolved by this pass — a fully lock-free disposal queue for old readers would be needed to eliminate it completely. Given it's a small, bounded, deterministic-cost operation (not file I/O or an unbounded copy), and the master prompt's own guidance against over-engineering, this is left as a documented LOW-severity residual rather than a blocker. Flagged in `docs/COMMERCIAL_RELEASE_BLOCKERS.md` as P2.

Everything else in `processBlock` (playhead read, `transportSource.getNextAudioBlock()`) is realtime-safe JUCE primitives — clean.

## 2. UI thread responsiveness

Well engineered overall: file scanning (`addPathToQueue` → `scanPool`), ONNX inference (dedicated `InferenceWorker` thread, batched 32-64 files), and UMAP/HNSW work (coordinator `run()` thread) are all properly backgrounded, with UI updates delivered via `juce::MessageManager::callAsync` (250ms coalesced).

Two exceptions remain synchronous on the message thread:

| Operation | Location | Severity |
|---|---|---|
| Initial directory enumeration (`file.findChildFiles()`) | `SampleManagerEngine.cpp:413-416`, called from `PluginEditor.cpp:493,679` | LOW — brief stall on very large directory trees before work is handed to the pool |
| "Sort Library" (`reorganizeSamples()`) | `SampleManagerEngine.cpp:2153`+, called from `PluginEditor.cpp:717` | MEDIUM-HIGH — synchronous per-file disk move/copy under `dbLock`, will visibly freeze the UI on large libraries. Not fixed in this pass (a real feature — backgrounding a file-reorganization operation safely needs its own progress/cancel UX design, out of scope for a safety-fix pass). Flagged as P1 in `docs/COMMERCIAL_RELEASE_BLOCKERS.md`. |

`findDuplicateGroups()` and `pruneMissingFiles()` are also synchronous button handlers but operate on in-memory data / cheap `stat()` calls — acceptable. `findSimilarSamples()` is an O(log N) HNSW query — fine.

## 3. Startup path

Both ONNX model load and SQLite cache open happen **synchronously during `PluginProcessor` construction** — `engine.init()` builds `Ort::Env`/`Ort::Session` (including a CoreML execution-provider compile) with no async path, and the engine constructor opens the SQLite cache synchronously. This means DAW project load blocks on disk I/O + ONNX/CoreML compilation for however long that takes, once per plugin instance.

**Not fixed in this pass** — converting this to a real async init (background thread + "ready" flag the editor polls) is a legitimate feature change, not a quick safety patch, and risks introducing new bugs around "what does the UI show before the engine is ready" without more design time than a readiness audit warrants. Flagged as P1 in `docs/COMMERCIAL_RELEASE_BLOCKERS.md` — should be fixed before a paid release, since hosts that load many instances during project open (or a project with several SmartSampleManager instances) will feel this as a real stall.

## 4. Multi-instance state sharing

Correct: no global/static singleton holds the ONNX session, database connection, or thread pool. `SampleManagerEngine` is a plain non-static member of `PluginProcessor`; each plugin instance loads its own complete copy of the model and runs its own scan/inference/UMAP threads. This is the right correctness choice — the cost is N instances loaded in one DAW session multiply CPU/RAM/thread usage N times, worth a "don't load 20 instances casually" caveat in user-facing docs, not a code fix.

One caveat: `getCacheDbFile()` resolves to a single fixed path shared across all instances/processes, WAL mode is enabled (permits concurrent readers/one writer) but no `PRAGMA busy_timeout` is set — concurrent instances scanning simultaneously could hit `SQLITE_BUSY` without a documented retry. Not verified whether this is silently swallowed elsewhere; worth a follow-up if simultaneous multi-instance scanning turns out to be a real usage pattern. P3.

`AppLogger`/`AppSettings` are explicit, intentional process-wide singletons for logging/preferences — appropriate, not audio-relevant.

## Summary

| # | Finding | Severity | Status |
|---|---|---|---|
| 1 | Audio-thread file I/O + allocation + locked deep copy in `processBlock` | CRITICAL | **Fixed this pass** |
| 2 | Old-reader disposal + `transportSource.setSource()` internal cost still on audio thread | LOW | Documented, not fixed (P2) |
| 3 | "Sort Library" freezes UI on large libraries | MEDIUM-HIGH | Documented, not fixed (P1) |
| 4 | Directory enumeration on message thread before pool dispatch | LOW | Documented, not fixed (P3) |
| 5 | Synchronous ONNX + SQLite init blocks DAW project load | HIGH (startup stall) | Documented, not fixed (P1) |
| 6 | No `busy_timeout` for concurrent multi-instance cache writes | LOW | Documented, not fixed (P3) |
| 7 | Per-instance model/DB loading (correct, by design) | — | Sound, no action needed |
