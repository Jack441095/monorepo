# SLO Classification Golden Set V1 Methodology

This document outlines the evaluation framework designed to rigorously measure the audio understanding capabilities of the Sample Library Optimiser (SLO).

## 1. Corpus Design & Synthesis
The test corpus consists of **170 synthetic mono WAV files** generated programmatically across all **17 subcategories** of the SLO Ableton-oriented taxonomy. Programmatic synthesis guarantees 100% correct ground-truth annotations (no human annotation error or ambiguity).

- **Corpus Size**: 170 files (10 files per subcategory).
- **Format**: Mono, 16-bit PCM, 32kHz sample rate (matching the PANNs ONNX embedding model input).
- **Variability**: Frequencies, decay parameters, and BPM values are modulated across fixtures to prevent byte-identity skew.

## 2. Evidence Ablation Slices
To isolate filename/path heuristics from true audio signal processing, the harness executes four distinct ablation slices:

- **Slice A (Real World)**: Original filenames and folder paths (e.g. `Kicks/kick_01.wav`). Represents standard user library scanning.
- **Slice B (Audio Only)**: Generic filenames in a flat folder structure (`sample_000001.wav`). Disables all filename and folder parsing heuristics, forcing reliance solely on DSP features.
- **Slice C (Heuristics Only)**: Identical flat dummy audio named as the original files (`kick_01.wav`) or in structured folders (`Kicks/sample_001.wav`), isolating the accuracy of semantic name parsers.
- **Slice D (Adversarial)**: Conflicting cues where filenames say one thing (e.g., `kick_01.wav`) but the audio content is completely different (e.g., a high-frequency Hi-Hat hit). Measures how the engine resolves semantic/acoustic conflicts.

## 3. Classifier Diagnostics
We leverage the internal `winningEvidence` provenance field to track whether the classifier's output was driven by:
1. `USER_OVERRIDE`
2. `EMBEDDED_METADATA`
3. `FILENAME`
4. `FOLDER`
5. `DSP`
6. `UNKNOWN`
