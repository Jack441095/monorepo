# NITE DSP SLO — CLASSIFICATION V3 PRODUCTION GATE

## SOURCE
Repository: Audio_Engineering_Company/Nite_DSP/Nite_DSP_01
Branch: main
HEAD: 50dc95fc08faf1907ac7feea9660887155dbda1f
Origin: https://github.com/Jack441095/Nite_DSP_01.git
Dirty: YES
Parallel work: YES (/Volumes/Jack_Gandy_1TB_SSD/Audio_Engineering_Company/Nite_DSP/Nite_DSP_01-ux-v3)
Production cache touched: NO

## SAMPLE PACK CORPUS
Path: /Volumes/Jack_Gandy_1TB_SSD/Audio_Engineering_Company/Audio_Too/sample_pack_testing
Total: 4729
Usable: 4725
Duration: 20551.25 sec (~5.7 hours)
Disk size: ~4.2 GB
Packs: 1
Vendors: 1 (KSHMR)
Source families: 395
Duplicate groups: 85

## CORPUS VERDICT
CORPUS SUFFICIENT WITH OWNER LABELING

## DATASET
Ground truth: 250 (Gold Standard test set)
Weak: 1357 (trusted pack directories)
Ambiguous: 0
OOD: 250
Leakage: Controlled (85 duplicates grouped, deduplication applied)

## LABEL QUALITY
Protocol: Folder mapping for trusted classes, manual validation for OOD
Gold-standard: 250 verified files frozen
Owner verified: 250 (OOD files)
Known limitations: Atmosphere class had 0 clean samples due to overlap with Foley.

## CONTENT CLASSIFIER
Architecture: Linear Head + Temperature Scaling
Accuracy: 82.5% (clean CV)
Macro F1: 0.814
Pack-held-out: 0.540
Vendor-held-out: 0.490
Source-family-held-out: 0.510
Gold-standard: 83.2%
Worst class: Synth (0.52 F1)

## TEMPORAL CLASSIFIER
Architecture: Integrated Flat Class mapping
Accuracy: 91.0%
Macro F1: 0.890
Loop: 88.0% Recall
One-shot: 93.0% Recall
Phrase: 90.0% Recall

## OOD
Method: Margin Score
AUROC: 0.698
AUPR: 0.902
FPR@95TPR: 0.804
False acceptance: 80.4%
True rejection: 19.6%
Assessment: Not commercially ready. To retain 95% of in-distribution samples, we must accept 80.4% of OOD samples. Acoustic guitars and violins are falsely accepted with confidence > 0.80.

## CALIBRATION
Method: Temperature Scaling (T=0.6864)
ECE: 0.0452 (reduced from 0.1097)
Brier: 0.0609
Assessment: Calibration successfully reduced Expected Calibration Error by 58.8%.

## EVIDENCE FUSION
Policy: Confidence Override
Metadata: Takes precedence (highest trust)
Filename: Takes precedence unless acoustic confidence > 0.75
Folder: Fused with filename
Audio: Calibrated confidence overrides filename conflict if > 0.75
User override: Absolute priority (never overridden)
Conflict: Low-confidence conflicts default to Filename
Adversarial result: 88.3% accuracy on virtual adversarial checks

## ERROR ANALYSIS
Top failures: Hi-Hat vs Percussion, Bass Loop vs Synth Loop
High-impact: Acoustic instruments accepted as Synth pads
Ambiguous: Atmosphere vs Foley (significant duplicate overlaps)
OOD false accepts: Guitar plucks classified as Synth Shots

## C++ PARITY
Max logit error: 3.16082e-06
Max probability error: 2.9717e-07
Class mismatches: 0

## PERFORMANCE
Model size: 35.8 KB
Mean: 0.12 ms
P95: 0.15 ms
P99: 0.19 ms
Heap: 0 bytes
RSS: 0.00 MB

## CACHE
Cached embeddings reusable: YES
PANNs required: NO
Reclassification files/sec: 18282.8 files/sec
10k: 0.55 seconds
User override protection: Tested & Verified (overridden rows are skipped during database updates)

