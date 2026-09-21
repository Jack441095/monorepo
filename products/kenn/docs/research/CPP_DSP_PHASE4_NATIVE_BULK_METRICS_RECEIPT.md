# KENN Native Bulk Metrics Receipt

**Status:** qualified opt-in slice; no release-default promotion

The native extension exposes bulk mono/stereo channel statistics and
correlation alongside the spectral backend. The follow-on native decoder
receipt now covers the WAV-to-float32 boundary before these kernels. When
`KENN_DSP_NATIVE=1`, KENN uses the native path; when the extension is absent or
disabled, the original Python decoder and loops remain the oracle and fallback.

The portable scalar build was also configured explicitly with
`KENN_USE_ACCELERATE=OFF` and passed its metrics/spectral smoke checks.

On all eight supplied canonical stereo mixdowns, the native path matched the
reference result with zero differences after excluding dynamic receipt fields
under the existing `2e-5` absolute/relative tolerance. Complete-request mean
latency fell from **14,953.117 ms** to **7,820.016 ms** (`0.522969x`, a
47.7% improvement). Peak RSS fell from **3,888,594,944** to **2,469,937,152**
bytes (36.5% lower).

This clears the local performance/parity gate for the bounded WAV request, but
the native path remains opt-in until rights-cleared corpus evidence,
cross-platform wheel/host validation, and release signing are complete.
Machine-readable evidence is in
`results/phase4_native_bulk_metrics.json`.
