# QC-05 Model Provenance — V5 vs V6 Dedup (2026-09-18, branch slo/class-opt-v1)

## Findings (md5-verified)
- Shipped `Source/AcousticClassifierWeights.h` == benchmark `AcousticClassifierWeights_v6.h`
  (md5 `ec6150053bbd71538a61586be9f8387c`). Canonical = **V6**.
- Shipped `Source/AcousticClassifierCentroids.h` was numerically identical to
  `AcousticClassifierCentroids_v6.h` (all 8209 floats) but differed by ONE stray line:
  `inline constexpr float classThresholds[numClasses] = {` (line 12, unterminated,
  would break compilation if the benchmark header were ever included).
- Fix applied (1-line deletion): benchmark v6 header now diffs **0 lines** vs shipped.
- `*_v5.h` (weights md5 `bd9b8857…`, centroids md5 `1db3840e…`) are genuinely different
  values — superseded research archives, referenced only by
  `train_gpu_classifier_v6_intelligent.py`.

## Rule (canonical source)
- `Source/*.h` is the ONLY model source the build reads. Benchmark `*_v5.h` are
  frozen archives — do not include, do not edit, do not delete without owner sign-off
  (25 MB generated files; deletion needs explicit approval per safety rails).
- Any future export must overwrite BOTH the shipped header and the benchmark
  versioned copy in the same commit, with md5s recorded here.

## Verification
- `python3` float-compare: shipped vs v6 = 8209/8209 identical after fix.
- `diff` shipped vs v6 = 0 lines.
- No `#include` of any `*_v5`/`*_v6` benchmark header exists in `Source/` or tests.
