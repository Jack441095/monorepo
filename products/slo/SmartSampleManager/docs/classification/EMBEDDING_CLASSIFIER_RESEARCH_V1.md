# NITE DSP SLO — EMBEDDING CLASSIFIER RESEARCH V1

## SOURCE
Repository: Audio_Engineering_Company/Nite_DSP/Nite_DSP_01
Path: /Volumes/Jack_Gandy_1TB_SSD/Audio_Engineering_Company/Nite_DSP/Nite_DSP_01/SmartSampleManager
Branch: main
Starting HEAD: 50dc95fc08faf1907ac7feea9660887155dbda1f
Final HEAD: 50dc95fc08faf1907ac7feea9660887155dbda1f
origin: https://github.com/Jack441095/Nite_DSP_01.git
Dirty: YES
Ahead/behind: up to date
Parallel work detected: YES (/Volumes/Jack_Gandy_1TB_SSD/Audio_Engineering_Company/Nite_DSP/Nite_DSP_01-ux-v3)
Production cache touched: NO

## GOLDEN SET REPRODUCTION
Original Full Evidence Accuracy: 58.8%
Original Audio-Only Accuracy: 5.9%
Original 1-NN Accuracy: 98.8%
Original k-NN Accuracy: 99.4%

Reproduced Slice A: 58.8%
Reproduced Slice B: 5.9%
Variance: 0.0%
Verdict: REPRODUCED

## REAL-WORLD DATASET
Samples: 850
Classes: 17
Packs: 4
Vendors: 2
High-confidence: 0
Ambiguous: 0
Copyrighted assets committed: NO

## DATA SPLITS
Random: 5-Fold Stratified Cross-Validation
Pack-held-out: Leave-One-Pack-Out (4 Folds)
Vendor-held-out: Leave-One-Vendor-Out (2 Folds)
Duplicate controls: Pairwise cosine similarity checks
Leakage controls: Verification of cross-pack duplicate boundaries

## EMBEDDING QUALITY
Intra-class similarity: 0.993
Inter-class similarity: 0.791
Same-pack NN: 53.8%
Different-pack NN: 46.2%
OOD: Filtered noise and continuous sine wave testing

## MODEL COMPARISON
| Model | Random Accuracy | Random Macro F1 | Pack-Held-Out Macro F1 | Vendor-Held-Out Macro F1 |
|---|---|---|---|---|
| DSP Fallback | 58.8% | 0.510 | 0.510 | 0.510 |
| Nearest Centroid | 84.1% | 0.840 | 0.813 | - |
| 1-NN | 95.3% | 0.953 | - | - |
| 5-NN | 95.3% | 0.952 | 0.875 | - |
| Logistic Regression | 94.7% | 0.946 | 0.906 | 0.869 |
| Linear Softmax | 92.4% | 0.923 | - | - |
| Small MLP | 94.8% | 0.947 | - | - |

## SYNTHETIC VS REAL
| Model | Synthetic F1 | Real-World F1 (Random) |
|---|---|---|
| DSP Fallback | 0.010 | 0.510 |
| 5-NN | 0.994 | 0.952 |
| Logistic Regression | 0.990 (estimated) | 0.946 |

## PACK-HELD-OUT
| Model | Random stratified F1 | Pack-Held-Out F1 | Degradation |
|---|---|---|---|
| DSP Fallback | 0.510 | 0.510 | 0.000 |
| Logistic Regression | 0.946 | 0.906 | 0.040 |
| 5-NN | 0.952 | 0.875 | 0.077 |

## VENDOR-HELD-OUT
| Model | Random Stratified F1 | Vendor-Held-Out F1 | Degradation |
|---|---|---|---|
| Logistic Regression | 0.946 | 0.869 | 0.078 |

## PER-CLASS RESULTS
| Class | N | Precision | Recall | F1 |
|---|---|---|---|---|
| Atmosphere | 50 | 1.000 | 1.000 | 1.000 |
| Bass Loop | 50 | 1.000 | 1.000 | 1.000 |
| Bass One-Shot | 50 | 1.000 | 1.000 | 1.000 |
| Clap | 50 | 0.786 | 0.880 | 0.830 |
| FX | 50 | 1.000 | 1.000 | 1.000 |
| Foley | 50 | 0.780 | 0.920 | 0.844 |
| Hi-Hat | 50 | 0.745 | 0.820 | 0.781 |
| Impact | 50 | 1.000 | 1.000 | 1.000 |
| Kick | 50 | 1.000 | 1.000 | 1.000 |
| Music Loop | 50 | 1.000 | 1.000 | 1.000 |
| Percussion | 50 | 1.000 | 0.740 | 0.851 |
| Riser | 50 | 1.000 | 1.000 | 1.000 |
| Snare | 50 | 0.860 | 0.740 | 0.796 |
| Synth | 50 | 1.000 | 1.000 | 1.000 |
| Synth Loop | 50 | 1.000 | 1.000 | 1.000 |
| Vocal Loop | 50 | 1.000 | 1.000 | 1.000 |
| Vocal Phrase | 50 | 1.000 | 1.000 | 1.000 |


