# C++ platform and library research

Audit date: 2026-09-21. Target host: Apple Silicon/macOS. This document records suitability; it is not evidence that a dependency is shipped by KENN.

## Recommended platform choices

| Need | Candidate | Fit for KENN | Decision and boundary |
|---|---|---|---|
| FFT/vector DSP | Apple Accelerate/vDSP | Native Apple implementation, already exercised by the current optional backend | Use on Apple platforms behind the existing numerical contract; retain a portable implementation and golden parity tests |
| Python/C++ boundary | nanobind | Existing binding layer, ndarray support, low-friction NumPy interop and explicit GIL controls | Keep for offline/batch DSP. Never call Python or acquire the GIL from an audio callback |
| Plugin framework | JUCE | Existing VST3/AU implementation and state/parameter machinery | Keep. Treat parameter state exposed to the processor as realtime data; do not mutate trees, allocate, lock or perform I/O in `processBlock` |
| Model inference | ONNX Runtime C/C++ plus CoreML EP | Viable for portable local inference with Apple acceleration | Research/prototype only until a frozen model, operator coverage, fallback behavior, numerical tolerance, latency and license/package plan are qualified |
| Cross-platform build | CMake presets and target properties | Already used; can make architectures and options explicit | Add checked-in presets for arm64 developer, universal Release and sanitizer builds. Avoid global architecture flags where target-local configuration is possible |
| Compiler cache | ccache | Useful for repeat native builds and CI | Optional developer/CI accelerator; never a correctness dependency |
| Dynamic analysis | Clang ASan, UBSan, TSan | Appropriate complementary checks for memory, undefined behavior and races | Create separate configurations. Do not combine TSan with ASan; do not interpret sanitizer-clean as realtime-safe |
| Interchange/data | Typed JSON at process boundaries; plain C++ structs internally | Current contracts are inspectable and versioned | Keep JSON off the audio thread. Consider FlatBuffers/Cap'n Proto only after profiling demonstrates serialization is material |
| Accelerated ML alternative | Direct Core ML | Strong Apple deployment option | Prefer through ONNX Runtime first for portability; choose direct Core ML only if profiling or unsupported operators justify an Apple-specific adapter |

## Technology decision ledger

| Technology | Problem / applicability | Compatibility and realtime status | Performance evidence or potential | Risk / license | Decision |
|---|---|---|---|---|---|
| C++20, selective C++23 | RAII, spans, atomics, jthreads/stop tokens and stronger types for native kernels/workers | Current AppleClang build already accepts C++20; verify each C++23 feature in the deployment compiler | Correctness and lifecycle benefit; no speed claim by itself | Standard/toolchain evolution | **Adopt C++20; trial individual C++23 features** |
| JUCE | AU/VST3 hosting surface, parameters and UI/audio separation | Already builds universal; callback-safe design still requires KENN discipline | Existing kernel deadline fractions are low; full callback unmeasured | Commercial or AGPL licensing must be resolved | **Adopt/retain** |
| Live Object Model / Max for Live | Supported object graph and observation/control surface inside Live | Operations are constrained to exposed LOM properties/functions; not an audio-thread API | Reliability/identity value, not a CPU optimization | Ableton/Max platform dependency | **Adopt as semantic reference; retain external adapter** |
| AbletonOSC | Current external Live bridge | Reachable only when its remote script is installed/running; offline in this audit | Round-trip unmeasured | Community component and Python remote-script lifecycle | **Retain short term; qualify, correlate and bound** |
| Accelerate/vDSP | FFT, vector maths and convolution on Apple | Apple-only, callback-compatible when plans/scratch are prepared outside callback | Fresh native analysis 10.04x synthetic and 57.35x real-stem p50 | Platform lock-in; Apple SDK terms | **Adopt behind portable contract** |
| Accelerate BLAS | Dense linear algebra | Apple-only backend; useful only for a real matrix-heavy workload | No current KENN hotspot supports adoption | Oversubscription and layout costs | **Defer** |
| ARM NEON/ACLE intrinsics | Hand-vectorize kernels not covered by vDSP | ARM64-specific and easy to over-specialize | No residual hotspot measured after Accelerate | Maintenance/portability cost | **Defer** |
| Compiler auto-vectorization | Portable optimized loops | Compatible with C++20; callback-safe for pure preallocated loops | Low-cost first step on portable fallback | Performance varies by compiler | **Adopt with benchmark and vectorization reports** |
| `std::simd` / experimental SIMD | Portable explicit data parallelism | Standard facility is C++26; experimental availability is inconsistent with current Apple deployment | Potential portable fallback speed | ABI/toolchain maturity | **Defer; do not depend on the TS** |
| Google Highway / xsimd | Maintained portable SIMD abstraction | Additional dependency; suitable for pure kernels | Trial only if portable fallback becomes dominant | Apache-2.0 / BSD-3-Clause; dependency cost | **Defer pending cross-platform profile** |
| ONNX Runtime C/C++ | Stable local model execution API | macOS/CPU supported; model/operator set must be frozen | Could reduce Python/provider overhead; unmeasured | MIT; binary size and provider/version matrix | **Trial in isolated worker** |
| ONNX Runtime CoreML EP | Apple Neural Engine/GPU/CPU provider | Apple-only provider with shape/operator constraints | Potential embedding/inference gain; unmeasured | Provider variance and conversion/fallback behavior | **Trial after model freeze** |
| nanobind | Existing CPython binding and NumPy ndarray boundary | Already integrated; GIL can be released; never usable from audio callback | Current native path reports `native_input_copied=false` | BSD-3-Clause; Python ABI wheels required | **Adopt/retain** |
| pybind11 | Alternative mature binding layer | Broad compatibility, but parallel binding frameworks duplicate packaging | No measured reason to replace nanobind | BSD-style license; migration cost | **Reject replacement** |
| CPython limited ABI | Reduce wheel matrix | Native NumPy/ndarray constraints may prevent practical `abi3` use | Distribution benefit, not runtime speed | Compatibility investigation needed | **Research only** |
| Python buffer protocol / NumPy views | Avoid PCM copies at language boundary | Safe only with dtype, contiguity, alignment, mutability and lifetime checks | Material for long buffers; current input-copy diagnostic is promising | Dangling/lifetime hazards | **Adopt explicit view-or-copy contract** |
| GIL release | Permit independent native work to run concurrently | Safe only while native code touches no Python objects | Fresh four-worker path improved 15.73x vs reference | Race/lifetime bugs | **Adopt for substantial pure native calls** |
| `std::jthread` / stop token | Explicit lifecycle and cooperative cancellation | Background workers only, never callback work | Reliability, not direct speed | Cancellation points must be designed | **Trial for native worker layer** |
| SPSC queue / atomics | Bounded plugin UI/control-to-audio exchange | Realtime-suitable if fixed-capacity and wait-free for used operations | Removes locks/deadline variance | Memory-ordering complexity | **Adopt only with TSan/stress proof** |
| Preallocation / arenas | Remove callback allocation and stabilize workers | Essential for audio callback; useful for repeated FFT scratch | Deadline/determinism benefit | Sizing and fragmentation trade-offs | **Adopt for realtime; trial for workers** |
| libsndfile | Broad audio decode | Cross-platform; keep outside callback | May replace fragile custom format handling; not benchmarked here | LGPL-2.1; distribution obligations | **Trial against current decoder corpus** |
| libsamplerate / r8brain alternatives | High-quality sample-rate conversion | Offline/worker unless a bounded configuration is proven | No current end-to-end profile | BSD-2-Clause or library-specific terms | **Defer until resampling is measured** |
| libebur128 | EBU R128 implementation | Cross-platform, preallocation possible | Could simplify loudness code; full Mix Review gain is only 1.13x | MIT; semantic parity required | **Trial only as correctness simplifier** |
| CMake presets + Ninja | Reproducible build matrix and fast incremental builds | Cross-platform and compatible with current build | Build-time benefit | Configuration maintenance | **Adopt** |
| ccache | Compiler result cache | Developer/CI only | Expected repeat-build improvement; not measured | GPL-3.0 tool, no runtime linkage | **Trial in CI** |
| IPO/LTO | Whole-program optimization | Release only; verify plugin and extension linkers | Unknown until benchmarked | Longer builds/debug complexity | **Trial, retain only with complete-request gain** |
| ASan / UBSan / TSan | Detect memory, UB and races | Separate builds; TSan overhead is not performance evidence | Reliability value | False negatives and dependency incompatibilities | **Adopt as promotion gates** |
| Universal binaries | AU/VST3 arm64+x86_64 delivery | Current plugin artifacts are universal; Python extension is arm64 | Distribution requirement | Signing and doubled link complexity | **Adopt for plugin; per-arch Python wheels** |
| Instruments + `os_signpost` | Time, allocation and contention attribution | Apple-only profiling; avoid unbounded callback logging | Needed for full-request/callback proof | Diagnostic overhead/privacy | **Adopt in qualification builds** |

