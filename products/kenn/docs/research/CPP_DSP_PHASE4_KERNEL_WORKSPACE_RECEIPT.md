# C++ DSP phase 4: native FFT workspace receipt

## Scope

The Accelerate/vDSP spectral and masking kernels were profiled for avoidable
hot-loop work. Each frame previously created packed-complex, real, imaginary,
and power-spectrum scratch vectors, and the spectral peak path copied every
window into a temporary vector. The windowing pass also ran separately from
input staging.

The native implementation now:

- owns vDSP real/imaginary scratch buffers for the lifetime of one kernel call;
- reuses the power vector capacity across frames;
- passes the already-interleaved real input to `vDSP_ctozD` without a packed
  complex copy;
- fuses Hann windowing into input staging; and
- scans window spectra by pointer, without a per-window spectrum copy.

The scratch lifetime is per call, so concurrent requests do not share mutable
FFT state. The portable scalar path remains compiled and tested.

## Reproduction

```text
PYTHONPATH=products/kenn/apps/backend/src \
KENN_DSP_NATIVE=1 \
products/kenn/apps/backend/.venv/bin/python \
products/kenn/tooling/scripts/benchmark_native_kernels.py \
  --seconds 10 --sample-rate 48000 --repeats 20 \
  --json-out products/kenn/docs/research/phase4_native_kernel_workspace.json
```

Current Accelerate receipt (`phase4_native_kernel_workspace.json`) reports:

| Kernel | p50 | p95 | Backend |
| --- | ---: | ---: | --- |
| `spectral_power` (4 windows, 16,384 FFT) | 1.0387 ms | 1.0846 ms | `cpp-accelerate` |
| `masking_band_energy` (233 frames, 4,096 FFT) | 1.8649 ms | 1.9573 ms | `cpp-accelerate` |

The fixture is deterministic float32 noise (10 seconds at 48 kHz; SHA-256
`d44fe9e6a54c456ab3205bbcae38fdfb9927731a7dedb6602030429db8987c39`). These
are kernel timings only, not perceptual or real-mix claims. Promotion still
requires the complete-request benchmark and fallback checks.

## Verification

- Native smoke/parity checks: passed.
- Accelerate and scalar CMake builds: passed.
- Native backend plus Mix Review regression tests: `50 passed`.
- Native-disabled fallback smoke: passed.
- Isolated wheel install and native smoke/parity checks: passed.
- `git diff --check`: passed.
