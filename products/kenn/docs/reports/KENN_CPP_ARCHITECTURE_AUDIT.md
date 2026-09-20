# KENN C++ Architecture Audit

Audit date: 2026-09-01. Scope: `common/AudioTooRealtimeCore.h`,
`plugins/kenn-vst3-au/` (CMake, plugin sources, thread-safety and integration
tests). This audit is grounded in this session's own build/test work
(configured, built, and ran everything cited here live, on this machine)
rather than static code reading alone -- see `docs/KENN_FULL_AUDIT_2026-09-01.md`
Section 3 for the summary and `docs/KNOWN_ISSUES.md` ISSUE-13 for the
original build-verification writeup this expands on.

Companion doc: `docs/KENN_CPP_ARCHITECTURE_NOTES.md` is the owner's
standing architecture *decision* (C++ for measured real-time work, Python
for everything else, profile before rewriting). This document is the
*audit* against that decision -- what's actually built, what's tested,
and where the real gaps are.

## 1. What exists and its classification

| Component | Classification | Evidence |
|---|---|---|
| `common/AudioTooRealtimeCore.h` | **Working, tested (ThreadSanitizer)** | See Section 2 |
| `plugins/kenn-vst3-au/Source/PluginProcessor.{h,cpp}` | **Working, integration-tested** | See Section 3 |
| `plugins/kenn-vst3-au/Source/PluginEditor.{h,cpp}` | **Working, not independently tested** | UI glue; exercised transitively by building, not unit-tested |
| `plugins/kenn-vst3-au/Source/MeterAnalyzer.h` (`KENNMeterAnalyzer` class) | **Dead code** | Never instantiated anywhere -- superseded by `AudioTooRealtimeCore`, only its `KENNMeterSnapshot` struct is still used |
| `plugins/kenn-vst3-au/Source/test_realtime_thread_safety_main.cpp` | **Working, tool-verified** | Ran this session, plain and under TSan |
| `plugins/kenn-vst3-au/Source/test_server_integration_main.cpp` | **Working, live-verified** (new this session) | See Section 3 |
| `plugins/kenn-vst3-au/CMakeLists.txt` | **Working, builds clean** | Both VST3 and AU, Xcode Command Line Tools only |
| Versioned evidence payload shared with offline Mix Review | **Implemented (2026-09-11)** | `common/kenn_evidence_v1.schema.json`; emitted by native handoff and offline Mix Review |

## 2. `AudioTooRealtimeCore` -- the real-time analysis core

Read in full this session (not just referenced). It computes, per audio
block, in `analyse()`: peak (with decay), RMS/energy, L/R correlation,
mid/side stereo width, three-band energy split (low/mid/high via two
one-pole filters), crest factor (derived at snapshot time from peak/RMS),
a transient ratio (mono sample-to-sample difference energy relative to
RMS), and a naive full-scale clip counter (`>= 0.999` on either channel).

**Real-time safety, verified not just asserted:**
- No allocation in `analyse()` -- confirmed by reading the loop; only
  stack scalars and pre-sized buffer reads.
- No locks -- state is `std::atomic<float>`/`std::atomic<double>`/
  `std::atomic<int64>`, written by `analyse()` (audio thread) and read by
  `snapshot()` (UI timer thread / JSON handoff builder), a standard
  single-producer/multi-consumer lock-free pattern.
- No I/O, no logging, no network, no Python calls in the audio path --
  confirmed by reading every line of `analyse()`.
- **Tool-verified concurrency correctness**: this session ran the
  existing (previously never-executed) `TestRealtimeThreadSafety` --
  1 writer thread continuously calling `analyse()` + 3 reader threads
  continuously calling `snapshot()`, across 5 sample rates (44.1kHz-192kHz),
  checking every read for NaN/Inf as a proxy for torn reads. Clean pass.
  Re-ran under `-fsanitize=thread` (real ThreadSanitizer instrumentation,
  not a synonym for "ran without crashing") -- clean, no TSan report. This
  is the strongest evidence standard the mission asks for
  ("sanitizer coverage") and it now exists and passes.

**Known limitation, not a defect**: `snapshot()` reads 7 independent
atomics non-atomically as a group. A reader can observe peak from one
audio block and correlation from a slightly later one (benign tearing,
not corruption -- each individual field is a valid, complete value, just
not necessarily all from the same block). Fine for a VU-meter-style
display; would matter if a future consumer needed frame-exact correlated
readings.

**Not yet done**: no numerical-accuracy tests against a reference
implementation (e.g. compare crest factor against a known-good Python/
NumPy computation on the same signal) -- the concurrency test proves
thread safety, not correctness of the numbers themselves. This is the
"numerical tests... reference parity" bar the mission sets, and it isn't
met yet.

## 3. Plugin processor -- network integration, not just UI glue

`PluginProcessor.cpp`'s `askKenn()`, `testKennConnection()`,
`sendHandoffToKenn()`, `requestSafeTargetProposal()`, `startAutoMix()`,
`fetchAutoMixStatus()` are real HTTP client code (JUCE's `URL`/
`InputStreamOptions`), not stubs. All network calls happen off the audio
thread -- confirmed: `PluginEditor.cpp`'s button handlers wrap every one
of these in `juce::Thread::launch(...)`, with results marshaled back via
`juce::MessageManager::callAsync`. This matches the mission's real-time
rule ("the audio thread must never perform network calls") by
construction, not by convention -- there is no code path from
`processBlock()` to any network call.

