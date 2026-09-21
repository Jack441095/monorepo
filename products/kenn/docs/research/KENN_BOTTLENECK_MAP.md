# KENN bottleneck map

## Measured on this host

| Path | Reference | Native | Decision |
|---|---:|---:|---|
| 10 s/48 kHz analysis p50 | 440.133 ms | 43.830 ms | 10.04x; accept native candidate after distribution gates |
| Same p95 | 444.122 ms | 111.735 ms | 3.97x; investigate native jitter |
| 2 s/96 kHz p50 | 277.858 ms | 22.820 ms | 12.18x |
| 4 concurrent analyses | 1767.952 ms | 112.385 ms | 15.73x |
| Peak process RSS | 213,057,536 B | 54,149,120 B | 74.58% lower in separate-process runs |
| Real 24-bit 44.1 kHz vocal stem p50 | 475.969 ms | 8.300 ms | 57.35x |
| Real stem p95 | 507.688 ms | 8.659 ms | 58.63x |
| Mix Review complete p50 | 165.780 ms | 146.338 ms | 1.13x; reject default promotion |

All analysis cases used three warmups and ten measured repetitions. Input SHA-256 values and individual samples are in the JSON receipts. The real asset is local testing material and is identified by path/hash in the receipt; audio was not copied into documentation.

Native kernel timings for 10 s float32 noise: spectral p50 3.5751 ms, masking p50 6.1818 ms. Plugin meter-kernel tests consumed 0.072%–0.112% of the callback deadline across 64–1024 frame blocks, but this is not a full plugin or Live deadline measurement.

## Unmeasured or dominant system latency

Model provider inference, AudioGen generation, real OSC round trips, state snapshot scaling, database contention, UI transport and SLO large-library inference were not measured end to end here. They are likely to dominate once DSP is native. The current semantic index is absent, so retrieval latency/quality measurements would characterize BM25 fallback rather than the intended stack.

Native/Python output parity passed the provided decoder/DSP smoke and backend regression suite. The benchmark reports `native_input_copied=false`; nanobind-owned result arrays and GIL release are present in source. Cross-platform wheels, ASan/UBSan and representative-corpus deterministic output digests remain promotion gates.
