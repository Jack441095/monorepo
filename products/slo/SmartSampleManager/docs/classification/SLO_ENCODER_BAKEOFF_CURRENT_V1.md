# SLO cached encoder bake-off v1

Date: 2026-09-12

## Decision

Cached MERT and AST representations are not candidates to replace or augment the incumbent representation for the current SLO taxonomy. Both are weaker on the collection-held-out task, and concatenation slightly reduces performance.

## Protocol

- Same duplicate-collapsed `factorised_training_manifest_v1.json` used for the factorised experiments.
- Same collection/vendor groups and five grouped folds across five seeds.
- 1,495 rows, 27 eligible classes, and 80 collection groups.
- Each arm standardised features inside each training fold and used nearest-centroid prediction.
- Cached MERT/AST rows were matched by absolute path; no new audio extraction was required.

## Results

| arm | accuracy | macro-F1 | delta vs incumbent |
| --- | ---: | ---: | ---: |
| incumbent representation | 54.70% | 47.40 | — |
| MERT | 31.68% | 27.06 | −23.02pp |
| AST | 45.70% | 40.14 | −9.00pp |
| incumbent + MERT | 54.49% | 46.40 | −0.21pp |
| incumbent + AST | 54.50% | 47.04 | −0.20pp |
| incumbent + MERT + AST | 54.17% | 46.73 | −0.54pp |

## Product implication

Do not add these encoders to the production model or spend more labels on an encoder bake-off. The remaining gains are more likely to come from collection breadth, taxonomy decisions, and calibrated evidence/policy than from swapping generic audio representations.

