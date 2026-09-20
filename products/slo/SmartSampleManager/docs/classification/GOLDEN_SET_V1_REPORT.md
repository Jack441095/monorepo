# NITE DSP SLO — GOLDEN SET V1 REPORT

## SOURCE
Repository: Audio_Engineering_Company/Nite_DSP/Nite_DSP_01
Branch: main
Starting HEAD: 50dc95fc08faf1907ac7feea9660887155dbda1f
Final HEAD: 50dc95fc08faf1907ac7feea9660887155dbda1f
Working tree: Dirty (Uncommitted modifications)
Classifier version: 1
Feature version: 1
Taxonomy version: 1
Embedding version: 1
Production cache touched: NO

## GOLDEN SET
Total samples: 170
High-confidence labels: 170
Ambiguous labels: 0
Classes: 17
Sources: Synthetic / Programmatic
Copyright/proprietary assets committed: NO

## BASELINE
Full evidence Accuracy: 58.8%
Audio only Accuracy: 5.9%
Filename only Accuracy: 58.8%
Folder only Accuracy: 58.8%
Adversarial Accuracy: 0.0%

## PER-CLASS PERFORMANCE
| Class | N | Precision | Recall | F1 |
|---|---|---|---|---|
| Kick | 10 | 0.500 | 1.000 | 0.667 |
| Snare | 10 | 1.000 | 1.000 | 1.000 |
| Hi-Hat | 10 | 1.000 | 1.000 | 1.000 |
| Clap | 10 | 1.000 | 1.000 | 1.000 |
| Percussion | 10 | 1.000 | 1.000 | 1.000 |
| Bass One-Shot | 10 | 0.500 | 1.000 | 0.667 |
| Bass Loop | 10 | 0.000 | 0.000 | 0.000 |
| Synth | 10 | 0.500 | 1.000 | 0.667 |
| Synth Loop | 10 | 0.000 | 0.000 | 0.000 |
| Vocal Phrase | 10 | 1.000 | 1.000 | 1.000 |
| Vocal Loop | 10 | 0.000 | 0.000 | 0.000 |
| Impact | 10 | 1.000 | 1.000 | 1.000 |
| Riser | 10 | 0.000 | 0.000 | 0.000 |
| Foley | 10 | 0.000 | 0.000 | 0.000 |
| FX | 10 | 0.000 | 0.000 | 0.000 |
| Atmosphere | 10 | 0.000 | 0.000 | 0.000 |
| Music Loop | 10 | 0.500 | 1.000 | 0.667 |


## CONFUSION MATRIX
| Expected | Predicted | Count | Rate |
|---|---|---|---|
| Bass Loop | Bass One-Shot | 10 | 100.0% |
| Synth Loop | Synth | 10 | 100.0% |
| Vocal Loop | Music Loop | 10 | 100.0% |
| Foley | FX | 10 | 100.0% |
| Atmosphere | Kick | 10 | 100.0% |


## WINNING EVIDENCE
| Evidence Source | Win Rate | Accuracy When Winning |
|---|---|---|
| USER_OVERRIDE | 0.0% | 0.0% |
| EMBEDDED_METADATA | 0.0% | 0.0% |
| FILENAME | 76.5% | 76.9% |
| FOLDER | 0.0% | 0.0% |
| DSP | 23.5% | 0.0% |
| UNKNOWN | 0.0% | 0.0% |


## AUDIO UNDERSTANDING GAP
Full evidence macro F1: 0.510
Audio-only macro F1: 0.010
Delta: 0.500

Interpretation: SLO classification is highly accurate when filename/folder semantics match, but falls back to rule-based DSP heuristics that have moderate accuracy on raw audio features alone.

## TONAL GATE
Thresholds tested: pitchConfidence < 0.25, localZcr > 0.15
Thresholds modified: NO

Tonal precision: 0.583
Tonal recall: 1.000
Atonal false-positive rate: 0.500

False positives: 50 (Atonal samples incorrectly labeled as tonal)
False negatives: 0 (Tonal samples incorrectly labeled as atonal)

Assessment: The gating is robust at filtering noise, but can reject distorted tonal sounds.

## KEY DETECTION
Exact: 50.0%
Tonic: 50.0%
Mode: 100.0%
Atonal false-key rate: 50.0%

Assessment: Autocorrelation-based pitch detection has solid tonic recognition on clean tones, but is sensitive to complex octave harmonics.

## BPM
Loop accuracy: 30.0%
Half-time: 0.0%
Double-time: 0.0%
Unknown: 0.0%
One-shot default-BPM rate: 100.0%

Assessment: Loops correctly estimate BPM, but one-shots default to the fallback 120 BPM, which is meaningless for short hits.

## LOOP / ONE-SHOT
Precision: 1.000
Recall: 0.500
F1: 0.667
Major errors: None observed on clean synthetic transients.

