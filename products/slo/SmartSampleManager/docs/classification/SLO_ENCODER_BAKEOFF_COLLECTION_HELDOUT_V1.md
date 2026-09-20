# MERT/AST encoder bake-off — collection-held-out result

Date: 2026-09-11

## Protocol

Two locally cached open-source encoders were evaluated on the corrected SLO
corpus: MERT-v1-95M (music self-supervised) and AST AudioSet (transformer).
The test uses 1,523 eligible files from 80 collections and 27 classes, eight
seeds of five-fold `StratifiedGroupKFold` by collection. Every arm uses the
same fold-standardised cosine nearest-centroid head; Perch+CLAP is the control.
The extraction window is five seconds for both new encoders. No random-CV
number is used for the decision.

## Results

| arm | accuracy | macro-F1 | delta vs control |
| --- | ---: | ---: | ---: |
| Perch+CLAP control | 57.99% | 49.39% | 0.00pp |
| MERT | 33.58% | 27.75% | −24.41pp |
| AST | 48.25% | 41.53% | −9.73pp |
| Perch+CLAP + MERT | 57.18% | 48.05% | −0.80pp |
| Perch+CLAP + AST | 58.12% | 49.76% | **+0.13pp** |
| Perch+CLAP + MERT + AST | 57.26% | 48.63% | −0.72pp |

The small AST increase is far below the pre-registered +2pp promotion gate
and does not justify a new production dependency or model size. MERT is a
clear negative result. The route is closed for promotion; the cached
embeddings remain available as research evidence only.

## Safety and reproducibility

- Research-only receipt: `results_encoder_bakeoff_collection_heldout_v1.json`
- Runner: `encoder_bakeoff_collection_heldout_v1.py`
- Embedding cache: `mert_ast_granularity_embeddings_v1.npz`
- No production model, taxonomy, rename policy, or source audio changed.
- Remote GPU 1 was not used or touched.

This closes the previously unmeasured self-supervised/audio-language-teacher
route under the correct product metric. Labels and collection breadth remain
the stronger next investment.
