# SLO V4 Hybrid — DSP Feature Parity Specification

**Date:** 2026-09-09
**Status:** ACTIVE — canonical reference for train/serve feature alignment

## Problem

The V4 Hybrid classifier (520-D = 512 PANNs + 8 DSP) shipped with a
train/serve skew: the Python dataset builder (`build_hybrid_v4_dataset.py`)
computed 8 DSP features using different definitions, windows, and sample
rates than the C++ production path (`SampleManagerEngine.cpp`
`runInferenceBatch`). Only 1 of 8 dimensions matched.

### Per-dimension skew (before fix)

| Dim | Python (trained on) | C++ (production) | Match? |
|-----|---------------------|-------------------|--------|
| 0   | `duration/10` | `durationSeconds/10` | ✅ |
| 1   | `centroid / (native_sr/2)` | `centroid / 16000` | ❌ divisor |
| 2   | spectral flatness (geo/arith mean) | `1 - crestFactor/20` | ❌ unrelated |
| 3   | ZCR over first 0.5s | ZCR over whole file | ❌ window |
| 4   | RMS over first 0.5s | RMS over whole file | ❌ window |
| 5   | `norm_duration` **duplicate of dim 0** | `decayTime/3` | ❌ bug + unrelated |
| 6   | energy fraction < 250 Hz | `1 - rolloff/20000` | ❌ unrelated |
| 7   | energy fraction > 4000 Hz | `rolloff/20000` | ❌ unrelated |

Additionally, dim 5 in the trainer was a copy-paste bug (`norm_duration`
written twice), meaning the model never received a decay feature despite
one being available. Dims 6 and 7 in C++ summed to exactly 1.0, encoding
one degree of freedom where the model expected two independent band-energy
ratios.

### Cross-validated accuracy (before fix)

- V3 (512-D, pure PANNs): OOF **70.03%** (90 epochs/fold)
- V4 Hybrid (520-D, mismatched features): OOF **68.31%** (40 epochs/fold)

The comparison was confounded by epoch count and loss function differences.

## Fix

**Decision:** Match the Python dataset builder to C++ production behaviour
(not the other way around), since the C++ path is the immovable production
runtime and its feature definitions are well-specified.

### Canonical 8-feature spec

All features computed over the **entire mono-downmixed file at native
sample rate**, matching `analyzeAudioProperties()` in
`SampleManagerEngine.cpp`.

| Dim | Name | Raw computation | Normalisation |
|-----|------|-----------------|---------------|
| 0 | `norm_duration` | total file duration (seconds) | `min(dur / 10.0, 1.0)` |
| 1 | `norm_centroid` | spectral centroid (Hz), 2048-Hann/512-hop avg | `min(centroid / 16000.0, 1.0)` |
| 2 | `norm_flatness` | crest factor = peak / RMS (linear) | `1.0 - min(crest / 20.0, 1.0)` |
| 3 | `zcr` | zero-crossing rate, `>= 0` vs `< 0` | `clamp(0.0, 1.0)` |
| 4 | `norm_rms` | RMS amplitude (linear) | `min(rms * 5.0, 1.0)` |
| 5 | `norm_decay` | envelope decay time (15ms one-pole, peak→10%) | `min(decay / 3.0, 1.0)`, fallback to `norm_duration` if ≤ 0.001 |
| 6 | `low_rolloff` | spectral rolloff (Hz), 85th percentile, Hann-avg | `1.0 - min(rolloff / 20000.0, 1.0)` |
| 7 | `high_rolloff` | (same as above) | `min(rolloff / 20000.0, 1.0)` |

**Note:** Dims 6 and 7 still encode the same scalar (spectral rolloff) as
`1 - x` and `x`. This is a known single-degree-of-freedom representation
inherited from the C++ side. It wastes one dim but doesn't harm the model
(the linear layer can learn to ignore one). Changing it would require
modifying the C++ production path, which is out of scope for this fix.

### Spectral analysis matching

Python uses the same windowed-FFT protocol as C++:
- FFT size: 2048 (order 11)
- Window: Hann
- Hop: 512 (FFT_SIZE / 4)
- Centroid: `sum(freq * |FFT|) / sum(|FFT|)` per frame, averaged
- Rolloff: bin where cumulative magnitude ≥ 85% of frame total, converted to Hz, averaged

### Envelope decay matching

Python reimplements `computeEnvelopeDecayTimeSeconds` identically:
- 15ms one-pole envelope follower (`alpha = 1 - exp(-1 / (sr * 0.015))`)
- Find envelope peak index and value
- Scan forward for first sample below 10% of peak
- Return `(decay_idx - peak_idx) / sr`

### Training protocol (matched to V3 for fair comparison)

- 5-fold stratified CV, `random_state=42`
- **90 epochs per fold** (was 40, V3 used 90)
- **130 epochs for final production fit** (was 50, V3 used 130)
- LR 1.2e-3 for folds (was 1e-3, V3 used 1.2e-3)
- LR 1e-3 for final fit (unchanged, matches V3)
- Cosine annealing T_max matches epoch count

## Files changed

- `tools/classification_benchmark/build_hybrid_v4_dataset.py` — rewritten
- `tools/classification_benchmark/train_gpu_classifier_v4.py` — epoch/LR adjustments
- `tools/classification_benchmark/retrain_v4_pipeline.sh` — convenience pipeline script
- This document

## Verification plan

