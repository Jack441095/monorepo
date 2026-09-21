# KENN Real-Mix Bottleneck Profile Receipt

**Status:** next native target identified; no new promotion

A fresh cProfile run on the supplied 69.8 MB stereo mixdown completed in
54,668.87 ms with native DSP disabled. The FFT accounted for only 130 ms of
exclusive time (187 ms cumulative), while WAV decode accounted for 10,316 ms,
RMS/statistical loops for roughly 8,234 ms, and correlation for 7,874 ms.

This explains why the scalar and Accelerate FFT candidates do not materially
improve the long-mix complete request: the dominant work is Python decoding
and per-sample summary computation. The next bounded C++ experiment should
cover PCM decode plus bulk channel statistics/correlation, preserving the
current Python reference and result schema as the oracle.

Machine-readable evidence is in
`results/phase4_real_mix_profile.json`. This is prioritisation evidence only;
it is not a release or perceptual-quality claim.