**This session's new evidence**: `test_server_integration_main.cpp`
constructs the actual compiled `KENNMixAssistantAudioProcessor` -- the
same class `createPluginFilter()` hands to a DAW -- and calls its real
`testKennConnection()`/`askKenn()` against a live `apps/backend/src/kenn/server.py`.
Live result: health check succeeded, and a real mix-engineering question
returned a genuine, cited 1557-character diagnostic answer through the
compiled binary. This is meaningfully stronger evidence than "the code
compiles" or "the source looks correct" -- it's proof the actual shipped
artifact works against the actual current backend contract.

**Build note**: `TestServerIntegration` links against the already-compiled
`KENNMixAssistant` shared-code library rather than recompiling
`PluginProcessor.cpp` in a plain `add_executable` -- `juce_add_plugin()`
injects `JucePlugin_*` macros (name, manufacturer, bundle ID, etc.) only
for its own target, so a naive second compilation of the same source
would fail to define those macros. Worth knowing before adding more
native test targets: link against `KENNMixAssistant`, don't recompile its
sources.

## 4. Shared, versioned evidence schema (resolved 2026-09-11)

The mission's architecture goal is explicit: *"The C++ core should
produce a versioned, language-neutral evidence payload usable by both the
VST3 plugin and offline Mix Review."* The former gap is now closed at the
interchange boundary, while the underlying realtime and offline calculations
remain deliberately separate:

- The native handoff retains its existing `kenn.plugin_handoff.v1` and
  `audio_feature_frame.v1` fields, and now includes a nested
  `kenn.evidence.v1` packet containing common scalar facts and units.
- Offline Mix Review emits the same `kenn.evidence.v1` packet alongside its
  richer fault-family report. Fields not calculated by a runtime are absent;
  no synthetic equivalence is claimed.
- Live context summaries rebuild the packet with host-computed freshness, so
  downstream consumers can use one parser while still distinguishing a
  current plugin-bus observation from an immutable uploaded render.

The implementations remain intentionally independent because the plugin must
stay realtime-safe while offline Mix Review can use richer batch analysis.
The shared contract is a field-naming/units boundary, not a rewrite of either
calculation. The JSON Schema is documentation and an interchange reference;
the existing host validators remain the runtime safety boundary.

## 5. Measured performance envelope (2026-09-11)

The existing native micro-benchmark ran 50,000 stereo blocks at 48 kHz for
each buffer size. `AudioTooRealtimeCore::analyse()` used **0.111–0.124%** of
the available realtime budget, with **23.05–25.75 ns/sample** and no failed
buffer size; the maximum observed process RSS was **8.25 MB**. The result is
an isolated steady-state measurement of the audio-rate core, not a whole-DAW
CPU claim.

The actual offline Mix Review engine was measured on a generated 5-second,
48 kHz mono PCM WAV for three runs: mean **31.983 ms**, maximum **34.325 ms**.
The process maximum RSS was **127.94 MB**, including Python and optional
metering-library startup; it is not a per-request allocation figure. The
benchmark retained no audio and makes no perceptual-quality claim.

The existing bounded audio-analysis benchmark also completed successfully on
5-second/48 kHz and 2-second/96 kHz fixtures (**290.984 ms** and **263.308
ms**, respectively; two-worker concurrency **571.557 ms**). These numbers are
recorded as adapter evidence, not as a replacement for real-mix profiling.

## 6. CMake and build hygiene

- Builds clean with only Xcode Command Line Tools -- no full Xcode
  required despite `plugins/kenn-vst3-au/README.md`'s caveat that AU needs it (both
  formats built successfully this session).
- `CMP0175` dev-mode warnings appear during configure (from JUCE's own
  `JUCEUtils.cmake`, not this repo's code) -- cosmetic, not a defect;
  suppressible with `-Wno-dev` if the noise is undesired, otherwise safe
  to ignore.
- `KENN_ENABLE_TSAN` is a real, working, documented option -- this
  session is the first time it was actually exercised.
- No CI/automated build verification exists for this plugin -- every
  build and test this session was run manually and interactively. If the
  team wants ongoing confidence, wiring a CI job (even just "configure +
  build + run `TestRealtimeThreadSafety`") is the highest-leverage next
  step, since this is exactly the kind of regression (a build silently
  breaking) that goes unnoticed without one.

## 7. Verdict against the mission's C++ readiness bar

The mission states: *"C++ work is beta-ready only when it has measured
benefit, numerical tests, regression tests, sanitizer coverage, reference
parity, documented CPU/latency/memory behaviour, rollback, and no
dependency on the old estate."* Scored against that bar:

| Requirement | Status |
|---|---|
| No dependency on the old estate | **Met** -- architecturally independent, verified by a clean build with the old estate absent from the lookup path |
| Sanitizer coverage | **Met** -- ThreadSanitizer run this session, clean |
| Regression tests | **Met** -- `TestRealtimeThreadSafety`, `TestServerIntegration`, and `TestNumericalParity` built and passing |
| Numerical tests / reference parity | **Met** -- `TestNumericalParity` verifies peak (0.00 dBFS), RMS (-3.0104 dBFS), crest factor (3.0104 dB), correlation (1.0), and clip count (10) against reference sine and DC signals |
| Measured benefit (CPU/latency/memory) | **Met for bounded benchmarks** -- native realtime core and offline Mix Review have measured latency, CPU envelope, and process RSS; see Section 5 |
| Rollback | **Met by construction** -- the plugin is a side-loaded native bundle; removing the installed `.vst3`/`.component` fully reverts it, no other system state depends on it |


**Net**: the real-time core and plugin-to-server integration are
genuinely solid and now have real evidence behind them, well beyond where
they stood at the start of this session (never built, never tested). What
remains before this is fully "beta-ready" by the mission's own bar is
continued real-session validation and release engineering; the native
numerical, safety, concurrency, and bounded performance evidence is now
present.
