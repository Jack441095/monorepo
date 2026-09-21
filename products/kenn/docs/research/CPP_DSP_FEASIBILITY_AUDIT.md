# KENN C++ DSP Feasibility Audit

**Audit date:** 2026-09-20
**Decision:** **Conditional go** for a small shared native DSP core; **no-go** for a broad KENN rewrite.
**Scope:** the active `products/kenn` boundary, the 2026-09-20 pre-monorepo archive, and the preserved audio-analysis implementation in `monorepo-collab`.

## Executive summary

KENN should remain a hybrid product. C++ is already the correct language for its
DAW audio callback and has proven useful for a few long-running offline DSP
kernels. Python remains the correct owner for orchestration, retrieval, policy,
evaluation, receipts, and product workflow.

The three strongest opportunities are:

1. **Restore and preserve the existing C++20/JUCE realtime feature core.** The
   archived `AudioTooRealtimeCore` processed the tested buffer sizes in
   0.041-0.071% of their realtime budget on this machine. This is already fast;
   the value is deterministic realtime behaviour and reuse, not a promised new
   speed-up.
2. **Prototype one native offline spectral-analysis slice.** The preserved
   KENN-owned WAV analyzer decodes samples into Python lists and runs a
   hand-written radix-2 FFT in Python. That is a credible bottleneck candidate.
   Replace only the decode/window/FFT/band-reduction hot path, preferably with
   Accelerate/vDSP on macOS and a portable backend elsewhere, while preserving
   the Python result and evidence contracts.
3. **Recover the previously measured AutoMix native kernels before inventing
   new ones.** Historical, repository-local measurements report an end-to-end
   reduction from 50.8 s to 22.6 s on a 15-stem project after a combined
   algorithmic/vectorization/native pass. The same report also shows several
   C++ ports at only 1.0-1.5x and one C++ phase-correlation port at 0.2x. This is
   strong evidence for profile-guided kernels, not for language-led migration.

The safest integration is a pure C++20 `kenn_dsp_core` static library linked
directly into the JUCE plugin, plus a thin nanobind extension for offline Python
arrays. Python must keep the existing reference implementation and select the
native path behind a feature flag until parity and performance gates pass.

The first experiment should be the preserved KENN WAV analyzer's
decode/window/FFT/band-reduction stage. Proceed only if a release build is at
least **3x faster for that stage** and improves the complete analysis request by
at least **25%**, with numerical and receipt parity.

## Evidence status

This audit distinguishes four evidence classes:

- **Current repository fact:** observed directly under active
  `products/kenn` on 2026-09-20.
- **Current measurement:** executed during this audit on the current machine.
- **Preserved-source fact:** observed in the pre-monorepo archive or
  `monorepo-collab`; it is not assumed to be active.
- **Historical measurement:** documented in repository reports but not rerun
  end to end during this audit.

## Current architecture and source-integrity finding

The active product README describes `products/kenn` as a product boundary over
the former `Audio_Too` implementation. The boundary is currently incomplete:

- `products/kenn/source` points to `../../Audio_Too/studio/kenn`;
- `products/kenn/vst3-plugin` points to
  `../../Audio_Too/studio/vst3_plugins/KENNMixAssistant`;
- those target directories do not exist in the active monorepo;
- `products/kenn/tooling/scripts/benchmark_audio_analysis.py` imports
  `kenn.core.audio_analysis`, which is absent from the active backend;
- running that benchmark currently fails with
  `ModuleNotFoundError: No module named 'kenn.core.audio_analysis'`;
- active `products/kenn/apps/backend/src/kenn` contains retrieval source, but
  not the broader backend/DSP source referenced by tooling and older docs;
- complete product and plugin sources remain available in
  `archive/kenn-pre-monorepo-2026-09-20`, `handoff/kenn-full-product-slo`, and
  `monorepo-collab`.

Therefore the first engineering action is to finish or roll back the source
migration and establish a canonical path. Adding another C++ implementation to
the current split layout would increase risk and make benchmarks ambiguous.

### End-to-end workload map