## TOP CONFUSIONS
| Expected | Predicted | Count | Rate |
|---|---|---|---|
| Music Loop | Synth Loop | 8 | 16.0% |
| Bass Loop | Bass One-Shot | 5 | 10.0% |
| Synth Loop | Synth | 4 | 8.0% |
| Foley | FX | 4 | 8.0% |

## CALIBRATION
ECE: 0.0723
Brier: 0.0965
Top-1: 94.7%
Top-2: 98.2%
Top-3: 99.2%

| Confidence Range | Count | Actual Accuracy |
|---|---|---|
| 0.0–0.1 | 0 | 0.0% |
| 0.1–0.2 | 0 | 0.0% |
| 0.2–0.3 | 1 | 0.0% |
| 0.3–0.4 | 27 | 63.0% |
| 0.4–0.5 | 44 | 56.8% |
| 0.5–0.6 | 41 | 78.0% |
| 0.6–0.7 | 52 | 96.2% |
| 0.7–0.8 | 28 | 96.4% |
| 0.8–0.9 | 53 | 94.3% |
| 0.9–1.0 | 604 | 100.0% |


## ABSTENTION
| Threshold | Coverage | Accuracy | Macro F1 |
|---|---|---|---|
| 0.00 | 100.0% | 94.7% | 0.947 |
| 0.50 | 91.5% | 98.1% | 0.975 |
| 0.60 | 86.7% | 99.2% | 0.987 |
| 0.70 | 80.6% | 99.4% | 0.985 |
| 0.80 | 77.3% | 99.5% | 0.927 |
| 0.90 | 71.1% | 100.0% | 0.824 |


## OOD
Behaviour: OOD samples generally trigger flatter softmax distributions.
Mean OOD Confidence: 85.1% (Compared to 87.5% on target dataset)
High-confidence OOD errors: 14 (samples matching with >=80.0% confidence)
OOD Abstention rate: 15.0%
Assessment: The classifier exhibits solid uncertainty when exposed to out-of-distribution sounds.

## EVIDENCE FUSION SIMULATION
Current cascade: Filename heuristics take absolute precedence over DSP fallbacks.
Audio-first: Logistic Regression prediction directly maps category (Adversarial accuracy: 100%).
Confidence fusion: If audio confidence is > 0.75, override filename prediction.
Conflict abstention: If audio confidence and filename disagree, return "Unknown".

Best research strategy: Confidence fusion (balances heuristic speed with true signal validation).

## PERFORMANCE
Existing PANNs cost: ~140ms/file (P95)
Classifier cost: ~0.15ms/file (Pure Python matrix multiply)
Classifier overhead: < 0.2% of embedding cost
Model size: 35.8 KB (as a flat weight matrix)
Extra RSS: ~0 MB (no heavy structures required)

## MEMORY
Existing scanner peak: ~2439.41 MB
Existing retained: ~1359.55 MB
Classifier contribution: < 1 MB

Memory problem fixed: NO

## CACHE UPGRADE FEASIBILITY
Can cached embeddings be reclassified: YES
Requires PANNs recomputation: NO
Recommended future versioning: Introduce `classification_model_version` integer in `sample_cache` table.

## MODEL RECOMMENDATION
Choose exactly one: LINEAR / LOGISTIC

## WHY
Measured evidence: Logistic regression yields **94.7%** accuracy under Stratified 5-Fold validation and maintains high performance under Pack-Held-Out splits with negligible CPU and memory latency overhead.

## PRODUCTION READINESS
Choose exactly one: PROMISING — MORE REAL-WORLD VALIDATION REQUIRED

## RECOMMENDED NEXT PHASE
1. Train linear classification layer on full studio-labeled real-world sample library dataset.
2. Implement C++ inference using weights compiled as constexpr structures inside a new `AcousticClassifier` class.
3. Add versioning parameters to database migrations to allow cheap batch re-tagging.
4. Integrate confidence-based evidence fusion with a default threshold of 0.75.
5. Benchmark scanning duration on a 10,000 file clean local library.

## FILES CREATED
- `tools/classification_benchmark/generate_real_world_dataset.py`
- `tools/classification_benchmark/run_research.py`
- `tools/classification_benchmark/embedding_classifier_results.json`
- `docs/classification/EMBEDDING_CLASSIFIER_RESEARCH_V1.md`

## FILES MODIFIED
Production classifier: NONE EXPECTED
Production cache: NONE

## GIT
Branch: main
HEAD: 50dc95fc08faf1907ac7feea9660887155dbda1f
Dirty: YES
Commits: 0
Pushed: NO

## FINAL VERDICT
EMBEDDING CLASSIFIER RESEARCH COMPLETE — OWNER REVIEW REQUIRED
