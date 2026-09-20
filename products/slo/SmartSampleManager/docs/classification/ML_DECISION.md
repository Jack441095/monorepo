# Machine Learning Decision Framework

## Decision Verdict
**MAYBE — TARGETED CLASSIFIER EXPERIMENTS JUSTIFIED**

## Evidence Summary
- **Audio-Only Subcategory Accuracy (Slice B)**: 5.9% (Macro F1: 0.010)
- **Full Evidence Subcategory Accuracy (Slice A)**: 58.8% (Macro F1: 0.510)
- **Audio Understanding Gap**: 52.9 percentage points.

- **Leave-One-Out 1-NN Embedding Accuracy**: 98.8%
- **Leave-One-Out 5-NN Embedding Accuracy**: 99.4%
- **Mean Intra-Class Embedding Similarity**: 0.993
- **Mean Inter-Class Embedding Similarity**: 0.791

## Rationale
The evaluation shows that the 512D PANNs embeddings carry very high categorical information, as evidenced by a leave-one-out 1-NN accuracy of **98.8%**.
However, the current rule-based DSP fallback classifier has lower performance on audio-only inputs.
This justifies targeted classifier experiments, comparing the current rule-based DSP cascade with a lightweight classification head (e.g. a linear classifier or small MLP) trained directly on top of the already-computed PANNs embeddings. Since the embeddings are already extracted for indexing, training a lightweight classifier over them introduces **zero additional inference cost**.
