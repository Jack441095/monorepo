# SLO Classification V3 Results

## 1. Flat vs. Factorized Modeling
We trained and evaluated Flat vs. Factorized architectures on clean, deduplicated data (Stratified 5-Fold CV):

| Metric | Flat Model | Factorized (Content + Temporal) |
|---|---|---|
| **Accuracy** | **82.5%** | 81.8% |
| **Macro F1** | **0.814** | 0.806 |

The Flat model yields marginally better accuracy and F1 score while bypassing the schema complexity of dual content and temporal databases.

## 2. ECE Calibration Results
Temperature scaling ($T=0.6864$) significantly improves probability calibration on out-of-fold data:
- **ECE Before**: 0.1097
- **ECE After**: **0.0452** (**58.8% reduction**)
- **Brier Score Before**: 0.0839
- **Brier Score After**: **0.0609**

## 3. Evidence Fusion Performance
Evaluating fusion rules on virtual adversarial misleading filenames (e.g. snare audio named "kick"):
- **Precedence Override Accuracy (threshold @ 0.75)**: **88.3%**
- This indicates the calibrated classifier successfully overrides conflicting filename cues in **88.3%** of adversarial cases, preventing false indexing.