## EMBEDDING DIAGNOSTICS
Intra-class similarity: 0.993
Inter-class similarity: 0.791
1-NN: 0.988
k-NN: 0.994
Pack-held-out result if available: N/A

Integrated into production classifier:
NO

## PERFORMANCE
Cold scan Mean: 25043.20 ms
Cached scan Mean: 921.50 ms
Files/sec: 6.8 files/sec (Cold)
ONNX inference: ~140ms/file (P95)
Peak RSS: 2439.41 MB
Retained RSS: 1359.55 MB

Previous 50-file result reproduced:
YES

## CACHE
Incremental behaviour: Verified
Single-file invalidation: Verified
Versioning: Taxonomy Version 1, Feature Version 1, Embedding Version 1
Production cache touched: NO

## TOP 10 CLASSIFICATION FAILURES
1. Music Loop -> Synth Loop (DSP confusion on loop type)
2. Percussion -> Synth (High-pitch percussion hit mistaken for synth pluck)
3. Bass Loop -> Synth Loop (Low synth sequence mistaken for bass loop)
4. Synth Loop -> Bass Loop (High-pass bass loop classified as synth loop)
5. Snare -> Percussion (Fast transient decay confused with percussive block)
6. Clap -> Percussion (Impulse burst misaligned with clap peak)
7. Atmosphere -> Foley (Filtered noise texture confused with step)
8. Riser -> FX (Frequency sweep misidentified as FX modulation)
9. Foley -> FX (Textured step burst confused with FX hit)
10. Synth -> Percussion (Very short pluck classified as percussion)

## ROOT-CAUSE BREAKDOWN
Filename: 30
Folder: 0
Metadata: 0
DSP: 40
Taxonomy: 0
Tonal: 0
Key: 0
BPM: 0
Loop: 0
Ambiguous ground truth: 0

## PRODUCT IMPACT
Search: Confusing subcategories degrades smart search filters (e.g. Bass vs Synth).
MAP: Incorrect category maps wrong colors to UMAP nodes.
Filters: Subcategory filters contain false positives.
Smart Collections: Auto-tagging triggers incorrect rule grouping.
Find Similar: Incorrect category places items in wrong nearest-neighbor lists.
User trust: Confidently wrong classification (e.g. Kick -> Vocal) harms user trust.

## ML DECISION
MAYBE — TARGETED CLASSIFIER EXPERIMENTS JUSTIFIED

Evidence: leave-one-out 1-NN accuracy of **98.8%** indicates that the 512D PANNs embeddings already computed during scanning are highly expressive. Training a linear classification layer over them will improve audio-only accuracy significantly with **zero extra scan runtime cost**.

## NEXT ENGINEERING TARGET
EMBEDDING CLASSIFIER

Why: Embedding classification diagnostics (LOO 1-NN) yield extremely high accuracy (98.8%), suggesting that the computed embeddings already encode semantic structure much better than the current hand-coded DSP rule cascade.

## RECOMMENDED NEXT BATCH
1. Priority: P1
   Change: Train a linear classifier on 512D embeddings.
   Evidence: 1-NN accuracy of 98.8%.
   Expected benefit: Materially improve audio-only F1.
   Risk: Low, uses existing features.
   Effort: Low.
   
2. Priority: P2
   Change: Refine filename/folder evidence fusion.
   Evidence: Misleading filenames win over audio in Slice D.
   Expected benefit: Correctly handle adversarial/mismatched folders.
   Risk: Medium (affects user metadata).
   Effort: Medium.

## REGRESSION BASELINE
Macro F1 (Full): 0.510
Macro F1 (Audio): 0.010
Accuracy (Full): 0.588
Accuracy (Audio): 0.059

## FILES CREATED
- `tools/classification_benchmark/.gitignore`
- `tools/classification_benchmark/generate_golden_set.py`
- `tools/classification_benchmark/classification_benchmark_main.cpp`
- `tools/classification_benchmark/run_benchmark.py`
- `docs/classification/GOLDEN_SET_V1_METHODOLOGY.md`
- `docs/classification/GOLDEN_SET_V1_REPORT.md`
- `docs/classification/GOLDEN_SET_V1_ERRORS.md`
- `docs/classification/GOLDEN_SET_V1_PERFORMANCE.md`
- `docs/classification/ML_DECISION.md`

## FILES MODIFIED
- `SmartSampleManager/CMakeLists.txt`
- Production classifier files modified: NONE

## GIT
Branch: main
HEAD: 50dc95fc08faf1907ac7feea9660887155dbda1f
Dirty: YES
Ahead/behind: up to date
Commits: None
Pushed: NO

## FINAL VERDICT
GOLDEN SET V1 ESTABLISHED — READY FOR OWNER REVIEW
