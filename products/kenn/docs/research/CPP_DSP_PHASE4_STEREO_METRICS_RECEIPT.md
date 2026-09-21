# KENN Phase 4 Stereo-Metrics Scan Receipt

**Run date:** 2026-09-21
**Status:** native implementation optimized; opt-in release status unchanged

`stereo_metrics` previously summarized both channels and then called a
correlation helper that summarized both channels again. The helper now accepts
the already-computed DC offsets, so stereo analysis performs one summary pass
per channel and one combined correlation/mid-side pass instead of rescanning
both channels for correlation.

The output contract remains unchanged. The deterministic native smoke,
complete audio-analysis parity test, and Python fallback tests all pass. A
local Release Accelerate build measured a p50 of `19.030 ms` for 4.8 million
stereo frames; this is a direct-kernel timing reference, not a release gate.

The broader eight-mix complete-request parity and performance evidence remains
in `CPP_DSP_PHASE4_NATIVE_BULK_METRICS_RECEIPT.md`. Keep native dispatch
opt-in until the rights-cleared and cross-platform gates are complete.