Maintained libraries should replace custom code only when their semantics, license, corpus behavior and complete-request result beat the current implementation. No new SIMD, decode or serialization dependency is approved solely from a microbenchmark.

## Realtime constraints

The audio callback must have bounded execution and use preallocated memory. It must not perform heap allocation, file/network I/O, JSON work, Python calls, mutex acquisition, model loading or Live/OSC requests. UI/control-thread state reaches DSP through atomics, lock-free single-producer/single-consumer queues, or immutable snapshots exchanged outside the callback. Large analysis and ML work belongs in a worker process or bounded worker pool.

The existing plugin performance test is useful kernel evidence, not a proof of the full callback. A release gate needs full `processBlock` tests across sample rates, buffer sizes, channel layouts and automation density, with missed-deadline counters and a TSan build for control/audio-thread exchange.

## ABI, packaging and fallback policy

- Build Python extensions for each supported Python ABI and macOS deployment target; do not rely on a locally copied `.so`.
- Publish an arm64 artifact first and a universal plugin where required. Validate `CMAKE_OSX_ARCHITECTURES` before the first configure because the property is initialized at target creation.
- Keep native features capability-probed and fail to the tested Python/reference path with a structured diagnostic.
- Pin dependency versions and preserve their license notices. The observed nanobind, ONNX Runtime and pybind11 upstream licenses are permissive; JUCE's commercial/GPL terms require a product-specific licensing review before distribution.
- Produce SBOM, hashes and reproducible build metadata for released native artifacts.

## Research sources

Primary references used in this review: Apple Accelerate/vDSP (https://developer.apple.com/documentation/accelerate), Apple unified logging/signposts (https://developer.apple.com/documentation/os/logging/generating_log_messages_from_your_code), JUCE parameter state (https://docs.juce.com/master/classjuce_1_1AudioProcessorValueTreeState.html), Ableton Max for Live control (https://help.ableton.com/hc/en-us/articles/5402681764242-Controlling-Live-using-Max-for-Live), the Live Object Model (https://docs.cycling74.com/legacy/max8/vignettes/live_object_model), nanobind ndarray/GIL documentation, pybind11 GIL documentation, ONNX Runtime C/C++ and CoreML EP documentation, CMake architecture/IPO properties, and Clang sanitizer documentation. Reproducible URLs are also listed in `CPP_MIGRATION_OPPORTUNITY_MATRIX.md`.
