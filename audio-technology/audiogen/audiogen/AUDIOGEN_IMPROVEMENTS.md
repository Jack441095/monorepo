# AudioGen — Master Improvement Plan (Phase D)

This document scopes **Phase D: Phrase-Level Neural Generator** for `LLM_AudioGen`, transitioning from purely rule-based and Markov-chain melody generation to hybrid neural phrase synthesis.

---

## 1. Phrase-Level Neural Generator (Phase D Core)
Instead of relying strictly on Markov probabilities and post-process heuristics, we propose introducing a lightweight sequence model (e.g. LSTM, GRU, or a small Transformer) to generate melody pitch/duration patterns.

### 1.1 Tokenization Schema
- Represent musical events as unified tokens: `(PITCH_DELTA, DURATION, VELOCITY)`.
- Restrict generated notes to scale degrees relative to the active root key to ensure grounding:
  - `PITCH_DELTA`: Integer distance from scale root (0 to 11).
  - `DURATION`: Time ticks (e.g., sixteenth notes).
  - `VELOCITY`: MIDI velocity bins.

### 1.2 Neural Architecture
- Recommend a **lightweight GRU sequence model** (~500k parameters) to minimize latency on CPU/MPS.
- The model will take the past 4 bars of MIDI tokens and the target emotion vector as inputs, predicting the next phrase token sequence.

---

## 2. Neural-Markov Hybrid Conditioning
Keep the generation strictly grounded to prevent chaotic or dissonant melodies:
- **Joint Plan Constraints**: Force neural predictions to align with the active chord degree targets from `joint_section_plan.py`.
- **Reranker Integration**: Feed neural-generated phrases directly into the Phase B Ridge Reranker (`song_rerank_model.py`) to prune candidates that fail density or repetition checks.

---

## 3. Realtime Performance Targets
- **Inference Latency**: Capped at **< 30ms** per phrase on single-thread CPU to prevent stuttering during realtime playback in `ui_realtime_cli.py`.
- **Pre-loading**: Generate next-phrase patterns asynchronously in a background thread before the current section ends.

---

## 4. Proposed Upgrades Timeline

| Component | Task | Target File(s) |
|---|---|---|
| **4.1 Tokenizer** | Build training dataset exporter converting MIDI history to tokens | `LLM_AudioGen/scripts/export_midi_tokens.py` [NEW] |
| **4.2 Model** | Train a lightweight PyTorch GRU phrase model | `LLM_AudioGen/training/train_phrase_gru.py` [NEW] |
| **4.3 Generation** | Integrate the neural loader into `PhrasePlanner` as a fallback/option | `LLM_AudioGen/composition/phrase_generation.py` [MODIFY] |
| **4.4 Verification** | Add snapshot comparisons and audit check validations | `LLM_AudioGen/tests/test_neural_phrases.py` [NEW] |
