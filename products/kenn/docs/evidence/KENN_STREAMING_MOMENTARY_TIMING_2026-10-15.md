# Streaming momentary timing — 15 October 2026

This checkpoint addresses E1 in [KENN_PLAN.md](../../KENN_PLAN.md). It uses
generated audio and isolated FakeLive verification. The streaming candidate
remains disabled in production and absent from the HTTP handoff. This receipt
does not qualify EBU Mode, installed plug-ins or Ableton playback.

## Starting state and reproduction

Work began on `feature/reference-review-grade` at `75042bac`, matching origin.
The only pre-existing working-tree changes were untracked capability-landscape
research; they were left untouched and excluded from publication.

The previous generated cases 13/14 measured momentary maxima only every 100 ms.
Case 14 missed the ±0.1 LU tolerance on 16/20 maxima at each of 44.1/48/96 kHz;
the worst absolute error was 0.453583 LU. Case 11 passed. The stricter native
regression required every generated case 13/14 maximum to meet the original
tolerance before implementation: **1,058 checks, 102 failures** on the old code.

Ranked hypotheses were observation-grid energy loss, weighting/calibration error,
then reset/segment attribution. The fix preserves the weighting coefficients
and continuous test streams, changing only timing and bounded energy storage.

## Reuse decision

The standing reuse check was repeated against upstream documentation, source
and licences on 15 October. No dependency was added.

