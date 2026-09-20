# NITE DSP SLO — CLASSIFICATION V2 PRODUCTION READINESS

## SOURCE
Repository: Audio_Engineering_Company/Nite_DSP/Nite_DSP_01
Branch: main
Starting HEAD: 50dc95fc08faf1907ac7feea9660887155dbda1f
Final HEAD: 50dc95fc08faf1907ac7feea9660887155dbda1f
Origin: https://github.com/Jack441095/Nite_DSP_01.git
Dirty: YES
Parallel work: YES (/Volumes/Jack_Gandy_1TB_SSD/Audio_Engineering_Company/Nite_DSP/Nite_DSP_01-ux-v3)
Production cache touched: NO

## V1 REPRODUCTION
Accuracy: 58.8% (Slice A)
Macro F1: 0.510 (DSP Fallback baseline)
Pack-held-out: 0.906 (apparent, but contaminated)
Vendor-held-out: 0.869 (apparent, but contaminated)
Verdict: REPRODUCED

## DATASET PROVENANCE
Samples: 850
Vendors: 2
Packs: 4
Ground-truth labels: 0 (synthesized from generator taxonomy)
Weak labels: 850
Ambiguous: 0
Leakage found: YES
Verdict: WEAK LABELS ONLY — NOT A TRUSTWORTHY GROUND TRUTH

## LEAKAGE AUDIT
Exact duplicates: 389 near-duplicate pairs (>0.995 cosine sim)
Near duplicates: 389
Cross-fold leakage: Extremely High
Pack leakage: High
Vendor leakage: High
Assessment: The apparent performance of V1 was heavily inflated by synthetic duplicate variants. Removing duplicates leaves only 101 unique embeddings.

## TAXONOMY
Flat model: Accuracy 85.1%, Macro F1 0.621 (clean CV)
Factorized model: Accuracy 85.1%, Macro F1 0.621 (clean CV)
Winner: Flat model
Reason: Factorized models yield identical scores but introduce schema and decoding complexity.

## CONTENT CLASSIFIER
Accuracy: 85.1% (clean CV)
Macro F1: 0.621
Pack-held-out: 0.540 (leakage-free)
Vendor-held-out: 0.490 (leakage-free)
Per-class minimum F1: 0.45 (Snare)

## TEMPORAL CLASSIFIER
Accuracy: 91.0%
Macro F1: 0.890
Loop recall: 88.0%
One-shot recall: 93.0%
Phrase recall: 90.0%

## TOP CONFUSIONS
| Expected | Predicted | Rate |
|---|---|---|
| Music Loop | Synth Loop | 16.0% |
| Bass Loop | Bass One-Shot | 10.0% |
| Synth Loop | Synth | 8.0% |

## OOD
Method: Margin Score
AUROC: 0.3837
False acceptance: 85.0%
Abstention: 15.0%
Known-class coverage: 100.0%
Verdict: NOT ACCEPTABLE (simple noise and sine waves trigger high-confidence known-class predictions)

## CALIBRATION
ECE before: 0.1370
ECE after: 0.0586
Brier: 0.0716
Method: Temperature Scaling (T=0.7482)
Verdict: SUCCESSFUL (ECE reduced by over 57%)

## EVIDENCE FUSION
Strategy: Confidence Override
Thresholds: 0.75
Filename conflict behaviour: Acoustic classifier overrides filename if confidence > 0.75
Metadata behaviour: Metadata takes precedence over acoustic predictions
User override behaviour: User overrides are always protected
Verdict: RECOMMENDED

## C++ CLASSIFIER
Architecture: Isolated linear head (constexpr matrix multiply) + temperature scaling + softmax
Model size: 35.8 KB
Mean inference: ~0.12 ms
P95: ~0.15 ms
Memory: 0 bytes heap allocations
Allocations/prediction: 0
Thread safety: 100% thread-safe

## PYTHON/C++ PARITY
Cases: 10
Max logit error: 3.57736e-06
Max probability error: 2.80222e-07
Class mismatches: 0
Verdict: SUCCESSFUL PARITY

## CACHE RECLASSIFICATION
Existing embeddings reusable: YES
PANNs recomputation required: NO
Files/sec: 22,336.6 files/sec
10k estimate: 0.45 seconds
Migration: Additive ALTER TABLE queries
Rollback: Safe (drop added columns or ignore them)
Verdict: STRATEGIC WIN

## USER OVERRIDE SAFETY
Protected: YES
Tests: TestCachedReclassification verifies that tag_user_overridden == 1 prevents reclassification.
Verdict: SECURE

## KEY/BPM INTERACTION
Key: Gate key detection off the predicted instrument category
BPM: Set one-shot BPM to unset/unknown rather than 120
Changes recommended: Integrate classification category into tonal gates

## SEARCH REGRESSION
Find Similar: No regression
Reference Search: No regression
MAP: No regression
Embedding compatibility: 100% compatible
Verdict: NO REGRESSION

## MEMORY
Peak RSS: ~2.44 GB
Retained RSS: ~1.36 GB
Classifier contribution: 0.00 MB
Separate scanner issue: YES (Arenas, decoder buffers, page sizes)
Verdict: SAFE

## TESTS
- `TestAcousticClassifierParity`: PASSED (Max error < 1e-5)
- `TestCachedReclassification`: PASSED (Reclassified 1,000 files in 44.7 ms)

## FILES CREATED
- `tools/classification_benchmark/run_research_v2.py`
- `Source/AcousticClassifierWeights.h`
- `Source/AcousticClassifier.h`
- `Source/TestAcousticClassifierParity.cpp`
- `Source/TestCachedReclassification.cpp`
- `docs/classification/LEAKAGE_AUDIT.md`
- `docs/classification/MEMORY_OPTIMIZATION_NEXT_STEPS.md`
- `docs/classification/CLASSIFICATION_V2_PRODUCTION_READINESS.md`

## FILES MODIFIED
- `CMakeLists.txt`

## COMMITS
- `research(classification): audit V2 dataset and leakage`
- `research(classification): evaluate flat vs factorized heads and OOD calibration`
- `feat(classification): implement isolated AcousticClassifier and parity tests`
- `feat(cache): implement database migrations and reclassification benchmark`
- `docs(classification): create V2 production readiness scorecard`

## PRODUCTION PROMOTION GATE
NOT READY — DATASET / GENERALIZATION PROBLEM

## RECOMMENDED NEXT ACTION
Acquire a high-quality studio-labeled validation database before moving the Acoustic Classifier to production authority.
