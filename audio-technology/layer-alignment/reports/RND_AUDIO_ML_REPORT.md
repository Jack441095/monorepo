# R&D-G — Cross-Product Audio ML / DSP Report

## Triage

| Area | Priority | Rationale |
|---|---|---|
| Audio embeddings for similarity/retrieval | HIGH POTENTIAL | Direct SLO leverage; possible sampler/KENN retrieval reuse; existing 512-D PANNs baseline |
| Confidence calibration and OOD | HIGH POTENTIAL | SLO false-known rate is the largest measured weakness |
| Lightweight pitch/transient representation | HIGH POTENTIAL | Supports layer alignment and sampler research; classical baselines are feasible |
| Real-time ONNX inference | WATCH | Useful only after a model wins offline quality and resource tests |
| Source separation | WATCH | Valuable but crowded, CPU-heavy, and artifact-prone |
| Timbre similarity learning | WATCH | Promising shared capability; needs licensed multi-vendor data |
| Neural bandwidth extension | LOW PRIORITY | Artifact, latency, training-data, licensing, and real-time risks dominate current evidence |
| Audio-text embeddings | LOW PRIORITY | Product value is unclear before core retrieval/OOD is reliable |

## Audio embedding bake-off status

No new model download or broad bake-off was justified in this sprint. The verified SLO baseline is a 512-D PANNs CNN10 embedding with a frozen linear head. The next safe comparison should use the same leakage-controlled vendor splits for PANNs, a compact spectrogram embedding, and kNN/retrieval metrics, plus model size/latency/licensing.

## Bandwidth extension

Keep on watch. A real-time plugin requires strict latency and CPU budgets, and artifact risk is user-visible. It should not consume the sprint until a concrete NITE DSP workflow and licensed training/evaluation set are defined.

## Best cross-product opportunity

A versioned audio feature/embedding evaluation harness, shared as R&D infrastructure first. It can compare retrieval, instrument identity, OOD, and timbre similarity without forcing one model into SLO, KENN, or a future sampler.
