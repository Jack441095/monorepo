# SLO CLASSIFICATION & ANALYSIS V4 — BASELINE / ROOT-CAUSE REPORT

**Date:** 2026-08-22  
**Repository:** `Nite_DSP/Nite_DSP_01`  
**Branch:** `engineering/slo-classification-analysis-v4`  
**Starting SHA:** `ab1de912361182db43a79e3801d04831c47ed1ed`  
**Author:** Principal Audio DSP & ML Systems Architect  

---

## 1. Executive Summary

This report establishes the baseline, empirical root-cause analysis, and architectural plan for **SLO Classification & Audio Analysis V4**. The primary objective is to transform Smart Sample Manager's classification from a rudimentary 6-rule heuristic ladder into a world-class, extensible, confidence-aware audio intelligence system.

Key findings of this baseline audit:
1. **Vocal Misclassification Root Cause:** `classifyAudioFeatures()` in `SampleManagerEngine.cpp` has **zero Vocal detection rules**. Short vocal chops and adlibs fall into `Snare` (due to ZCR and decay match) or `Kick` (due to low energy dominance). `AbletonTaxonomy` then maps `Snare` directly to `Drums / Snare`.
2. **Kick Overprediction:** The `Kick` rule relies on only 3 crude thresholds (`lowEnergyRatio > 0.82f`, `decayTimeSeconds < 0.28f`, `zcr < 0.12f`) without checking spectral centroid, pitch stability, or harmonicity. Low bass hits, sub shots, and low vocal grunts are frequently misclassified as Kicks.
3. **Unused Audio Features:** `analyzeAudioProperties()` extracts rich full-file features (`spectralCentroid`, `spectralRolloff`, `crestFactor`, `onsetCount`, `rmsAmplitude`), but **none of these features are used by the classification functions**.
4. **Hardcoded 120.0 BPM Fallback:** When metadata or filename parsing fails, `prepareFile()` explicitly hardcodes `loadedSample.bpm = 120.0f;`. No acoustic tempo estimation exists.
5. **Classification V3 Status:** `AcousticClassifier` V3 (512D linear head on PANNs Cnn10 embeddings) has exact C++ parity and high speed (0.12 ms/sample), but was left unwired due to 80.4% OOD false acceptance on unseen instruments and single-vendor (KSHMR) training bias.

---

## 2. Current Classification Pipeline Inventory

### 2.1 Complete Source Flow
The complete decision flow for a sample scanned by SLO:

```
[FilePath input to prepareFile] 
  │
  ├── Cache Check: tryLoadFromCache ── (Hit) ──> Selective Reanalysis if version stale
  │                                    │
  └── (Miss) ──────────────────────────┘
        │
        ├── TagLib: readWavMetadata
        ├── Decode & Resample to 32kHz 5s mono: loadAndResampleWaveform
        ├── Full File Analysis: analyzeAudioProperties -> AudioAnalysisResult
        ├── Key Detection: Filename parse -> Audio chroma fallback
        ├── BPM Resolution: Filename parse -> Hardcoded 120.0 BPM fallback
        │
        ├── instrumentType == Unknown?
        │     ├── (Yes) ──> Token Match: matchType on Filename & Parent Folder
        │     │               ├── Match Found ──> instrumentType = Token Match, winningEvidence = FILENAME/FOLDER
        │     │               └── No Match ─────> classifyAudioFeatures: 6-rule heuristic ladder
        │     │                                       └── instrumentType = Heuristic, winningEvidence = DSP
        │     └── (No) ───> winningEvidence = EMBEDDED_METADATA
        │
        └── AbletonTaxonomy::classify
              └── Assign category, subcategory, secondaryTags, tagConfidence, tagSource
```

---

## 3. Signal & Feature Inventory

