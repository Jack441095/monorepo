# NITE DSP SLO — Classification Signal Map

This document presents the current classification signal matrix showing how SLO resolves conflicts and fuses multiple inputs to determine a sample's taxonomy. It describes the shipped runtime path; qualification status and evidence limitations are tracked separately in `SLO_CLASSIFICATION_L05_EVIDENCE_GAP_V1.md`.

## 1. Classification Signal Matrix

| Signal | Used? | Priority / Precedence | Source Details |
| :--- | :--- | :--- | :--- |
| **User Override** | **YES** | **1 (Highest)** | Explicit user tagging in the UI. Overwrites and freezes all downstream classification fields. |
| **Existing Metadata (TagLib)**| **YES, format-aware**| **2** | WAV uses the project-specific RIFF/WAV ID3 path; other admitted formats use recognized TagLib `PropertyMap` keys for BPM, key, and instrument metadata, then fall through safely when unavailable. |
| **Filename & Path Heuristics**| **YES**| **3** | RegEx-like substring searches on `filename + "_" + parentFolder` (e.g., looking for "kick", "snare", etc.). |
| **DSP Audio Features** | **YES** | **4** | Heuristic rules run on ZCR, decay, energy ratio, and pitch sweep if no metadata or filename matches are found. |
| **Audio ML (ONNX) + acoustic head** | **YES, conditionally** | **After heuristic baseline; gated by confidence/OOD and evidence tier** | PANNs CNN10 produces a 512D embedding. The frozen 16-class linear head maps valid embeddings to taxonomy labels where `MlOverrideGate` permits it; the centroid gate can produce explicit OOD abstention. |
| **Embedding Neighbors** | **NO** | **N/A** | Nearest neighbors in the HNSW index do not currently participate in primary category prediction. |

---

## 2. Multi-Signal Evidence Fusion Policy

SLO uses a staged evidence cascade followed by a conditional acoustic-ML gate. It does not claim that every signal is probabilistically fused into one calibrated 17-class model:

```
        [User Override Present?]
               /        \
             YES         NO
             /            \
  [Keep Existing User]    [Embedded Metadata Found?]
                               /             \
                             YES              NO
                             /                 \
                     [Use TagLib Value]   [Filename/Folder Match?]
                                                /          \
                                              YES           NO
                                              /              \
                                   [Use Heuristics]    [Run DSP Classifier]
```

* **ML override policy**: A non-OOD result at or above the current confidence threshold may replace DSP/folder evidence; embedded metadata and strong filename evidence remain authoritative. An OOD result clears an untrusted derived label and is presented as `Needs review` / `Unknown Other`.
* **Loop/One-shot Fusion**: The category is refined by combining the resolved class from the above cascade with a separate loop-vs-one-shot DSP heuristic (`detectLoopVsOneShot`).
* **17-class limitation**: The product taxonomy has 17 subcategories. The current acoustic head has 16 trained classes and does not emit `Atmosphere`; Atmosphere is available only through the heuristic taxonomy path and is explicitly weak-class/qualification-gated.
* **BPM Fusion**:
  1. Priority 1: Reads embedded metadata via TagLib.
  2. Priority 2: Parses explicit filename BPM markers and the strict
     loop-plus-key convention (for example `Loop_01_160_C#`).
  3. Priority 3: Runs the multi-band acoustic estimator. For files longer than
     the true decoded duration capped at five seconds, a second view capped at
     20 seconds must agree within 2 BPM; model-padding silence is excluded
     from the short view. Otherwise BPM remains unknown (`0.0f`). BPM is
     retained only for loop-like taxonomy results, unless a user override is
     active.
* **Key Fusion**:
  1. Priority 1: Reads embedded metadata via TagLib.
  2. Priority 2: RegEx parses the filename for keys.
  3. Priority 3: Runs a DSP-based key estimator (`detectKeyFromAudio`) using
     autocorrelation pitch plus a conservative multi-frame chroma major/minor
     comparison; isolated one-note material keeps the pitch as the useful
     result and does not imply a musically certain mode.
