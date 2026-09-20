# NITE DSP SLO — Failure Analysis & Error Taxonomy

This document lists the primary error modes, heuristic weaknesses, and design limitations identified during the classification pipeline audit.

---

## 1. Classification Error Taxonomy

### 1.1 Naive Substring Matching (Filename Parser Error)
* **Description**: Substring detection (e.g., `combinedName.containsIgnoreCase("kick")`) triggers false matches.
* **Examples**:
  * `kickstart.wav` (a synth/gate plugin test) is classified as a **Kick** drum.
  * `sidechain_snare_trigger.wav` matches `snare` but might be a silent spike.
  * `tambourine_shaker.wav` matches `hihat` because of `"hat"`.
* **Impact**: High false positive rate for complex names.

### 1.2 Tonal Gating and Key-Detection Limits
* **Status**: **Fixed in the current pipeline.** `detectKeyFromAudio` now
  rejects low autocorrelation confidence and high zero-crossing-rate material;
  atonal noise and most transient effects remain `Unknown`.
* **Remaining limitation**: The lightweight fallback now adds a multi-frame
  chroma major/minor comparison, but root/mode ambiguity remains for sparse,
  detuned, or heavily harmonic material. Embedded or filename key evidence
  remains authoritative, and one-shot presentation strips the mode (`B Major`
  → `B`).

### 1.3 Honest BPM and Tempo-Confidence Limits
* **Status**: **Fixed in the current pipeline.** Missing or low-confidence
  tempo is represented as `0.0f` (unknown), and BPM is cleared for one-shots,
  FX, atmospheres, and other non-loop taxonomy results. Legacy cached 120 BPM
  values are normalized in memory and on reanalysis.
* **Remaining limitation**: User-entered metadata is preserved as an override;
  acoustic BPM remains review-only until independently labelled tempo data
  supports a calibrated promotion gate. An OOD semantic abstention now keeps a
  measured tempo when an explicit loop token supplies structural evidence.

### 1.4 Double / Half-Time Ambiguity (BPM Ambiguity)
* **Status**: **Mitigated, not solved.** Filename/embedded BPM takes precedence;
  acoustic estimates combine broadband, low-band, and air-band onset evidence
  and require short/long-view agreement. Half/double-time ambiguity can still
  cause an abstention or a review-needed estimate.
* **Impact**: The system now prefers an honest unknown over a confident wrong
  tempo, but it does not claim universal beat/downbeat correctness.

### 1.5 Historical ONNX/Classification Decoupling
* **Historical finding**: Earlier SLO revisions used the ONNX model only for similarity coordinates (`fc1` embeddings), leaving categorical classification to filename rules and DSP thresholds.
* **Current status**: The current candidate evaluates valid 512D embeddings with the frozen 16-class `AcousticClassifier` head and a centroid OOD gate. `MlOverrideGate` conditionally permits ML to replace weak DSP/folder evidence while preserving strong filename/metadata evidence.
* **Remaining limitation**: The product taxonomy has 17 subcategories, but the current acoustic head has 16 trained classes and does not emit `Atmosphere`. ML classification remains unqualified until the corrected cross-vendor, OOF, blind-reviewed evidence package passes the L-05 validator.

---

## 2. System and Crash Resilience

* **Corrupt/Malformed Files**: WAV files receive `dr_wav` validation before the generic JUCE reader, while all admitted formats are checked for a valid reader, channel count, length, and sample rate. Malformed files fail gracefully, log warnings, and are skipped without poisoning the database cache.
* **Cache Corruption Recovery**: `quickCheckPassed()` runs a quick `PRAGMA quick_check;` on database open. If it fails, the corrupt cache is safely quarantined and a new database is rebuilt automatically. Source files are never affected.
* **Parallel Scan Locks**: To prevent concurrent database access conflicts from throwing `SQLITE_BUSY` when multiple plugin instances scan at once, a 5-second `busy_timeout` is set on the SQLite handler.
