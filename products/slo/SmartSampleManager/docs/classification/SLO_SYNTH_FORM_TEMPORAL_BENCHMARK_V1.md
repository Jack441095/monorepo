# SLO synth form temporal benchmark v1

Date: 2026-09-12

## Decision

The apparent Synth Loop / Synth One-Shot opportunity does not survive feature isolation. Focused temporal and pitch/shape blocks provide at most a small improvement over the frozen embedding and do not clear the +2pp gate.

## Results

Collection-held-out evaluation used five seeds and five grouped folds on the existing labelled pair. The best focused block was `temporal_plus_shape` at **87.95%** accuracy (SD 2.08pp), approximately **+0.51pp** over the embedding-only arm on the same rows. Temporal-only and pitch/shape-only blocks were **87.69%**, also below the gate.

The earlier +1.28pp result came from broad descriptor fusion and is not reproduced when the putative form features are isolated. It is therefore not strong enough to justify a production rule or another broad labelling batch.

## Product implication

Keep temporal measurements in the evidence card for explanation and review. Do not promote a Synth-specific classifier from this result. If the product later needs a better sustained-vs-one-shot distinction, it should be addressed with a separately designed form label and a sealed form-specific validation set, not inferred from generic waveform fusion.

