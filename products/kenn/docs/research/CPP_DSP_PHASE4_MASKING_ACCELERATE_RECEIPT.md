# KENN Phase 4 Accelerated Stem-Masking Receipt

**Run date:** 2026-09-21
**Status:** qualified as an opt-in macOS Accelerate candidate; release default
remains NumPy

The earlier portable scalar masking POC was a no-go because its C++ FFT was
slower than NumPy. The same seven-band kernel now uses the existing Apple
Accelerate/vDSP FFT setup when the native extension is built with
`KENN_USE_ACCELERATE=ON`; the scalar implementation remains available for
portable builds and is not promoted as a performance claim.

On the deterministic 8-stem, 5-second, 48 kHz fixture:

| Candidate | Mean | p95 | Findings | Findings digest |
| --- | ---: | ---: | ---: | --- |
| NumPy reference | 32.994 ms | 33.332 ms | 9 | `88e333154ba1b7196e4ee70010a1a63a16d786dd3c6594124c45f06e4251bc2d` |
| C++ Accelerate | 13.127 ms | 13.388 ms | 9 | `88e333154ba1b7196e4ee70010a1a63a16d786dd3c6594124c45f06e4251bc2d` |

The opt-in native path is approximately 2.51× faster on this bounded fixture,
with exact finding parity. The reproducible command is
`tooling/scripts/benchmark_masking_native.py`; the JSON receipt records the
fixture hash and individual samples. The masking adapter reports the actual
backend (`cpp-accelerate` or `cpp-scalar`) instead of labelling every native
run as scalar.

This remains synthetic engineering evidence, not a perceptual or real-mix
quality claim. Keep `KENN_DSP_MASKING_NATIVE=0` as the default until the
rights-cleared real-mix matrix, Windows implementation, and complete-request
AutoMix qualification are available.