| Workflow | Current/preserved implementation | Cost and boundary |
| --- | --- | --- |
| Live DAW metering | Preserved C++20/JUCE plugin -> `AudioTooRealtimeCore::analyse()` -> atomics -> UI/worker snapshot | Hard realtime; no Python, I/O, locks, or allocation in the callback |
| Plugin handoff | C++ worker/UI thread -> JSON/HTTP -> local Python companion | Non-realtime; feature-only payload, no raw audio |
| Qualified Mix Review | Local path -> decoder from former Audio_Too -> NumPy array -> three frozen detectors -> Python receipt | Offline; active adapter currently cannot import the missing decoder tree |
| KENN bounded WAV analysis | Preserved Python byte parser -> Python lists -> hand-written FFT -> bands/peaks -> JSON | Offline; strongest isolated native POC candidate |
| AutoMix | Preserved Python/NumPy/SciPy orchestration -> optional C++ kernels -> render/validate/export | Offline and batch; profile by stage and stem count |
| Retrieval/chat | Python BM25/NumPy/ONNX runtime -> reasoning/reporting | Not DSP; custom C++ is low value |
| Model inference | Existing native-backed runtime where configured | Optimize configuration/model first; do not write a custom inference engine |

## Measurements made during this audit

Machine: Apple M3, 16 GiB, arm64, macOS 27.0; Python 3.13.7; NumPy 2.3.3
using Accelerate; Clang 15 as reported by NumPy.

### Active qualified detector path

`evaluate_qualified_families()` was benchmarked directly on deterministic
synthetic float32 stereo arrays. Decode, hashing, and receipt serialization were
excluded.

| Audio duration | Runs | p50 | p95 | p50 realtime factor |
| ---: | ---: | ---: | ---: | ---: |
| 1 s | 50 | 0.355 ms | 0.387 ms | 0.000355 |
| 10 s | 30 | 2.883 ms | 2.935 ms | 0.000288 |
| 60 s | 12 | 17.735 ms | 18.290 ms | 0.000296 |
| 180 s | 5 | 54.771 ms | 54.846 ms | 0.000304 |

**Finding:** porting these three detectors to C++ is not justified. The complete
three-minute detector stage takes about 55 ms. Optimize decoding/copies first if
the complete request is slow.

### Preserved realtime core

The archived, already-built binaries were rerun during this audit:

- numerical parity: passed for peak, RMS, crest, correlation, spectrum frame,
  and clipping count;
- concurrent writer/readers: passed at 44.1, 48, 88.2, 96, and 192 kHz with no
  NaN/Inf reads;
- 50,000 blocks at 48 kHz: 8.637-14.788 ns/sample and 0.041-0.071% of realtime
  budget across 64-1024-sample buffers.

These are measurements of a preserved archived binary, not proof that the
active product currently builds it.

### Historical AutoMix evidence

`Audio_Too/docs/audits/2026-07-30-automix-cpp-kernel-and-vectorization-pass.md`
reports:

- `dream_of_you`, 15 stems: 50.8 s -> 22.6 s (-55%);
- relationship inference: 7.92 s -> 2.65 s (-66%) by replacing a per-bin
  Python loop with vectorized `np.bincount`;
- dynamics analysis: 16.7 s -> 4.2 s (-75%) from a native rolling threshold
  kernel plus a batched FFT;
- most individual native kernels: 1.0-1.55x over Numba/SciPy;
- direct C++ phase correlation: 0.20x because it changed from O(N log N) to
  O(N*max_lag).

These measurements are credible leads, not a current baseline. Reproduce them
after canonical source restoration.

## Ranked migration candidates

| Rank | Candidate | Evidence | Expected hypothesis | Decision |
| ---: | --- | --- | --- | --- |
| 1 | Restore/link shared realtime feature core | Rerun preserved binary is far below budget | Same feature set stays below 0.5% callback budget at 32-2048 samples and 44.1-192 kHz | Go after source restoration |
| 2 | Offline WAV decode + window + FFT + band reductions | Preserved code uses Python lists and hand-written FFT | >=3x hot-stage and >=25% request speed-up, lower peak RSS | POC |
| 3 | Recover proven AutoMix limiter/envelope/transient kernels | Historical measured whole-pipeline benefit | Recovered release path retains parity and >=10% whole-project gain | Conditional go |
| 4 | Shared feature cache and single-pass reductions | Repeated passes/copies identified in preserved architecture | Reduce complete analysis time/RSS more than a language-only port | Do before further ports |
| 5 | Resampling backend | Current preserved path uses SciPy C-level `resample_poly` | A new backend may improve throughput, but only after benchmark and quality tests | Benchmark only |
| 6 | Qualified detector rewrite | Current measurement: 54.8 ms for 180 s audio | Negligible product benefit | No-go |
| 7 | Retrieval, orchestration, receipt generation | Control-flow/text workload | Native boundary overhead and maintenance dominate | No-go |
| 8 | Custom FFTW integration | GPL/commercial licensing and existing platform alternatives | Possible speed, higher distribution risk | Avoid by default |