After retraining:
1. Compare V4 OOF accuracy against V3 baseline (70.03%)
2. If V4 ≥ V3: export weights to C++ headers, run parity test
3. If V4 < V3: the 8 DSP dims are not helping → revert to V3 512-D and treat hybrid as a research branch

---

## Addendum (2026-09-09): a larger skew in the 512 PANNs dims

While fixing the 8 DSP dims, the 512 PANNs dims were checked too. They are
produced by two pipelines that also disagree. Measured with
`measure_panns_train_serve_skew.py` over 12 files spanning 0.5-10.8s,
reporting cosine similarity of the production embedding against the
training-pipeline embedding:

| Cause | Mean cosine | Min | Verdict |
|-------|-------------|-----|---------|
| Resampler (soxr_hq -> C++ linear, no anti-alias) | 0.9995 | 0.9965 | negligible |
| Input window (10s training -> 5s production) | 0.9365 | 0.8690 | **significant** |
| Both together (actual production) | 0.9365 | 0.8684 | **significant** |

The resampler difference was suspected to matter (the C++ path at
`SampleManagerEngine.cpp` loadAndResampleWaveform does linear interpolation
with no anti-aliasing filter, training uses librosa `soxr_hq`). Measurement
shows it does not. That concern is closed.

The window difference does matter, and has two regimes:

- **Files <= 5s** (cosine ~0.97-0.98): both pipelines contain identical
  audio; the embedding still shifts because PANNs CNN10 global-pools over
  time and the two inputs have different zero-padding ratios (padded to
  320000 vs 160000 samples).
- **Files > 5s** (cosine ~0.87-0.95): production truncates to
  `sampleLen = 160000` (5s), so audio the training embedding saw is
  discarded outright. The similarity cliff sits exactly at 5s.

### Consequence

Cross-validated accuracy is measured on training-pipeline embeddings, but
production feeds different vectors. CV accuracy therefore overstates
real-world accuracy by an unknown margin, independent of the 8 DSP dims.

### Options

1. **Re-extract training embeddings through the production pipeline**
   (5s window + linear resample). Aligns training to production exactly,
   does not change shipped latency. Cost: 21,793 ONNX inferences (cheap on
   the GPU box). Downside: long loops lose content in training too, so the
   model may be inherently weaker on them - but honestly so.
2. **Widen the C++ window to 10s.** Preserves information for long files
   but roughly doubles per-file inference cost in the shipping product.

Option 1 is the default recommendation; option 2 is a product/latency call.
Either way the two pipelines must agree, which today they do not.

---

## Results (2026-09-09)

### Ablation: do the 8 DSP features earn their place?

Same architecture, same 5-fold protocol (`random_state=42`, 90 epochs/fold,
final-model evaluation), differing only in whether the 8 DSP columns are
present. Run on GPU 1.

| Model | OOF accuracy |
|-------|--------------|
| 520-D hybrid (PANNs + 8 DSP) | **73.51%** |
| 512-D control (PANNs only)   | 71.56% |
| V3 baseline (different architecture) | 70.03% |

Isolated DSP contribution **+1.95 pp** (95% CI +1.06 to +2.84), winning in
5/5 folds, paired t=6.10, p=0.0037. Of the +3.48 pp over V3, ~+1.95 pp is
the corrected DSP features and ~+1.53 pp is the architecture. The original
mis-specified hybrid scored 68.31%, i.e. below V3 -- fixing the feature spec
was a ~3.6 pp swing.

Caveat: the 8 dims are only ~6 independent signals. `low_r`/`high_r`
correlate at -1.0000 (complements by construction) and both correlate with
`centroid` at +/-0.9625.

### Deployment-population measurement

Training labels come from filename/folder keywords; production consults ML
only when that evidence is ABSENT. Model trained on 80% of the labelled
population, then scored on two unseen sets: held-out labelled (A) vs
no-evidence files (B, n=1500 sampled from a 13,343 population).

| Metric | A held-out labelled | B no-evidence (served) |
|--------|--------------------|------------------------|
| held-out accuracy | 73.89% | unknown (needs hand labels) |
| max softmax confidence | 0.7857 | 0.7714 |
| centroid cosine | 0.9828 | 0.9634 |
| centroid cosine p5 | 0.9481 | 0.8913 |
| flagged unknown by OOD gate | 9.0% | **30.8%** |

The confidence gap is negligible (0.014): the model is as confident on the
served population as on the trained one. Only the centroid/OOD gate detects
the shift, and it flags 3.4x as many files. That gate is therefore the sole
mechanism preventing silent mass mis-tagging and must not be loosened.

Predicted class mix diverges sharply. Loop classes are over-represented in
the served population (Music Loop 9.3x, Bass Loop 8.3x, Synth Loop 5.8x)
while drum one-shots are under-represented (Hi-Hat 0.42x, Snare 0.40x) --
one-shots almost always carry a filename keyword, so ML never sees them.

**Root cause of the 30.8%:** the four rarest training classes (Music Loop
92, Vocal Loop 102, Bass Loop 117, Synth Loop 138 -- under 2% of training
data) constitute ~10% of the served population. The deficit is a training
distribution problem, not a modelling one.

### Still unmeasured

These numbers are CONFIDENCE, not correctness. Accuracy on the served
population requires hand labels; ~250 stratified no-evidence files would
establish it. Everything above remains subject to the PANNs window skew
documented in the previous addendum.