| Signal / Feature | Source | Data Type | Range / Norm | Where Used | Actually Influences Classification? |
|---|---|---|---|---|---|
| `zcr` (Zero Crossing Rate) | `analyzeAudioBuffer` | `float` | `[0.0, 1.0]` | `classifyAudioFeatures`, `detectLoopVsOneShot`, `AbletonTaxonomy` | **YES** (Hi-Hat, Snare, Kick, Explosion, Loop/Ambience) |
| `lowEnergyRatio` | `analyzeAudioBuffer` | `float` | `[0.0, 1.0]` | `classifyAudioFeatures`, `AbletonTaxonomy` | **YES** (Kick, Explosion, Bass, Loop/Ambience) |
| `highEnergyRatio` | `analyzeAudioBuffer` | `float` | `[0.0, 1.0]` | `classifyAudioFeatures` | **YES** (UI, Hi-Hat) |
| `decayTimeSeconds` | `analyzeAudioBuffer` | `float` | Seconds (`>= 0.0`) | `classifyAudioFeatures`, `detectLoopVsOneShot` | **YES** (UI, Laser, Kick, Hi-Hat, Snare, Explosion, Bass, Loop) |
| `pitchSweep` | `analyzeAudioBuffer` | `float` | Hz delta | `classifyAudioFeatures` | **YES** (Laser only) |
| `peakAmplitude` | `analyzeAudioProperties` | `float` | `(0.0, 1.0]` | `SampleItem::audioFeatures` | **NO** (Stored in cache, unused in rules) |
| `rmsAmplitude` | `analyzeAudioProperties` | `float` | `(0.0, 1.0]` | `SampleItem::audioFeatures` | **NO** (Stored in cache, unused in rules) |
| `crestFactor` | `analyzeAudioProperties` | `float` | `[1.0, inf)` | `SampleItem::audioFeatures` | **NO** (Stored in cache, unused in rules) |
| `zeroCrossingRate` | `analyzeAudioProperties` | `float` | `[0.0, 1.0]` | `SampleItem::audioFeatures` | **NO** (Duplicate of `zcr` above, unused in rules) |
| `spectralCentroid` | `analyzeAudioProperties` | `float` | Hz (`0 .. Nyquist`) | `SampleItem::audioFeatures` | **NO** (Stored in cache, unused in rules) |
| `spectralRolloff` | `analyzeAudioProperties` | `float` | Hz (`0 .. Nyquist`) | `SampleItem::audioFeatures` | **NO** (Stored in cache, unused in rules) |
| `onsetCount` | `analyzeAudioProperties` | `int` | Integer (`>= 0`) | `SampleItem::audioFeatures` | **NO** (Stored in cache, unused in rules) |
| 512D PANNs Embedding | `inferenceWorker` (ONNX) | `std::vector<float>` | L2 Normalized | UMAP canvas, `TestFindSimilar` | **NO** (Unwired from production classifier) |
| Filename Tokens | `tokenizeString(name)` | `vector<string>` | Lowercase tokens | `matchType` in `prepareFile` | **YES** (When token matches in name) |
| Folder Tokens | `tokenizeString(folder)` | `vector<string>` | Lowercase tokens | `matchType` in `prepareFile` | **YES** (When token matches in parent dir) |
| Embedded Metadata | `readWavMetadata` (TagLib) | Strings/Floats | Various | `prepareFile` | **YES** (Overrides filename/DSP if present) |

---

## 4. Current Taxonomy Mapping

SLO currently implements a two-layer hybrid taxonomy:

1. **Coarse `instrumentType` (Flat):**
   - Derived in `SampleManagerEngine.cpp` via embedded metadata, filename/folder tokens, or `classifyAudioFeatures()`.
   - Supported strings: `"Kick"`, `"Snare"`, `"Hi-Hat"`, `"Clap"`, `"Percussion"`, `"Bass"`, `"Synth"`, `"Vocal"`, `"Explosion"`, `"Impact"`, `"Laser"`, `"Powerup"`, `"Jump"`, `"Coin"`, `"UI"`, `"Footstep"`, `"Loop"`, `"Other"`.

