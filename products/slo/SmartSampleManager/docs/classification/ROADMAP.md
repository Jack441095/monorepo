# NITE DSP SLO — Classification Intelligence Roadmap

This document outlines the phased roadmap for rolling out classification and metadata intelligence improvements in SLO.

---

## Phase 0: Correctness & Dead-Weight Removal (P0 / Size: S)
* **Goal**: Fix bugs, remove performance bottlenecks, and align naming matches.
* **Tasks**:
  1. **QW-01**: Disable the unused mel-spectrogram calculation inside `prepareFile()`.
  2. **QW-03**: Upgrade the heuristic name parser to be token/boundary-aware (resolves false matches like `kickstart.wav`).
  3. **QW-04**: Harmonize the "Hat" subcategory to "Hi-Hat" inside `AbletonTaxonomy.cpp`.

---

## Phase 1: Music Intelligence Hardening (P1 / Size: M)
* **Goal**: Prevent musically incorrect metadata assignments and optimize start-up speed.
* **Tasks**:
  1. **QW-02**: Add a ZCR-based tonal gate before key detection to prevent F# Major labels on white noise.
  2. **UMAP Persistence**: Verify and leverage SQLite caching of `umap_x`/`umap_y` coordinates to skip the expensive O(N) UMAP epoch calculation on launch.
  3. **Golden Set Deployment**: Establish the 1,400-file benchmark dataset in local unit tests.

---

## Phase 2: Search & Tag Enhancements (P2 / Size: L)
* **Goal**: Expand search functionality and tag vocabulary.
* **Tasks**:
  1. **Secondary Tags Expansion**: Introduce confidence-based secondary tags (e.g. "Punchy", "Bright") based on crest factor and spectral centroid thresholds.
  2. **Multi-Label Class Support**: Allow files to map to a primary category while carrying multiple secondary metadata filters.
  3. **Near-Duplicate Grouping Optimization**: Improve the O(N^2) HNSW near-duplicate comparison speed for larger libraries.

---

## Phase 3: Machine Learning & Active Learning (P3 / Size: XL)
* **Status**: Partially implemented in the current candidate; runtime integration exists, but qualification and active-learning evidence remain open.
* **Goal**: Train lightweight classifiers and learn from user overrides without overstating coverage.
* **Tasks**:
  1. **Lightweight Classification Head**: The current candidate uses a frozen 16-class linear head on top of 512D embeddings. Complete the separately tracked L-05 evidence package and decide whether a future trained head should cover the full 17-class taxonomy; do not replace evidence-bounded heuristics by assumption.
  2. **Local User Correction Feedback Loop**: Save user overrides to refine local rules and provide feedback to future model training.
  3. **Opt-in Privacy-Safe Telemetry**: Support sharing anonymized user correction logs (excluding actual audio files) to improve the global taxonomy dataset.
