# KENN C++ DSP Phase 1 Profile Receipt

**Run date:** 2026-09-20
**Source revision:** `ffea0c7c970172dd6bf2afd78142f475c41198e4`
**Machine:** macOS 27 / Apple arm64 / Python 3.13.7 / 8 CPUs

## Baseline artifacts

- [audio-analysis benchmark JSON](results/phase1_audio_analysis_benchmark.json)
- [audio-analysis cProfile JSON](results/phase1_audio_analysis_profile.json)
- [Mix Review qualification report](../MIX_REVIEW_BENCHMARK_REPORT.md)

All generated benchmark receipts use the `kenn.dsp_benchmark.v1` or
`kenn.dsp_profile.v1` schema and retain the source revision, fixture identity,
machine metadata, raw latency samples, and peak RSS.

## Measurements

### Bounded WAV analysis

Five repetitions per case, plus a two-worker concurrency pass:

| Fixture | p50 | p95 | p99 | Peak RSS | Result |
|---|---:|---:|---:|---:|---|
| 5 s, 48 kHz mono PCM16 | 165.482 ms | 165.766 ms | 165.788 ms | 75.9 MB | qualified |
| 2 s, 96 kHz mono PCM16 | 147.889 ms | 148.110 ms | 148.116 ms | 75.9 MB | qualified |

The complete bounded request is deterministic and within the existing resource
contract. This is a Python reference baseline, not a C++ speed claim.

### Mix Review

The current local Mix Review qualification benchmark passes its documented
synthetic scope:

- precision: 100%
- recall: 100%
- F1: 100%
- false-positive rate: 0%
- steady-state mean latency: 14.80 ms
- cold start: 16.57 ms
- corrupted-input recovery: 100%

The Mix Review test suite and Automix adapter tests also pass: 8 tests passed.

### Stage profile

Five profiled 2 s requests produced 1,004.832 ms total cProfile time:

| Function | Calls | Exclusive | Cumulative |
|---|---:|---:|---:|
| `_fft` | 20 | 369.437 ms | 369.481 ms |
| `_spectral_measurement` | 5 | 67.091 ms | 485.764 ms |
| `_decode` | 5 | 52.650 ms | 74.556 ms |

The FFT is the largest exclusive hot function and is the first native POC
candidate. The spectral stage is the largest named request stage. cProfile
totals overlap by design; the complete-request benchmark remains the adoption
gate.

## Scope boundary

No licensed/owned real-mix WAV corpus or rendered multistem AutoMix fixture is
present in the active product tree. The checked-in `.als` demo and Automix
adapter tests are structural assets; they are not a representative offline
DSP workload. A real-mix/1–64-stem fixture pack is required before claiming an
AutoMix performance result.

## Decision

Proceed to a narrow FFT/spectral vertical-slice POC:

1. retain the Python reference as the oracle and fallback;
2. compare a portable C++20 FFT against the current Python FFT on the same
   deterministic fixtures;
3. include binding/copy overhead and complete-request latency;
4. stop if the complete request does not clear the roadmap's adoption gates.

This receipt does not authorize a broad C++ rewrite.