2. **Rich `AbletonTaxonomy` (Category / Subcategory / Secondary Tags):**
   - Defined in `AbletonTaxonomy.h` / `AbletonTaxonomy.cpp`.
   - Category Mapping Table:
     - `Kick` → Category: `Drums`, Subcategory: `Kick` / `Drum Loop`
     - `Snare` → Category: `Drums`, Subcategory: `Snare` / `Drum Loop`
     - `Hi-Hat` → Category: `Drums`, Subcategory: `Hi-Hat` / `Drum Loop`
     - `Clap` → Category: `Drums`, Subcategory: `Clap` / `Drum Loop`
     - `Percussion` → Category: `Drums`, Subcategory: `Percussion` / `Drum Loop`
     - `Bass` → Category: `Bass`, Subcategory: `Bass One-Shot` / `Bass Loop`
     - `Synth` → Category: `Instruments`, Subcategory: `Synth` / `Synth Loop`
     - `Vocal` → Category: `Vocals`, Subcategory: `Vocal Phrase` / `Vocal Loop`
     - `Explosion` / `Impact` → Category: `FX`, Subcategory: `Impact`
     - `Laser` → Category: `FX`, Subcategory: `Riser`
     - `Footstep` → Category: `FX`, Subcategory: `Foley`
     - `Loop` → Disambiguated by ZCR: if `zcr > 0.25` & `lowEnergyRatio < 0.5` → `Ambience / Atmosphere`, else `Instruments / Music Loop`.

---

## 5. Root Cause Analysis: Vocal Misclassified as Drums

### 5.1 Causal Decision Chain
When a Vocal sample (e.g. `Adlib_Fm_128.wav` or `Short_Vocal_Chop.wav`) is processed:

1. **TagLib Metadata:** Returns `instrumentType = "Unknown"`.
2. **Filename / Folder Match:** `matchType` checks tokens: `{"voc", "vocal", "vocals", "sing", "chant"}`.
   - For filenames containing `"adlib"`, `"vox"`, `"acapella"`, `"choir"`, `"lead"`, `"phrase"`, `"spoken"`, or `"hum"`, `matchType` returns `false`.
3. **Fallback to `classifyAudioFeatures(f, filename)`:**
   - Evaluates:
     1. UI check: `decay < 0.06 && highEnergy > 0.6`
     2. Laser check: `pitchSweep > 150 ...`
     3. Kick check: `lowEnergyRatio > 0.82 && decay < 0.28 && zcr < 0.12`
     4. Hi-Hat check: `highEnergyRatio > 0.7 && zcr > 0.3 && decay < 0.32`
     5. **Snare check:** `if (f.zcr > 0.18f && f.decayTimeSeconds >= 0.05f && f.decayTimeSeconds < 0.42f) return "Snare";`
   - **Crucial Defect:** Short vocal chops, adlibs, and spoken words typically have `decayTimeSeconds` between `0.1s` and `0.38s` and `zcr > 0.18` (due to speech sibilance and consonants). **They trigger the Snare rule!**
   - Low vocal hits or sub-vocals trigger the **Kick rule**.
   - **There is NO Vocal rule anywhere in `classifyAudioFeatures()`!**
4. **Taxonomy Cascade:** `classifyAudioFeatures()` returns `"Snare"`. `AbletonTaxonomy::classify()` receives `existingInstrumentType = "Snare"` and maps it directly to:
   - **Category: `Drums`**
   - **Subcategory: `Snare`**
   - **Result:** **VOCAL SAMPLE IS MISCLASSIFIED AS DRUMS / SNARE.**

---

## 6. Root Cause Analysis: Kick Overprediction

In `classifyAudioFeatures()`:
```cpp
if (f.lowEnergyRatio > 0.82f && f.decayTimeSeconds < 0.28f && f.zcr < 0.12f) {
    return "Kick";
}
```
Any sample with fast decay (< 0.28s), low zero-crossing rate (< 0.12), and dominant low-frequency energy (> 0.82) is classified as a `Kick`.

