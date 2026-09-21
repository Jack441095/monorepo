# C++ shared-runtime architecture

## Decision

Do not build a monolithic “KENN C++ runtime,” and do not extract speculative `nite_*` shared libraries in this pass. Continue hardening the measured KENN-owned native analysis library. Consider a small versioned cross-product DSP library only after AudioGen and SLO owners demonstrate function-level duplication, compatible semantics and independent benchmark value. Keep orchestration, Live safety policy, retrieval, user memory and external product integrations outside it.

## Evidence and extraction decision

| Proposed component | Evidence found | Compatibility problem | Decision |
|---|---|---|---|
| `nite_dsp_core` | KENN has measured FFT/spectral/masking/loudness kernels; the adjacent SLO checkout has C++ source; AudioGen producer code is outside canonical KENN | No frozen cross-product numerical contract or same-input output comparison was available; plugin callback constraints differ from offline analysis | **Defer extraction.** First inventory duplicated functions and run golden cross-product parity/benchmarks |
| `nite_midi_core` | KENN has multiple Python MIDI validation/artifact paths and one validation defect was fixed | No measured CPU/GIL/copy bottleneck and no proven identical AudioGen consumer contract | **Keep Python now.** Consolidate one canonical validator before considering native code |
| `nite_runtime_core` | KENN needs bounded workers/cancellation; plugin needs SPSC/atomics | SLO, AudioGen, server workers and plugin callback have different lifecycle/failure semantics | **Reject shared runtime now.** Use product-local primitives until two consumers prove the same contract |

The adjacent checkout remained read-only, so no ownership transfer or shared-library change is implied by this design.

```text
Vue client / JUCE UI
        |
local API + typed command/proposal service (Python)
        |                    |                         |
Live adapter/OSC       analysis workers        AudioGen/SLO adapters
(read/confirm/write)          |                 (versioned manifests)
                              v
                   kenn-owned libkenn_analysis (C++20)
                   - decode/normalise adapter
                   - FFT/spectral/masking
                   - loudness/stereo/bulk metrics
                   - stable C ABI + nanobind wrapper

JUCE processBlock -> realtime-only kenn_dsp kernels
                    (no Python, JSON, network, allocation or locks)
```

## Components and ownership

`libkenn_analysis` is the conditional target for the existing KENN-owned native code. It owns pure transformations over explicit buffers and immutable configuration. It returns versioned result structs with status/error codes. A stable C ABI isolates language bindings from C++ ABI changes; nanobind owns Python conversion. The offline worker owns decoding, cancellation, deadlines and process isolation. Cross-product consumers are not added until the extraction gates below pass.

Extraction gates: two real owners, a named maintainer, identical versioned input/output semantics, golden corpus parity, at least 20% complete-request benefit or substantial reliability simplification for each consumer, independent packaging/version compatibility, and a rollback/fallback plan. Until then, duplication is cheaper than premature ABI coupling.

`kenn_dsp` contains only callback-safe primitives needed by the plugin. Code sharing with `libkenn_analysis` is allowed only for allocation-free kernels with explicit scratch storage and bounded behavior. It must not link the Python runtime.

The Python application remains authoritative for proposal policy, confirmation expiry, state preconditions, Live readback, receipts, undo identity, retrieval, preference rules and integration contracts. AudioGen remains the producer of bounded generated artifacts; SLO remains the owner of library intelligence. KENN consumes both through schemas rather than source-code coupling.

## API sketch

```c
typedef struct kenn_audio_view_v1 {
  const float *interleaved;
  uint64_t frames;
  uint32_t channels;
  uint32_t sample_rate;
} kenn_audio_view_v1;

typedef struct kenn_analysis_config_v1 {
  uint32_t struct_size;
  uint64_t requested_metrics;
  uint32_t fft_size;
} kenn_analysis_config_v1;

kenn_status_v1 kenn_analyse_v1(
    const kenn_audio_view_v1 *input,
    const kenn_analysis_config_v1 *config,
    kenn_analysis_result_v1 *output,
    kenn_scratch_v1 *scratch);
```

The caller owns input lifetime; library-owned output uses an explicit destroy function or caller-provided storage. Every struct carries a version/size. No exceptions cross the C ABI. Python inputs must be contiguous float32 or take an explicit, diagnosed conversion path. Cancellation is cooperative between bounded stages, never through signal-unsafe interruption.

## Concurrency and failure containment

- Offline analysis runs in a bounded process pool so native crashes, corrupt media and model memory do not take down the command/safety service.
- The plugin uses atomics or a bounded SPSC queue for control changes and publishes immutable meter snapshots back to the UI.
- Every call has byte/frame ceilings, time budgets and structured errors. Native unavailable/unsupported falls back to reference Python only where parity is guaranteed.
- Model inference, if adopted, is a separate worker with provider selection and CPU fallback visible in the receipt.
- Live actions remain serialized by project/session and proposal identity; analysis completion can recommend but cannot mutate Live.

## Build and qualification profiles

| Profile | Purpose | Required properties |
|---|---|---|
| `dev-arm64` | Fast local iteration | Debug symbols, tests, optional ccache |
| `release-arm64` | Python/native product path | `-O3`, explicit deployment target, LTO only after benchmark |
| `release-universal-plugin` | AU/VST3 delivery | arm64+x86_64, host validation, signed/notarized in release pipeline |
| `asan-ubsan` | Memory/UB qualification | Representative corpus and malformed-input tests |
| `tsan` | Concurrency qualification | Plugin control/audio exchange and worker queues |

## Observability contract

Receipts record implementation (`python-reference`, `cpp-accelerate`, future provider), build ID, input hash, elapsed stages, copies/conversions, peak memory where measured, result schema and fallback reason. They never imply a Live state change without post-write readback.
