# SLO OOD / Unknown-Handling Report V1

## Shipping design

The shipping path uses a 512-dimensional PANNs embedding, linear-head softmax, entropy diagnostics, nearest-centroid cosine similarity, and V4-H per-class OOD thresholds. The 16-class taxonomy is version 2 and the embedding model version is 1.

## Evidence

Historical V4-H results report:

- Full evaluation OOD false-known: **41.6%**; OOD rejection: 58.4%; known acceptance: 96.8%.
- Holdout OOD false-known: **47.2%**; OOD rejection: 52.8%; known acceptance: 97.3%.
- The corpus is thin and single-vendor; the holdout has approximately 26–50 samples per class and 125 OOD samples.

The older score-only comparator reports AUROC approximately 0.697 for MSP, entropy, and margin, with FPR@95 between 0.784 and 0.812. That is a research comparator, not the current production gate.

## Decision

OOD handling is **NOT SUFFICIENT FOR UNQUALIFIED AUTOTAGGING**. It is acceptable only with visible Unknown/OOD output, conservative defaults, and no automatic file movement. The current gate must be measured against cross-vendor and adversarially named material before broader beta claims.
