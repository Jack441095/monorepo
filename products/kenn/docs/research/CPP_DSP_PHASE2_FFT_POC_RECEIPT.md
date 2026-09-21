# KENN Native FFT POC Receipt

**Run date:** 2026-09-20
**Status:** integrated behind an opt-in/rollback-safe Python boundary; not yet
the default release artifact

Comparison receipt: [phase2_native_comparison.json](results/phase2_native_comparison.json)

## Candidate

`tooling/native/fft_poc` is a portable C++20 radix-2 FFT candidate. It uses
the same 16,384-point Hann-windowed, 1 kHz deterministic signal shape used by
the Python reference probe and processes four windows per iteration.

The candidate now has two layers:

- a shared portable C++20 FFT/spectral core in `tooling/native/dsp_core`;
- an optional nanobind module and Python adapter used by the bounded WAV
  spectral path.

The Python reference remains available with `KENN_DSP_NATIVE=0`. If the module
is missing, the analyzer falls back to the reference implementation. The
native result records `implementation=cpp-scalar` and whether the float32
NumPy boundary copied the input.

Apple builds now also expose `implementation=cpp-accelerate` through the
Accelerate/vDSP backend. Its complete-request result is recorded in
`CPP_DSP_PHASE4_ACCELERATE_RECEIPT.md`; it remains opt-in because it did not
beat the Python/NumPy reference on the supplied long-mix corpus.

## Build and test

```text
cmake -S products/kenn/tooling/native/fft_poc -B <build> -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON
cmake --build <build> --parallel 2
ctest --test-dir <build> --output-on-failure
```

The Release build and CTest smoke test passed.

The CTest suite now also includes an explicit FFT-core contract test covering
power-of-two validation, Python-compatible multi-window starts, and an impulse
transform. It passes in both Release and ASan/UBSan builds.

The standalone core also passed an AddressSanitizer/UndefinedBehaviorSanitizer
build and smoke run on macOS with leak detection disabled (Apple's runtime does
not support `detect_leaks` on this host).

The portable-core ASan/UBSan CTest smoke is now part of
`.github/workflows/kenn-dsp-native.yml` on macOS 14 and Ubuntu 24.04. This
guards the shared FFT implementation on both Unix toolchains; it is not a
substitute for Windows host validation or a sanitizer run inside a DAW-loaded
nanobind/plugin process.

The optional extension also builds as a clean wheel using the declared
`scikit-build-core`/`nanobind` build requirements. The current local macOS
arm64 wheel is recorded in
`results/phase4_native_wheel_packaging.json`; `make native-wheel` passes
`CMAKE_EXECUTABLE` explicitly so scikit-build-core cannot select an
incompatible stale system CMake. Windows and host-loading validation remain
open.

## Kernel comparison

| Candidate | 400 FFTs | Average FFT | Checksum |
|---|---:|---:|---:|
| Python reference `_fft` | 7,005.680 ms | 17,514.200 µs | 363014246.166083 |
| C++20 scalar candidate | 117.449 ms | 293.624 µs | 363014246.166083 |

The checksum is identical for this deterministic probe. The standalone C++
kernel is approximately 57x faster than the Python reference on this machine.

The integrated complete-request comparison (10 repetitions, fresh process per
candidate) is:

| Fixture | Python p50 | Native p50 | p50 improvement | Native p95 |
|---|---:|---:|---:|---:|
| 5 s, 48 kHz | 164.426 ms | 93.294 ms | 43.3% | 132.417 ms |
| 2 s, 96 kHz | 148.847 ms | 74.881 ms | 49.7% | 76.142 ms |

Peak RSS changed from 81.2 MB to 82.3 MB (+1.37%), inside the proposed 5%
regression bound. This includes Python-to-float32 conversion and native result
conversion, not just the kernel.

Reference/native report parity passed with zero differences under a 2e-5
absolute/relative numeric tolerance across metrics, spectral bands, LTAS,
localized windows, and findings. The native analyzer test set and reference
test set each passed 11 tests.

Malformed native-boundary probes reject empty and non-contiguous inputs with
deterministic Python exceptions; unsupported/absent native modules fall back
to the reference path.

The broader backend regression suite completed with 1,260 passed and 5
skipped. Three unrelated retrieval/session tests remain red because the
optional ONNX embedding model is absent from this checkout; the failures are
not in the audio-analysis or native-DSP paths.

## Next gate

Complete release qualification for the integrated vertical slice:

1. add an owned real-mix/AutoMix fixture pack and rerun the complete-request
   comparison;
2. add sanitizer coverage to the extension build and CI;
3. build/test the wheel on every supported Python and OS target;
4. add the macOS Accelerate/vDSP backend only if it improves the complete
   request further;
5. keep the reference default until those gates pass.

Do not enable this candidate in the product until the complete-request and
parity gates in `CPP_DSP_MIGRATION_ROADMAP.md` pass.
