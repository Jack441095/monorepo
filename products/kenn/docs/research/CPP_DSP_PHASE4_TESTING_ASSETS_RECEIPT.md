# KENN Phase 4 Testing-Assets Receipt

**Run date:** 2026-09-20
**Status:** internal qualification pass; native release-default gate not met

The supplied directory
`/Volumes/Jack_Gandy_1TB_SSD/Nite-DSP/Nite-DSP-Operations/testing-assets`
contains a 9-track manifest with 341 audio files. Eight canonical generated
stereo mixdowns were benchmarked without copying them into the repository:

- 44.1 kHz, 24-bit PCM;
- 80.8–263.9 seconds per mix;
- 21.4–69.8 MB per file;
- all eight analyses completed successfully.

## Reference/native evidence

Receipts:

- `results/phase4_testing_assets_reference.json`
- `results/phase4_testing_assets_native.json`
- `results/phase4_testing_assets_parity.json`
- `results/phase4_testing_assets_post_cleanup_summary.json`

The native spectral path matched the Python reference on all eight reports
under the declared numeric policy. After the duplicate-correlation cleanup,
the refreshed full-corpus mean complete-request speed ratio was `0.98962x`
(native was 1.05% slower and did not clear the 25% end-to-end adoption gate).
Only the shorter `dream_of_you` case was faster; the longer mixes were slower
because localization, summary loops, and peak extraction remain Python work.

## Decision

Keep `KENN_DSP_NATIVE` opt-in. The current scalar C++ path is a valid parity
and packaging slice, but this corpus does not justify making it the production
default. A future promotion requires moving more of the complete request over
the boundary or using an optimized platform FFT backend, followed by another
full-corpus comparison.

The Apple Accelerate/vDSP experiment is recorded separately in
`CPP_DSP_PHASE4_ACCELERATE_RECEIPT.md`. It also passes parity but measures
`1.00231x` complete-request latency on this corpus, so it is not promoted.

The follow-on native bulk channel-statistics/correlation slice is recorded in
`CPP_DSP_PHASE4_NATIVE_BULK_METRICS_RECEIPT.md`. It reduces the complete
request to `0.522969x` reference latency with zero parity differences, but
remains opt-in until the corpus rights and cross-platform release gates are
closed.

The asset manifest labels its source license as `TODO-vendor-pack`. Therefore
this receipt is internal engineering evidence only; it is not a rights or
redistribution approval and does not complete the release-listening gate.

The corresponding stem-level AutoMix evidence and exact-count coverage are
recorded in `CPP_DSP_PHASE4_AUTOMIX_ASSETS_RECEIPT.md`; historical native
AutoMix kernel measurements and their recovery boundary are in
`CPP_DSP_PHASE4_AUTOMIX_KERNEL_RECEIPT.md`.
