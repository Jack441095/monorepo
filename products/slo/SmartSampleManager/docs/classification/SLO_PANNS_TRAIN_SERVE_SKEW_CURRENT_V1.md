# PANNs train/serve skew — current verification

Date: 2026-09-11

The existing PANNs path was measured locally on 12 testing-library files. The
training path embeds 10 seconds padded to 320,000 samples; the C++ production
path embeds 5 seconds padded to 160,000 samples. Both use 32 kHz audio, but
the production path uses linear resampling while training uses `soxr_hq`.

| comparison with training embedding | mean cosine | minimum | maximum |
| --- | ---: | ---: | ---: |
| window only (10 s → 5 s) | 0.9365 | 0.8690 | 0.9840 |
| resampler only (`soxr_hq` → linear) | 0.9995 | 0.9965 | 1.0000 |
| both production differences | 0.9365 | 0.8684 | 0.9838 |

The material shift is the window, not the resampler. Long samples lose content
at exactly the five-second boundary, and even short samples move because the
global pooling sees a different zero-padding ratio. Cross-validation on the
10-second training embeddings therefore cannot be treated as production
accuracy for a PANNs-trained classifier.

This is a validity guard, not a model promotion. The current SLO review
incumbent remains the collection-held-out Perch+CLAP model. Any future PANNs
route must either re-extract training embeddings through the production
window or intentionally widen the product window, then pass the same grouped
evaluation and rename gates.

Receipt: `results_panns_train_serve_skew_current_v1.json`.
