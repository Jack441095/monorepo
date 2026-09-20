# SLO Encoder Research Decision — 2026-09-15

## Outcome

The CLAP-music+DSP candidate is a materially stronger classification input on
the current 21,793-row corpus, but it is **not approved for Beta 1**. Continue
it as a post-beta candidate while the shipping PANNs+DSP path remains frozen.

## Controlled result

Protocol: identical rows, labels, DSP block, ClassifierV4 architecture,
five stratified out-of-fold splits, seed 42, and 90 epochs per fold. Training
ran with only GPU 0 visible on an NVIDIA RTX 4090 D.

| Input | OOF accuracy | Macro-F1 | Fold accuracy range |
|---|---:|---:|---:|
| Shipping PANNs+DSP 520-D | 73.86% | 69.98% | 72.95–74.79% |
| CLAP-music+DSP 520-D | 82.20% | 79.27% | 81.17–82.79% |
| Candidate delta | **+8.34 pp** | **+9.29 pp** | — |

Every class improved in F1. The smallest improvements were Vocal Phrase
(+4.00 pp), Synth (+4.84 pp), and Synth Loop (+4.97 pp); the largest were
Music Loop (+19.19 pp), FX (+13.60 pp), Bass Loop (+12.47 pp), and Clap
(+12.09 pp).

The candidate’s weakest remaining classes are Music Loop (61.54% F1, support
92), Impact (61.97%, support 185), FX (71.57%, support 865), and Vocal Loop
(75.90%, support 102). The largest residual confusion is Foley predicted as
Percussion (309 cases), followed by Percussion/Hi-Hat and Hi-Hat/Percussion.

## Why this is not a ship decision

- The split is row-stratified, not vendor/pack-held-out. Near-duplicate and
  same-pack leakage may inflate both arms, so this measures controlled encoder
  lift rather than real-world generalisation.
- The CLAP music checkpoint directory is about 744 MB and its weights file is
  about 776 MB, versus roughly 23 MB of PANNs ONNX weights/data in the current
  product. Packaging, memory, startup, scan throughput, CPU fallback, and AU/
  VST3 host effects are unmeasured.
- Model redistribution rights and all third-party notices still require an
  explicit legal/license review.
- The production C++ preprocessing and inference path does not yet implement
  this candidate; Python research parity is insufficient.
- Unknown/OOD calibration, confidence reliability, and the protected blind
  set have not been rerun for this encoder.

## Promotion gates

1. Vendor/pack-grouped blind evaluation with duplicate-family isolation.
2. No material class regression; report confidence intervals for low-support
   classes instead of treating point estimates as stable.
3. Exported-model numerical parity between Python and production C++.
4. Signed Release measurements for package size, cold start, per-file latency,
   1k/10k-library throughput, peak RSS, CPU fallback, and host stability.
5. Redistribution-license and notices approval.
6. OOD/Unknown threshold calibration with false-confident-error limits.
7. Separate immutable candidate and rollback plan; no in-place replacement in
   the Beta 1 branch.

## Evidence receipt

- Local copy: `_artifacts/slo_encoder_quality_detailed_20260915.json`
- Size: 9,308 bytes
- SHA-256: `83c8ab41254b781a6a3f68bdc632cf68d985d126ab9b457023f0f25b8c62682f`
- Remote source: `/mnt/data/slo_training/beta_research/encoder_quality_detailed_20260915.json`
- GPU 0 was idle again after completion.
- The run did not reset or restart the server, GPU, services, or other jobs.
