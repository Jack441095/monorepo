# NITE DSP SLO — Benchmark Design

This document details the blueprint for a deterministic audio classification benchmarking system to evaluate accuracy, signal fusion, and performance.

---

## 1. Golden Dataset Composition
To establish a reliable baseline, the benchmark dataset requires **1,400 audio files** evenly distributed across the 14 core taxonomy classes:

| Category | Expected Subcategories | Target Count | Expected Loop/One-Shot Split |
| :--- | :--- | :--- | :--- |
| **Kick** | Kick, Drum Loop | 100 | 80 One-Shot / 20 Loop |
| **Snare** | Snare, Drum Loop | 100 | 80 One-Shot / 20 Loop |
| **Clap** | Clap, Drum Loop | 100 | 90 One-Shot / 10 Loop |
| **Hi-Hat** | Hat, Drum Loop | 100 | 70 One-Shot / 30 Loop |
| **Percussion**| Percussion, Drum Loop | 100 | 60 One-Shot / 40 Loop |
| **Bass** | Bass One-Shot, Bass Loop | 100 | 40 One-Shot / 60 Loop |
| **Lead** | Synth, Synth Loop | 100 | 50 One-Shot / 50 Loop |
| **Pad** | Synth, Synth Loop | 100 | 20 One-Shot / 80 Loop |
| **Pluck** | Synth, Synth Loop | 100 | 80 One-Shot / 20 Loop |
| **Vocal** | Vocal Phrase, Vocal Loop | 100 | 30 One-Shot / 70 Loop |
| **FX** | Impact, Riser, FX | 100 | 100 One-Shot / 0 Loop |
| **Foley** | Foley | 100 | 100 One-Shot / 0 Loop |
| **Ambience** | Atmosphere | 100 | 0 One-Shot / 100 Loop |
| **Loop** | Music Loop | 100 | 0 One-Shot / 100 Loop |

Each file in the Golden Set carries a JSON metadata declaration with:
* `expected_category`
* `expected_subcategory`
* `expected_bpm`
* `expected_key`
* `expected_loop_one_shot`
* `expected_tonal_atonal`

---

## 2. Benchmark Slices (Signal Isolation)
To determine exactly which signal (Audio DSP, Filename, or Path) contributes to classification, the Golden Set is split into four evaluation slices:

### Slice A: Original Filenames
* **Description**: Preserves files with their original, descriptive vendor names (e.g., `KSHMR_Kick_07_Fmin_128.wav`).
* **Tests**: Full pipeline accuracy including filename parsing, parent folder detection, and metadata extraction.

### Slice B: Anonymized Filenames
* **Description**: Filenames are overwritten with a neutral format (e.g., `sample_0001.wav`). Folder structures are flattened.
* **Tests**: Audio DSP-only classification, key detection, and loop heuristics, removing all lexical biases.

### Slice C: Misleading Filenames
* **Description**: Filenames are intentionally renamed to mismatch the actual content (e.g., `kick_001.wav` containing a snare).
* **Tests**: Signal conflict resolution, confidence calibration, and override priority.

### Slice D: Folder-Only Signal
* **Description**: Filenames are anonymized, but the files are placed inside descriptive folders (e.g., `/Drums/Kicks/sample_0001.wav`).
* **Tests**: Path-traversal intelligence and folder parsing rules.
