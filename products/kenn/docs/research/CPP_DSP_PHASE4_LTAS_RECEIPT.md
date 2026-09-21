# KENN Phase 4 Native LTAS Receipt

**Run date:** 2026-09-21
**Status:** qualified as an opt-in native report optimization; release default
remains unchanged

The native spectral kernel now accepts `include_ltas=True` and computes the
40 logarithmic LTAS band levels from the already-averaged FFT powers. The
Python report layer uses those levels for normalization around 1 kHz instead
of rescanning the full power array in `_ltas_40_band_relative_db`.

Evidence:

- Native and forced-reference LTAS reports produced the same 40-band rows and
  pink-noise comparison on a deterministic 10-second, 48 kHz PCM16 fixture.
- The native wheel smoke checks the new `ltas_band_levels` export shape and
  finite-value contract.
- `test_audio_analysis.py` passes in native mode and the reference fallback
  remains green.
- Warm complete-request benchmark with LTAS enabled: native p50 `5.152 ms`;
  forced Python reference p50 `254.330 ms`. The native and reference output
  contracts remain exact; these timings include the full decoder, spectral
  analysis, and report construction, not only the LTAS loop.

The reproducible benchmark is:

```sh
KENN_DSP_NATIVE=1 python tooling/scripts/benchmark_audio_analysis.py \
  --long-seconds 10 --repeats 5 --workers 2 --include-ltas
```

This is bounded synthetic runtime evidence. Keep native dispatch opt-in until
rights-cleared real-mix, cross-platform, and complete AutoMix qualification
gates are satisfied.
