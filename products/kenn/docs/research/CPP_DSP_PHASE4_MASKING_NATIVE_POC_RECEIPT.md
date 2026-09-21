# KENN Stem-Masking Native POC Receipt

**Run date:** 2026-09-20
**Status:** measured no-go for portable scalar C++ promotion

The measured `_band_energy_over_time` hotspot was implemented behind the
optional native boundary and compared with the existing NumPy reference on an
8-stem, 5-second, 48 kHz deterministic fixture.

| Check | Result |
| --- | --- |
| Output shape | 116 frames × 7 bands |
| Maximum absolute error | `2.84e-14` |
| Findings parity | exact |
| Python/NumPy mean | 4.212 ms |
| C++ scalar mean | 13.146 ms |
| C++ speedup | `0.32x` (slower) |

The portable scalar kernel is therefore **not promoted**. It remains available
only with `KENN_DSP_MASKING_NATIVE=1` for future backend experiments; the
default path stays NumPy so installing the native spectral extension cannot
regress masking latency. A future native masking attempt needs an optimized
FFT/SIMD backend and a complete real AutoMix request before reconsideration.

The optimized Apple follow-up is recorded separately in
`CPP_DSP_PHASE4_MASKING_ACCELERATE_RECEIPT.md`; it uses Accelerate/vDSP and
does not change this scalar no-go decision.

This is synthetic evidence, not a real-mix or perceptual-quality claim.