This captures:
- Low bass stabs / sub one-shots
- Low FX impacts
- Low vocal grunts / vocal chops
- Low tom hits / percussion

Because it lacks secondary verification (such as pitch contour stability vs percussive transient attack or spectral centroid), non-Kick samples with low energy are overpredicted as Kicks.

---

## 7. Filename Intelligence Audit

Current status in `SampleManagerEngine.cpp`:
- Active ONLY when embedded metadata is missing (`instrumentType == "Unknown"`).
- Token matching algorithm: `tokenizeString()` splits string by `_`, `-`, space, or numbers.
- **Current Token Gaps:**
  - Vocal synonyms missing: `vox`, `acapella`, `acap`, `adlib`, `lead_vocal`, `choir`, `spoken`, `phrase`, `ad_lib`.
  - Drum synonyms missing: `bd` (Kick), `sd` (Snare), `hh` (Hi-Hat), `cp` (Clap), `tom`, `rim`, `shaker`.
  - Synth / Bass synonyms missing: `808`, `sub`, `lead`, `pad`, `pluck`, `arp`, `stab`.
- Filename intelligence is effective when tokens match, but its dictionary is severely incomplete and uncentralized.

---

## 8. Classification V3 Audit

- **Algorithm:** Linear classification head ($16 \times 512$ weights + $16$ biases) on 512D PANNs Cnn10 embeddings.
- **Inputs:** 512D L2-normalized float vector.
- **Outputs:** Logit vector, temperature-scaled softmax probabilities, top-1 class, top-2 margin, OOD flag.
- **Supported Classes (16):** Bass Loop, Bass One-Shot, Clap, FX, Foley, Hi-Hat, Impact, Kick, Music Loop, Percussion, Riser, Snare, Synth, Synth Loop, Vocal Loop, Vocal Phrase.
- **Runtime & Memory:** 0.12 ms per sample, 35.8 KB memory footprint, 0 heap allocations, fully deterministic.
- **Why Unwired from Production:**
  1. **OOD Rejection Failure:** Margin-based OOD rejection had an 80.4% false acceptance rate on unseen instruments (e.g. acoustic guitars/violins).
  2. **Vendor Bias:** Trained on a single dataset (KSHMR), resulting in poor pack-held-out generalization (54% accuracy).

---

## 9. Current BPM Implementation Audit

- **Exact Source of 120.0 BPM:** Line 2783 of `SampleManagerEngine.cpp`:
  ```cpp
  if (loadedSample.bpm <= 0.0f) {
      float parsedBpm = parseBpmFromFilename(loadedSample.name);
      if (parsedBpm > 0.0f) {
          loadedSample.bpm = parsedBpm;
      } else {
          loadedSample.bpm = 120.0f; // Hardcoded fallback!
      }
  }
  ```
- **Defect:** Any audio file that lacks an explicit BPM filename token (e.g., `_128bpm_`) or ID3 BPM tag is assigned **120.0 BPM**, masquerading as a valid detection.
- **Requirement:** Unknown BPM MUST be represented as `0.0f` (or `UNKNOWN`), not a false `120.0`.

---

## 10. Proposed V4 Classification & Analysis Architecture

We propose a 4-Stage Confidence-Aware Multimodal Fusion Architecture:

```
[Input Audio + File Context] ──> [Stage 1: Enhanced Signal Extraction]
                                   │
                                   ├── Spectral Centroid, Rolloff, Crest Factor, Formant/Harmonicity Proxy
                                   ├── Tempo & Onset Strength Estimator
                                   └── Semantic Tokenizer: Expanded Synonym Dictionary
                                         │
                                         ▼
                                [Stage 2: Deterministic Acoustic Classifier]
                                         │
                                         ▼
                                [Stage 3: Multi-Evidence Fusion & Confidence Scorer]
                                         │
                                 (Confidence >= Threshold?)
                                   ├── (Yes) ──> Assign Category / Subcategory & Confidence
                                   └── (No) ───> Assign UNKNOWN / Low Confidence
```