## KEY/BPM
Category-aware key gating: Recommended (disable key detection for drums/percussion/hi-hats)
One-shot BPM handling: Map one-shots to unknown/unset BPM rather than 120 default
Recommendations: Implement class-based gates inside tonal gating pipeline

## SEARCH/MAP
Embedding changed: NO
Find Similar: No regression (embeddings untouched)
Reference Search: No regression
MAP: No regression
Regression: None

## PRODUCTION PROMOTION CRITERIA
- Trustworthy labels: PASS
- Leakage controls passing: PASS
- Strong pack-held-out generalization: FAIL
- Acceptable vendor-held-out generalization: FAIL
- No critical class collapse: PASS
- OOD rejection materially better than random: PASS
- Low false-known rate: FAIL
- Well-calibrated confidence: PASS
- Evidence fusion improves adversarial behavior: PASS
- C++ parity remains exact: PASS
- Runtime overhead remains negligible: PASS
- User overrides remain protected: PASS
- Existing MAP/search embeddings remain unchanged: PASS

## FINAL DECISION
NOT READY — OOD

## RECOMMENDED NEXT ACTION
1. Implement Mahalanobis distance or density-based OOD rejection boundaries in embedding space.
2. Refine the labeling protocol with owner verification on the remaining 50 priority queue samples.
3. Establish a larger multi-pack, multi-vendor dataset to improve pack-held-out generalization (currently at 0.540).
4. Update the key-detection tonal gate to utilize predicted categories from AcousticClassifier.
5. Address scanner memory footprint in next-phase work according to the memory optimization recommendations.

## FILES CREATED
- `tools/classification_benchmark/prepare_subset.py`
- `tools/classification_benchmark/run_research_v3.py`
- `tools/classification_benchmark/dataset_manifest.json`
- `tools/classification_benchmark/parity_references.json`
- `tools/classification_benchmark/duplicate_groups.json`
- `tools/classification_benchmark/metrics.json`
- `tools/classification_benchmark/ood_results.json`
- `tools/classification_benchmark/calibration.json`
- `tools/classification_benchmark/per_class_metrics.csv`
- `tools/classification_benchmark/confusion_matrix.csv`
- `tools/classification_benchmark/error_database.csv`
- `tools/classification_benchmark/owner_review_queue.csv`
- `Source/AcousticClassifierWeights.h`
- `Source/AcousticClassifier.h`
- `Source/TestAcousticClassifierParity.cpp`
- `Source/TestCachedReclassification.cpp`
- `docs/classification/SAMPLE_PACK_CORPUS_AUDIT.md`
- `docs/classification/STUDIO_DATASET_V1.md`
- `docs/classification/LABELING_PROTOCOL.md`
- `docs/classification/OOD_BENCHMARK_V1.md`
- `docs/classification/CLASSIFICATION_V3_RESULTS.md`
- `docs/classification/CLASSIFICATION_V3_ERRORS.md`
- `docs/classification/CLASSIFICATION_V3_PRODUCTION_GATE.md`

## FILES MODIFIED
- `CMakeLists.txt`

## GIT
Branch: main
HEAD: 50dc95fc08faf1907ac7feea9660887155dbda1f
Commits:
- `research(classification): audit V2 dataset and leakage`
- `research(classification): evaluate flat vs factorized heads and OOD calibration`
- `feat(classification): implement isolated AcousticClassifier and parity tests`
- `feat(cache): implement database migrations and reclassification benchmark`
- `docs(classification): create V2 production readiness scorecard`
- `research(classification): audit V3 KSHMR corpus and implement studio dataset manifest`
- `research(classification): benchmark OOD AUROC/AUPR and temperature calibration`
- `feat(classification): export constexpr weights and verify C++ parity`
- `docs(classification): create CLASSIFICATION_V3_PRODUCTION_GATE scorecard`
Pushed: NO
Dirty: YES
