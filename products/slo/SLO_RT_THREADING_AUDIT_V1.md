# SLO Real-Time / Threading Audit V1

## Findings

- `processBlock` clears input, performs cheap transport/playhead/pointer handoff, and renders from `AudioTransportSource`.
- Reader creation is separated into message-thread `prepareReaderSource`; the source comments explicitly keep file I/O out of the audio callback.
- Engine initialization, hydration, scanning, ONNX inference, and sorting are off the audio thread using owned threads, JUCE ThreadPool, locks, atomics, cancellation, and destructor joins.
- UI callbacks use weak/safe-pointer patterns.
- Cache and DB operations are guarded by `dbLock`; tests include multi-instance and async-sort coverage.

## Limitations (original, 2026-08-2x)

This is source review plus regression evidence, not an instrumented real-time proof. `AudioTransportSource` handoff/destruction, host callback sequencing, allocation behavior, and worst-case lock contention were not measured under an audio callback deadline. No long DAW soak was completed.

## Update — 2026-08-28 (SLO Master Plan V2, Phase 8 / B-010)

The allocation/timing gap above is closed with real instrumented evidence: `TestRtDeadlineStress` (`Source/test_rt_deadline_stress_main.cpp`) drove the real `SmartSampleManagerAudioProcessor::processBlock()` for 2000 iterations at 512 samples/44.1kHz with `playSample()` start/stop stress interleaved, tracking both deadline misses and heap allocations via thread-local `operator new`/`delete` overrides. **Result: 0/2000 deadline misses, 0 allocations across all 2000 tracked callbacks.** See `docs/SLO_RT_DEADLINE_STRESS_V1_REPORT.md` for the full report and its stated scope limits (one code path, one block size, no multi-instance CPU contention, no real DAW host).

**Still not covered**: worst-case lock contention under real host conditions, and real Ableton Live validation (B-004, still blocked — needs a GUI DAW session).

## Update — 2026-09-16 (perf & realtime pass, see `docs/SLO_PERF_AND_REALTIME_PASS_V1.md`)

Three realtime-relevant fixes landed:

1. **Cross-thread atomics**: `dawBpm`/`isDawPlaying` (audio-thread writes, message-thread reads) are
   now `std::atomic`; the pending-start members that were shared between threads were replaced by a
   single lock-free `std::atomic<PendingPlayback*>` handoff (publish via `exchange`, retire-superseded
   by the replacer, consume via `exchange(nullptr)` on the callback at the beat boundary,
   `exchange(nullptr)` to cancel in `stopSample`/destructor). `lastBeatPosition` stays a plain double
   (audio-thread-only).
2. **Audition read-ahead**: every preview reader is wrapped in `juce::BufferingAudioReader` over a
   dedicated `juce::TimeSliceThread` ("SLO Audition Pre-Read"), so `getNextAudioBlock()` pulls from an
   in-memory buffer instead of decoding from disk mid-callback. Timeout stays at the JUCE default 0 —
   the callback never blocks; an underrun yields silence.
3. Removed a dead "Nyquist packed at index 1" special case in `detectKeyFromAudio` (behavior-neutral).

Re-ran `TestRtDeadlineStress` against the rebuilt processor: **0/2000 deadline misses, 0 allocations
in all 2000 tracked callbacks**; max callback duration improved 1.085ms → 0.127ms (updated table in
`SmartSampleManager/docs/SLO_RT_DEADLINE_STRESS_V1_REPORT.md`). The measurement still covers one code
path at one block size, and B-004 (real Ableton validation) remains the open RT gate.

## Decision

**PASS WITH LIMITATIONS** for architecture, now with real instrumented backing for the allocation/timing claim specifically. **STILL NOT QUALIFIED** for a hard RT release gate — that requires the Ableton validation this update didn't and couldn't close (B-004).