### Stage Breakdown:
1. **Stage 1 (Feature Extraction):**
   - Utilize `spectralCentroid`, `spectralRolloff`, `crestFactor`, `zcr`, `decayTimeSeconds`, and a Formant/Harmonicity ratio to distinguish voiced vocal material and tonal synth stabs from noise-like percussive hits.
2. **Stage 2 (Refined Acoustic Rules & Vocal Branch):**
   - Add explicit **Vocal** branch:
     - Moderate ZCR (`0.08 - 0.35`), sustained/modulated decay (`> 0.15s`), mid-frequency spectral centroid (`800Hz - 4500Hz`), low crest factor (sustained voiced vowel resonance).
   - Refine **Kick** branch: Require `spectralCentroid < 400Hz` and low `zcr` to prevent sub-bass / vocal grunt false positives.
   - Refine **Snare / Clap** branch: Require high crest factor / sharp attack onset.
3. **Stage 3 (Centralized Semantic Dictionary):**
   - Centralize filename/directory token matching with complete industry synonyms (`vox`, `acap`, `adlib`, `bd`, `sd`, `hh`, `808`, etc.).
4. **Stage 4 (Confidence & OOD Handling):**
   - Compute honest confidence $C \in [0.0, 1.0]$. If acoustic evidence and semantic evidence strongly conflict, flag as `UNKNOWN` or assign reduced confidence instead of forcing a false category.
5. **Stage 5 (Honest BPM Analysis):**
   - Implement onset-autocorrelation tempo estimation for loops.
   - Remove hardcoded `120.0f` default; return `0.0f` for one-shots and low-confidence tempo analysis.

---

## 11. Proposed Implementation Stages

| Stage | Goal | Key Deliverables | Risk Level |
|---|---|---|---|
| **V4-A** | Baseline & Root Cause Report | Architecture audit, root cause verification, baseline tests | Safe (Docs/Analysis) |
| **V4-B** | Fix Vocal/Drums & Kick Defect | Add Vocal DSP rule, refine Kick/Snare rules, expand filename tokens, golden regression tests | Low |
| **V4-C** | Honest BPM & OOD Infrastructure | Remove hardcoded 120.0 BPM, return 0.0 for unknown, implement confidence scoring | Low-Medium |
| **V4-D** | Classification V3 Evaluation & Fusion | Fuse `AcousticClassifier` logits with heuristic/semantic rules where valid | Medium |
| **V4-E** | Acoustic Tempo Estimator | Implement onset-autocorrelation tempo estimator for loops | Medium |

---

## 12. Verification & Regression Strategy

1. **Synthetic Golden Corpus (`tools/classification_benchmark/fixtures/`):**
   - Ensure representative WAV fixtures exist for Kick, Snare, Hi-Hat, Percussion, Bass, Synth, Vocal Loop, Vocal Phrase.
2. **Automated Qualification Suite:**
   - Execute all core test binaries:
     - `TestTaxonomy`
     - `TestAudioFeatures`
     - `TestAcousticClassifierParity`
     - `TestCacheIntegrity`
     - `TestSafetyRegression`
     - `TestPersistedCacheHydration`
     - `TestPrecisionBrowserSorting`
3. **Cache & User State Protection:**
   - Verify `tagUserOverridden` is strictly respected (re-scan must never clobber manual edits).
   - Verify `kTaxonomyVersion` and `kFeatureAnalysisVersion` handle version bumps safely without destroying cache rows.

---

## 13. Recommendation

Proceed immediately to **Stage V4-B**:
1. Implement explicit Vocal branch in `classifyAudioFeatures()`.
2. Refine Kick and Snare rules in `classifyAudioFeatures()` using spectral centroid and decay constraints.
3. Centralize and expand the filename/folder token dictionary (`matchType`).
4. Add comprehensive unit and regression tests in `test_taxonomy_main.cpp` and `test_audio_features_main.cpp`.