## What should remain in Python

- chat, retrieval, citations, and evidence rendering;
- orchestration, policy, confirmation, and rollback decisions;
- evaluation, qualification, corpus tools, and benchmarks;
- HTTP endpoints, persistence, job lifecycle, and support receipts;
- experimental detectors until their numerical contract is frozen;
- the reference implementation used for native parity testing.

NumPy, SciPy, and ONNX Runtime already execute substantial work in optimized
native code. Rewriting their Python call sites in C++ is unlikely to help unless
profiling shows Python iteration, repeated calls, or avoidable memory movement.

## Correctness and realtime risks

1. The preserved plugin handoff labels sample peak as `true_peak_dbtp` and RMS
   as `integrated_lufs`. Those metrics are not equivalent. A shared C++ core
   must use explicit measurement names and must not preserve this semantic
   shortcut in a new contract.
2. Independent atomics give valid individual values but not an atomic coherent
   frame. Fine for meters; use a bounded sequence-stamped snapshot if a future
   decision requires fields from exactly the same block.
3. FFT plans, windows, filter coefficients, and scratch buffers must be created
   outside `processBlock()` and reused.
4. No exception, allocation, logging, filesystem, model, JSON, network, or
   blocking lock may enter the callback.
5. Numerical parity alone is insufficient. Spectral leakage, true peak,
   loudness, resampling alias rejection, denormals, NaNs, channel layouts, and
   long-stream state require dedicated fixtures.

## Dependency and licence assessment

This is an engineering assessment, not legal advice.

- **JUCE:** already used by the preserved plugin. Current official JUCE licence
  tiers depend on revenue/funding; confirm the applicable licence before
  distribution. Keep JUCE at the plugin boundary rather than making the offline
  core depend on it.
- **Apple Accelerate/vDSP:** excellent macOS FFT/vector backend and ships with
  the platform; not portable to Windows.
- **JUCE FFT:** portable and easy but JUCE's own documentation says it is a
  simple low-footprint implementation not tuned for speed. Benchmark it; do not
  assume it is the fastest backend.
- **nanobind:** BSD-3-Clause and suitable for a small NumPy-array boundary.
- **pybind11:** BSD-style and mature; acceptable alternative, with a somewhat
  larger binding surface. Pick one, not both.
- **FFTW:** GPL by default or separately commercially licensed. Do not place it
  in a proprietary build without an owner-approved licence decision.
- **libsamplerate:** BSD-2-Clause and portable; viable for a benchmark.
- **libsoxr:** LGPL-2.1 and can introduce meaningful latency in high-quality
  realtime modes; viable primarily for offline evaluation after legal review.
- **ONNX Runtime:** MIT-licensed core; retain it for model inference rather than
  creating a KENN inference runtime.

## External sources

Accessed 2026-09-20:

- Apple, [vDSP overview](https://developer.apple.com/documentation/accelerate/vdsp-library)
- Apple, [vDSP FFT](https://developer.apple.com/documentation/accelerate/vdsp/fft)
- JUCE, [juce::dsp::FFT](https://docs.juce.com/master/classjuce_1_1dsp_1_1FFT.html)
- JUCE, [JUCE 8 licence](https://juce.com/legal/juce-8-licence/)
- nanobind, [official repository and licence](https://github.com/wjakob/nanobind)
- pybind11, [official documentation](https://pybind11.readthedocs.io/en/stable/)
- FFTW, [official project and licensing](https://www.fftw.org/)
- libsamplerate, [official repository](https://github.com/libsndfile/libsamplerate)
- libsoxr, [official repository](https://github.com/chirlu/soxr)
- ONNX Runtime, [official repository](https://github.com/microsoft/onnxruntime)

## Final recommendation

**Conditional go.** First restore a single canonical KENN source tree and make
the existing benchmark/build paths runnable. Then prototype one offline native
spectral slice behind a feature flag. Do not rewrite KENN, do not port the
already-fast qualified detectors, and do not claim a speed-up until a complete
request benchmark demonstrates it.
