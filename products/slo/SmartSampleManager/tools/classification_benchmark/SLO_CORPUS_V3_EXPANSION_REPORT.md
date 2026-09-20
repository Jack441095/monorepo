# SLO corpus v3 expansion report

Date: 2026-09-11

## What was added

- 256 new, readable audio files with consensus human labels.
- 6 exact-content duplicates and 20 missing files were excluded.
- Base corpus rows: 1,069; expanded rows: **1,325**.
- Taxonomy inventory: 31 labels; 25 meet the current minimum support gate.
- New viable support includes Bass Loop and Chord Loop.

## Collection-held-out result

The same eight-seed, five-fold vendor/collection-held-out protocol was used.

| metric | corpus v2 | corpus v3 |
| --- | ---: | ---: |
| supported classes | 23 | **25** |
| accuracy | 56.57% | **57.01%** |
| macro-F1 | 46.98 | **49.37** |
| coverage @95% precision | 11.6% | **15.6%** |

The v3 model is frozen separately as `full_taxonomy_model_v3.npz`; v1 remains
the incumbent until the new-label audit is complete.

## Human-label audit interpretation

On the same old human-labelled evaluation rows, training with v3 raised audio
OOF accuracy from 68.05% to 68.90%. The full mixed audit fell to 65.62% because
the newly added labels are a harder, shifted population; that is evidence of
domain difficulty, not a reason to hide the rows. The two populations must be
reported separately before promotion.

On the 256 newly added files specifically, the collection-held-out audit gave:

| policy | accuracy | override precision |
| --- | ---: | ---: |
| audio only | 59.18% | — |
| filename if audio confidence < 0.70 | 67.63% | 100.00% |
| filename always (trusted classes) | 68.85% | 100.00% |

Raw per-class precision was strongest for Hi-Hat Loop (99.1%), Bass Loop
(94.7%), Percussion Loop (92.8%), and Crash (89.2%). These figures are useful
for prioritising further labels, but the lower confidence bounds and support
requirements still prevent automatic renaming.

## Decision

Use v3 for review and suggestion experiments only. Do not promote its new
classes or enable auto-renaming until the new-label population has its own
collection-held-out precision receipt and the class-level lower bounds clear
the product gate.