| Candidate | Measurement and runtime fit | Decision |
|---|---|---|
| Existing KENN `StreamingMeter.h` | Persistent per-channel K-weighting, 400 ms/3 s rectangular energy, bounded histogram/FIR history, per-instance state and invalid-input retirement already exist. Supported rates are 44.1/48/96 kHz. | Reuse the existing energy path with finer internal bins. Keep 100 ms current readings, peak intervals and integrated gates; retain finer maxima with explicit sample positions. Verify the actual implementation rather than adopting a library claim. |
| Existing JUCE 8.0.2 | The pinned DSP inventory has no BS.1770 loudness meter. `BallisticsFilter` is a recursive attack/release peak/RMS envelope, not a rectangular 400 ms energy window. Preparation resizes state. Existing AGPLv3/commercial distribution terms remain unchanged. | It would still need the timing/window layer and would change the qualified weighting path. Retain the current meter for this bounded fix. [Module inventory](https://github.com/juce-framework/JUCE/blob/8.0.2/modules/juce_dsp/juce_dsp.h), [filter source](https://github.com/juce-framework/JUCE/blob/8.0.2/modules/juce_dsp/processors/juce_BallisticsFilter.cpp), [licence](https://github.com/juce-framework/JUCE/blob/8.0.2/LICENSE.md). |
| libebur128 v1.2.6 | Momentary queries sum 400 ms at the current filtered-ring cursor, independently of 100 ms integrated gates. Each query scans the interval. Initialization allocates ring and resampler scratch; S-mode stereo arrays at 96 kHz total about 5.53 MB per state before overhead. MIT fits the existing screen. | Keep as an independent comparison option. A new dependency, adapter and allocation/reset/accuracy qualification exceed this timing fix. Existing KENN bins avoid rescanning every filtered sample per query. [Query source](https://github.com/jiixyj/libebur128/blob/v1.2.6/ebur128/ebur128.c#L1109-L1138), [initialization](https://github.com/jiixyj/libebur128/blob/v1.2.6/ebur128/ebur128.c#L411-L470), [licence](https://github.com/jiixyj/libebur128/blob/v1.2.6/COPYING). |

[EBU Tech 3341, November 2023, §§2.2–2.3 and Table 1](https://tech.ebu.ch/docs/tech/tech3341.pdf)
distinguishes ungated momentary/short-term windows from integrated gating.
A 10 ms internal grid has an ideal nearest-grid loss of approximately
`10 log10(395/400) = -0.0546 LU` for an arbitrary 400 ms rectangular tone.
That calculation motivates the hop; generated numerical tests must establish
the complete filtered error. Cases 13/14 use 20 ms offsets, so additional starts
between 10 ms grid points are needed. Current readings and interval maxima
must retain different names and sample intervals.

## Implementation and numerical results

`StreamingMeter.h` adds forty fixed 10 ms energy bins. Once 400 ms is ready,
each observation re-sums those bins rather than subtracting an expired loud bin;
this retains the existing protection against loud-to-quiet cancellation.
The greatest energy in each completed 100 ms interval is retained with its
actual window-end sample. The interval is open at its left boundary and closed
at its right boundary; the maximum's own window spans the preceding 400 ms.
Ready digital silence has zero energy, a measured sample position and no finite
LUFS value. Warm-up remains unavailable.

`push()` still returns one snapshot per 100 ms. Current M/S, 400 ms integrated
blocks with 75% overlap, and the delayed 100 ms true-peak interval retain their
contracts. The new maximum is distinct from current M: the 500 ms worker
snapshot retains a tone's earlier maximum even after its current reading falls.
No HTTP field, publication rate, dependency or callback entry point changes.

| Generated measurement | 44.1 kHz worst error, LU | 48 kHz | 96 kHz |
|---|---:|---:|---:|
| Case 13, twenty start offsets | 0.00699330 | 0.00640471 | 0.00402413 |
| Case 14, twenty continuous successive maxima | 0.00699334 | 0.00640487 | 0.00402427 |
| Case 11, twenty continuous successive maxima | 0.0656667 | 0.0662565 | 0.0686450 |
| Arbitrary starts: 1 frame, 7/45/95 ms plus 1 frame | 0.0471606 | 0.0477458 | 0.0501456 |

Every generated maximum meets its unchanged ±0.1 LU tolerance. Cases 13/14
now assert that tolerance for every offset instead of accepting the known gap.
These are generated signals from the table, not the EBU's authentic vectors
or a full EBU Mode claim. A mutation that restricts momentary observations to
100 ms causes **114 failures in 1,301 checks**, including the original
16/20 case-14 failures per rate; restoring 10 ms observations gives
**1,304 checks, zero failures**. Counts differ because readiness controls
position assertions. Case 11 remains unchanged and passing.

All **33 generated fixture/rate combinations** also pass the existing
independent NumPy/SciPy continuous-filter comparison: calibration, anti-phase,
changing level, DC, silence, noise and peak cases 15–19, at 44.1/48/96 kHz.
That comparison still checks current 100 ms snapshots, not interval maxima;
it protects the existing M/S and peak path from the timing change.

## Storage, callback safety and verification

On this arm64 build, `sizeof(KENNStreamingMeter)` changes from 26,688 to
27,096 bytes (**+408 bytes**), including forty doubles (320 bytes) and fixed
bookkeeping/snapshot state. `sizeof(KENNStreamingMeterSnapshot)` changes from
136 to 176 bytes (**+40 bytes**). Analysis history stores seven snapshot copies
per instance in addition to the meter's own latest snapshot. These fixed
members grow even when the candidate is disabled. No duration-dependent
container, queue-size or thread change is introduced.

At steady state, the new 40-bin sum runs 100 times per second:
**4,000 additions/second/insert**, plus two extra scalar energy additions per
stereo frame, hop bookkeeping/division and at most ten additional logarithmic
conversions per second. This executes in the analysis consumer; it does not
add DSP to the audio callback. These operation counts are not CPU timings.

The native tests cover reset inside a partial hop, fresh 400 ms warm-up, ready
silence, non-finite retirement and recovery, unsupported rates, active-instance
isolation, worker propagation, source/seek/overflow retirement, paired history
and the disabled production default. Ordinary C++ `new`/`new[]` instrumentation
observed zero allocations in the guarded callback/worker paths. This does not
claim a malloc/aligned-allocation audit, ThreadSanitizer run or host RSS gate.

Scoped verification on the final sources:

- Release/arm64 build of `TestStreamingMeter`, `TestContinuousAnalysis`,
  `TestRealtimeThreadSafety` and `TestCommandIntegration`: passed. Existing
  `PluginProcessor.cpp` integer-to-double warnings and JUCE/SDK warnings remain;
  no warning originates in the changed meter or test.
- CTest for those four targets with `KENN_TEST_OFFLINE_ONLY=1` and
  `KENN_LIVE_BACKEND=fake`: **4/4 passed**. StreamingMeter reports
  **1,304 checks, zero failures**.
- Backend scoped suite with compiled meter and command binaries,
  `KENN_LIVE_BACKEND=fake` and `KENN_LLM_ENABLED=0`: **206 passed,
  4 deselected**. The four publisher timing profiles were deliberately excluded
  because machine conditions cannot qualify them. The native HTTP client ran
  against the isolated FakeLive server, including two-insert ownership and
  selected analysis; the Python flow verifies proposed Apply/readback/Undo.
- Existing export-script tests: **24 passed** with
  `PYTHONPATH=products/kenn/tooling`.
- Independent read-only reuse/code review: no blocking finding.
- `git diff --check`: passed.

Reproduce the scoped native check from the monorepo root:

```sh
/opt/homebrew/bin/cmake --build workspace/builds/kenn-plugin-e1 \
  --target TestStreamingMeter TestContinuousAnalysis TestRealtimeThreadSafety TestCommandIntegration -j 2
KENN_TEST_OFFLINE_ONLY=1 KENN_LIVE_BACKEND=fake /opt/homebrew/bin/ctest \
  --test-dir workspace/builds/kenn-plugin-e1 \
  -R '^KENN\.(ContinuousAnalysis|RealtimeThreadSafety|StreamingMeter|CommandIntegration)$' \
  --output-on-failure
```

The backend command ran from `apps/backend` with
`KENN_STREAMING_METER_TEST_BINARY` and `KENN_NATIVE_COMMAND_TEST_BINARY` pointing
to the above build's executables:

```sh
KENN_LIVE_BACKEND=fake KENN_LLM_ENABLED=0 .venv/bin/python -m pytest -q \
  src/kenn/tests/test_profile_streaming_meter.py \
  src/kenn/tests/test_live_track_analysis.py src/kenn/tests/test_live_paired_analysis.py \
  src/kenn/tests/test_plugin_handoff.py src/kenn/tests/test_plugin_insert_sources.py \
  src/kenn/tests/test_plugin_parameters_api.py -k 'not native_feature_publishers'
```

The independent comparison called `scripts.profile_streaming_meter.qualify()`
directly with this binary; it did not call the performance-profile `run()`.

## Machine and qualification conditions

The initial condition was an arm64 Apple M3 (`Mac15,13`), 16 GiB memory,
Release/arm64 CMake build, battery at 60% and discharging. A later sample showed
59%, Live using about 80.6% of one CPU core, load averages 2.65/2.77/3.17,
24.81 MiB swap used and substantial compressed memory. `pmset -g therm`
reported no recorded thermal/performance warning. Live was observed as a
process only; no Live session was read or written.
After verification the machine remained on battery, 57% and discharging;
load averages were 3.43/3.04/3.07, with no recorded thermal/performance warning.

These conditions do not satisfy the controlled mains timing requirement.
Functional correctness and allocation checks can run, but their elapsed test
times do not close a CPU, callback-deadline or publisher gate. Do not substitute
the historical 65-second result for qualification of this build.

The pending protocol remains in E1: wall-paced callback coverage at
44.1/48/96 kHz, 64/128/256/512/1,024-frame buffers and 1/8/32/64 inserts;
isolated FakeLive publisher cells; sustained 64-insert operation across the
60-second rate bucket; and the separate five-minute workload cells plus
64-insert resident-model/ordinary-traffic contention. The scheduled disposable
Live soak remains owner-supervised. Publication stays capped at 2 Hz.
Cases 6–8, native LRA, authentic vectors, remaining temporal/transient and
peak promotion checks also stay open. The candidate remains disabled until
all relevant promotion gates pass. Session-bound plug-in grading was not started.

## Publication infrastructure

The current checks for `75042bac` still could not start. The
[KENN core run](https://github.com/Nite-DSP/monorepo/actions/runs/38735644338)
reported failed account payments or a spending limit. The native package and
sharing workflows also failed before execution. Local scoped checks and the
existing committed-tree export script are required for this checkpoint;
blocked Actions are not passing CI.
