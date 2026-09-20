# NITE DSP SLO — Quick Wins Analysis

This document identifies high-gain, low-risk quick wins that can be implemented in the classification pipeline without retraining neural networks or rewriting database schemas.

---

## 1. Quick-Win Matrix

| ID | Description | Expected Gain | Risk | Effort | Target Test |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **QW-01** | **Disable Unused Mel-Spectrogram Calculation** | Reduces CPU overhead and **speeds up cold scans by 5-10%**. | None | S (Delete 3 lines of dead code) | `BenchmarkScan` |
| **QW-02** | **Tonal Gating for Key Detection** | Prevents atonal SFX/drums from receiving false pitch assignments (e.g., F# Major). | Low | S (Add threshold check on ZCR/Flatness) | `TestKeyDetection` |
| **QW-03** | **Boundary-Aware Filename Parsing** | Prevents false positives like `kickstart.wav` getting classified as "Kick". | Medium | M (Regex boundary matching `\bkick\b`) | `TestFilenameClassification` |
| **QW-04** | **Harmonize Hat Taxonomy** | Resolves the naming mismatch mapping "Hi-Hat" type to subcategory "Hat" to keep search canonical. | Low | S (Change mapping string in `AbletonTaxonomy.cpp`) | `TestTaxonomy` |

---

## 2. Technical Details for Quick Wins

### QW-01: Remove Mel-Spectrogram Computation
In `SampleManagerEngine.cpp` around line 2314:
```cpp
// 3. Compute Mel Spectrogram (Optional features demonstration)
int frames = 0;
int melBins = 0;
std::vector<float> melSpec = computeMelSpectrogram(audioWaveform, targetRate, frames, melBins);
```
This mel-spectrogram is calculated for every scanned file but the variable `melSpec` goes out of scope and is **never used**. Removing this computation saves substantial CPU work.

### QW-02: Tonal Gate Check
In `SampleManagerEngine.cpp` around line 2207:
```cpp
// Add a simple flatness/harmonicity/ZCR gate
if (taxonomyFeatures.zcr > 0.35f || taxonomyFeatures.highEnergyRatio > 0.65f) {
    loadedSample.key = "Unknown"; // Atonal
} else {
    loadedSample.key = detectKeyFromAudio(audioWaveform.data(), ...);
}
```
Only run the key estimator on pitched sounds.

### QW-03: Boundary-Aware Parsing
Replace naive `containsIgnoreCase` calls in filename heuristics with word-boundary matches or structured token lists to avoid substring errors (e.g., `kickstart` vs `kick`).
