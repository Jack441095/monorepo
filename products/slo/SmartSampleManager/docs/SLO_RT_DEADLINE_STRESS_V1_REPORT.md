# SLO RT Deadline-Stress + Allocation Report V1

**Generated for:** SLO Master Plan V2, Phase 8 (B-010)
**Purpose:** `SLO_RT_THREADING_AUDIT_V1.md` was source-review-only — "allocation behavior... were not measured under an audio callback deadline." This is the first instrumented measurement.

## Method

New test target `TestRtDeadlineStress` (`Source/test_rt_deadline_stress_main.cpp`), built against the real `SmartSampleManagerAudioProcessor` (not a mock or simplified stand-in — the actual `PluginProcessor.cpp`/`PluginEditor.cpp` and their full UI-component dependency graph, compiled fresh into this target since they aren't part of the shared lightweight test-core object library).

- 2000 iterations of `processBlock()` at 512 samples / 44.1kHz (deadline ≈11.61ms), preceded by 10 untracked warm-up iterations.
- `playSample()` called every 100th iteration, always between (never inside) the tracked/timed window — matching how a real DAW's message thread and audio thread interact.
- Thread-local `operator new`/`delete`/`new[]`/`delete[]` overrides: increment-only counters, thin `malloc`/`free` passthrough, gated by a thread-local flag active only during the tracked `processBlock()` call. Safe process-wide — never changes allocation behavior, only counts it, and is scoped per-thread so it can't miscount other threads' work.

## Result

| Metric | Value (original pass) | Value (2026-09-16, after atomics + read-ahead buffering) |
|---|---|---|
| Deadline misses | 0 / 2000 (0%) | **0 / 2000 (0%)** |
| Callback duration (mean) | 0.006 ms | 0.009 ms |
| Callback duration (max) | 1.085 ms | 0.127 ms |
| Callback duration (p99) | 0.011 ms | 0.038 ms |
| Total allocations across all tracked callbacks | 0 | **0** |
| Callbacks with any allocation | 0 / 2000 | **0 / 2000** |

Both numbers are clean with wide margin — mean callback duration is ~1200x under the deadline, and
genuinely zero heap allocations were observed in any of the 2000 tracked calls, including the ones
immediately following a `playSample()`-triggered quantized-start transition. The max duration also
improved (1.085ms → 0.127ms) in the rebuilt pass.

## 2026-09-16 update — changes under test

The measured processor now contains the items from `docs/SLO_PERF_AND_REALTIME_PASS_V1.md`: atomic
`dawBpm`/`isDawPlaying`, a lock-free `PendingPlayback` publish/consume handoff (replacing the racy
pending-start members), and `BufferingAudioReader` read-ahead on a dedicated `TimeSliceThread`
("SLO Audition Pre-Read"). The 0-allocation result validates that the callback still does nothing
but a pointer exchange plus `transportSource` handoff — the read-ahead happens on the buffering
thread, which is not the tracked callback thread and is invisible to this instrumentation.

## Interpretation

This is real, positive evidence — not just an architecture claim. `SLO_RT_THREADING_AUDIT_V1.md`'s source-review assessment ("Realtime-safe: pendingReaderSource was already opened on the message thread... this is just a pointer handoff plus transportSource.start(), no file I/O") is now backed by an actual instrumented measurement showing exactly that: no allocation, no deadline miss, even across the state-transition path.

**What this does and doesn't prove**: this measures one specific, real code path (basic playback + quantized start/stop under an idle synthetic buffer) at one block size/sample rate. It does not cover every host callback pattern (block-size changes mid-session, sample-rate changes, multiple plugin instances contending for CPU, or actual host automation/parameter changes — SLO has no automatable parameters currently, so that's not a gap, just noting the scope). Real DAW validation (Ableton Live specifically, per B-004) remains a separate, still-open requirement — this closes the allocation/timing half of B-010's evidence gap, not the full RT-safety picture end to end.

## Build note for future maintainers

`PluginProcessor.cpp`/`PluginEditor.cpp` are not part of `SSM_ENGINE_CORE_SOURCES` — they're only otherwise compiled into the full `SmartSampleManager` plugin target. This test target compiles them fresh via `EXTRA_SOURCES`, following the same tier (`ssm_juce_ui`) and pattern `TestPrecisionBrowserSorting` already established. Also needed `${SODIUM_INCLUDE_DIR}`/`${SODIUM_LIBRARY}` explicitly (deliberately excluded from the default engine-test runtime libraries) since `PluginEditor.cpp` pulls in `Licensing/LicenseManager.cpp`. And critically: call `SampleManagerEngine::setCacheDbDirectoryOverrideForTesting()` before constructing the processor — its constructor builds a `SampleManagerEngine` internally, which fails closed against the real production cache path otherwise (by design, a safety guard — don't weaken it, just call the override like every other test binary does).
