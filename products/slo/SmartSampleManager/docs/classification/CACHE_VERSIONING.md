# NITE DSP SLO — Cache Versioning & Invalidation

This document details how SLO detects and handles stale classifications, embeddings, and layouts in its SQLite cache.

---

## 1. Version Identifiers
The system maintains four independent version domains to ensure that changes in one module do not force redundant computations in another:

* **`kFeatureAnalysisVersion`** (Current: `6`): Tracks the DSP feature extraction algorithms in `analyzeAudioProperties()` and the format-aware metadata evidence contract in `readAudioMetadata()`. Version 6 adds conservative chroma major/minor key-mode detection; stale rows are selectively refreshed without re-embedding.
* **`kEmbeddingModelVersion`** (Current: `1`): Tracks the ONNX model graph structure and weights (`panns_cnn10_embedding.onnx`).
* **`AbletonTaxonomy::kTaxonomyVersion`** (Current: `4`): Tracks the rules mapping `instrumentType` and features onto Categories/Subcategories in `AbletonTaxonomy.cpp` (including the Vocal tempo-marker loop signal).
* **`kUmapLayoutVersion`** (Current: `1`): Tracks UMAP dimensions and projection space.

---

## 2. Invalidation & Selective Update Matrix

On app startup or during a rescan, the system checks version columns for each file record:

| Version Condition | Action Taken | Operational Impact |
| :--- | :--- | :--- |
| **All Versions Current** | Load directly from Cache | **Maximum Performance**: Zero audio decoding, zero ONNX runtime overhead. |
| **`embeddingModelVersion` Stale** | Reject Cache Row | **Full Scan**: Decodes audio, re-runs ONNX model inference, re-calculates all features. |
| **`featureVersion` Stale** | `lightReanalyzeFile` | **Selective Re-Analysis**: Reread format-aware metadata, recompute native DSP features, and reuse the existing ONNX embedding; user overrides remain frozen. |
| **`taxonomyVersion` Stale** | `lightReanalyzeFile` | **Selective Re-Analysis**: Re-evaluate classification rules, reuse existing ONNX embedding. |
| **`umap_layout_version` Stale** | `UPDATE sample_cache SET umap_x = NULL, umap_y = NULL` | **Wipe Coordinate Cache**: Wipes all 2D coordinates on launch, triggers a full UMAP recompute, keeps HNSW index and embeddings. |

---

## 3. User Correction Protection

* **Constraint**: User-corrected category, subcategory, or secondary tags (flagged as `tagUserOverridden = 1` or `tagSource = "user"`) are **never** overwritten by automatic scans, even if a version mismatch is detected.
* **Reset**: The user must explicitly press "Reset to Auto" to clear the override and reset `taxonomyVersion` to `0`, allowing the heuristic classifier to recompute.
