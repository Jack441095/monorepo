# NITE DSP SLO — Audio Feature Inventory

This document details the complete set of DSP features extracted from audio samples during scanning.

---

## 1. Classification & Loop Heuristic Features (`AudioFeatures`)
These features are calculated on-the-fly inside the parallel queue worker thread (`prepareFile()`), specifically using a 32kHz down-sampled monophonic representation of the audio buffer (padded/truncated to 5 seconds).

### 1.1 Zero Crossing Rate (ZCR)
* **Definition**: The rate of sign changes in the audio waveform divided by the number of samples.
* **Units**: Crossings per sample.
* **Computational Cost**: Extremely low (single pass).
* **Usage**: Gating high-frequency noise vs tonal content. Used to identify hi-hats (ZCR > 0.3), snares/claps (ZCR > 0.18), and to classify noise-like atmospheres vs tonal loops.

### 1.2 Decay Time
* **Definition**: Time taken for the absolute amplitude envelope to decay from its maximum peak value to 10% of that peak value.
* **Units**: Seconds.
* **Computational Cost**: Low (single pass for envelope search).
* **Usage**: Primary metric for loop vs. one-shot classification. Short decay (< 0.28s to 0.32s) correlates to one-shot hits (kick, hi-hat, snare), while sustained decay (> 0.5s) maps to loop classifications.

### 1.3 lowEnergyRatio & highEnergyRatio
* **Definition**: Relative energy ratio computed by taking the absolute sum of sample-to-sample differences (high-frequency estimator) vs. averaged adjacent samples (low-frequency estimator).
* **Units**: Ratio (0 to 1).
* **Computational Cost**: Low (simple differentiator and averager).
* **Usage**:
  * `lowEnergyRatio > 0.82` identifies Kicks (when paired with fast decay).
  * `highEnergyRatio > 0.70` identifies Hi-Hats/Cymbals.
  * Used in distinguishing noise-like loops (`lowEnergyRatio < 0.5`) from tonal music loops.

### 1.4 Pitch Sweep
* **Definition**: The difference between the estimated pitch in the first 2048-sample window starting at the peak envelope and the pitch estimated in the final 2048-sample window of the analyzed waveform.
* **Units**: Hz.
* **Computational Cost**: High (autocorrelation checks across lags).
* **Usage**: Positively sweeps identify downwards pitched pitch-drops like lasers (`pitchSweep > 150.0`).

---

## 2. Native-Resolution Metadata Features (`AudioAnalysisResult`)
These features are extracted using the original native resolution of the file (e.g. 44.1kHz, 24-bit stereo) during `analyzeAudioProperties()`, bypass target-rate resamplers, and are persisted directly to the SQLite cache DB.

| Feature Name | Type | Unit | Range | Usage |
| :--- | :--- | :--- | :--- | :--- |
| `peakAmplitude` | `float` | Linear | `(0.0, 1.0]` | Visual representation and validation |
| `rmsAmplitude` | `float` | Linear | `[0.0, peak]` | Overall loudness and energy measurement |
| `zeroCrossingRate`| `float` | Crossings/sample| `[0, 1]` | Timbre refinement (noiseShift) and "Noisy"/"Tonal" tagging |
| `crestFactor` | `float` | Linear ratio | `[1.0, inf)` | Punchiness search weighting, "Punchy" tagging |
| `onsetCount` | `int` | Count | `[0, inf)` | Transient density search weighting, "Transient" tagging |
| `spectralCentroid`| `float` | Hz | `[0, SR/2]` | Brightness search weighting, "Bright"/"Dark" tagging |
| `spectralRolloff` | `float` | Hz | `[0, SR/2]` | High-frequency boundary (85% energy) estimation |
| `originalSampleRate`|`double` | Hz | `[0, inf)` | Audio file diagnostics and metadata |
| `originalChannels`| `int` | Channels | `[1, inf)` | Multi-channel diagnostics |
| `originalBitDepth`| `int` | Bits/sample | `[0, inf)` | Bit-depth diagnostics |

---

## 3. Unused Features in Classification
* The native-resolution features (`AudioAnalysisResult`) are **not** consumed by the primary classifier (`AbletonTaxonomy::classify`), which relies strictly on the resampled 32kHz `AudioFeatures` buffer.
* Instead, native features drive:
  1. Reranking in weighted similarity searches (`findSimilarWeighted` & `findSimilarRefined`).
  2. Filter matching in **Smart Collections**.
  3. Feature attribute tagging in **Auto-Tagging** (e.g., adding "Bright" or "Dark" based on spectral centroid thresholds).
