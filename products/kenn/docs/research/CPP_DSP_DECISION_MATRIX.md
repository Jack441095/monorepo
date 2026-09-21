# KENN C++ DSP Decision Matrix

**Date:** 2026-09-20
**Scoring:** 1 (poor) to 5 (strong). Higher integration/licence-risk scores
mean lower risk. Scores are directional and must be replaced by benchmark
evidence before implementation is selected.

## Component migration matrix

| Candidate | User value | Likely speed potential | Evidence strength | Maintainability | Integration safety | Priority | Decision |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Existing realtime feature core | 5 | 3 | 5 | 4 | 4 | 5 | Restore and share |
| Python WAV decode/list conversion | 4 | 5 | 3 | 4 | 4 | 5 | First profile/POC |
| Python hand-written FFT/band reduction | 4 | 5 | 4 | 4 | 4 | 5 | First profile/POC |
| Stem-masking per-frame band energy | 4 | 4 | 4 measured | 3 | 4 | 3 | Scalar C++ POC no-go; keep NumPy |
| Zero-lag stereo correlation summary | 3 | 3 | 2 measured | 4 | 4 | 2 | Temporary C++ POC ~9–10% complete-request gain; no-go below 25% gate |
| AutoMix transient threshold | 4 | 4 | 4 historical | 3 | 3 | 4 | Recover and remeasure |
| AutoMix limiter/envelope | 4 | 3 | 4 historical | 3 | 3 | 4 | Recover and remeasure |
| Shared feature cache/single pass | 5 | 5 | 4 architectural | 5 | 5 | 5 | Do before more ports |
| Resampling | 3 | 2 | 2 | 3 | 3 | 2 | Benchmark libraries only |
| Qualified beta detectors | 1 | 1 | 5 current | 2 | 3 | 1 | Do not port |
| Retrieval/BM25 | 2 | 2 | 2 | 2 | 3 | 1 | Keep Python |
| Receipt/report generation | 1 | 1 | 4 | 1 | 2 | 1 | Keep Python |
| Model inference runtime | 3 | 2 | 3 | 1 | 2 | 2 | Retain ONNX/native runtime |
| GPU DSP | 2 | 2 | 1 | 1 | 1 | 1 | Defer |

## Native integration options

| Option | Call overhead | Copy control | Crash isolation | Packaging | Reuse in plugin | Recommendation |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Pure C++ core + static plugin link + nanobind Python module | 5 | 5 | 2 | 3 | 5 | **Recommended** |
| Pure C ABI shared library + Python `ctypes` | 3 | 4 | 2 | 3 | 4 | Acceptable for a tiny stable ABI, but weaker array ergonomics |
| pybind11 extension | 4 | 5 | 2 | 3 | 5 | Mature alternative to nanobind |
| Separate native worker process | 2 | 2 | 5 | 2 | 1 | Use only for unstable/heavy offline jobs |
| Node-API addon | 4 | 4 | 2 | 3 | 3 | Not aligned with current Python owner |
| Swift/Objective-C++ bridge | 4 | 4 | 2 | 3 | 3 | Desktop-only; not the DSP contract |
| WebAssembly | 2 | 3 | 4 | 2 | 1 | No current product need |

## FFT/backend options

| Backend | macOS performance | Windows portability | Licence/distribution | Maintenance | Decision |
| --- | ---: | ---: | ---: | ---: | --- |
| Apple Accelerate/vDSP | 5 | 1 | 5 | 5 | First macOS POC backend |
| Vectorized NumPy/`numpy.fft` | 4 | 5 | 5 | 5 | Mandatory simpler comparator |
| JUCE FFT | 3 | 5 | 3 | 4 | Portability baseline; benchmark required |
| oneMKL | 3 on Apple Silicon | 5 on Windows x64 | 3 | 3 | Consider for Windows benchmark |
| FFTW | 5 | 5 | 1 under GPL; commercial option | 3 | Exclude by default |
| Custom FFT/SIMD | 2 initially | 3 | 5 | 1 | Do not build unless existing options fail |

JUCE's official documentation explicitly describes `juce::dsp::FFT` as a
simple low-footprint implementation not tuned for speed. Its score is therefore
a test hypothesis, not a criticism of its usefulness.

## Resampling options

| Option | Quality/control | Portability | Licence risk | Realtime suitability | Decision |
| --- | ---: | ---: | ---: | ---: | --- |
| Existing SciPy `resample_poly` | 4 | 5 | 4 | 2 | Keep as reference/current default |
| libsamplerate | 4 | 5 | 5 (BSD-2-Clause) | 4 | Best external benchmark candidate |
| libsoxr | 5 | 5 | 3 (LGPL-2.1) | 2-4 by mode | Offline benchmark after review |
| JUCE resampling facilities | 3 | 5 | 3 | 4 | Consider where JUCE already exists |
| Custom resampler | 1 | 3 | 5 | 1 | No-go |

## Binding choice

Recommend **nanobind** for the POC because the boundary is array-heavy and the
official project offers BSD-3-Clause licensing and NumPy-compatible ndarray
support. Use pybind11 instead if the team's existing packaging expertise is
materially stronger. Do not adopt both.

The binding library is not the performance strategy. The strategy is one
coarse-grained call over caller-owned contiguous arrays with the GIL released.

## Go/no-go scorecard

| Gate | Required result |
| --- | --- |
| Canonical source | Active build/test/benchmark has no missing legacy path |
| Hot-stage relevance | Candidate accounts for >=20% of target request |
| Hot-stage performance | >=3x improvement |
| End-to-end performance | >=25% analysis request or >=10% representative AutoMix project |
| Memory | <=5% regression unless justified; preferably lower |
| Numerical parity | All declared tolerances pass |
| Product parity | Receipt/gate/status semantics unchanged |
| Realtime safety | No allocation/lock/I/O; p99.9 <20% deadline |
| Fallback | Python reference selectable and tested |
| Packaging | Clean macOS and supported Windows artifacts |
| Licensing | Owner-approved dependency/licence record |

Any failed required gate means **no-go or further investigation**, not “ship
with a note.”

## Final selection

1. Repair the source boundary.
2. Compare vectorized NumPy, Accelerate/vDSP C++, and the preserved Python
   spectral implementation.
3. Adopt the smallest implementation that clears every gate.
4. Recover already-proven AutoMix kernels only after their complete-project
   benefit is reproduced.
5. Leave the rest of KENN in Python.
