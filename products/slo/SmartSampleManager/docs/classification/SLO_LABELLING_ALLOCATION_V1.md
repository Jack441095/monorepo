# SLO Labelling Allocation — V1 (domain coverage)

## Why this differs from the previous conclusion

The earlier simulation compared uncertainty, diversity, class balancing and random selection and found no difference, so the conclusion recorded was "label in any order". That result stands for the question it asked, but it drew its pool from the already-labelled population — it could not test breadth across unseen collections, because there were none in the pool.

Phase 1 changed the question. Unseen-vendor accuracy is ~10pp below random-CV accuracy, 55% of existing labels come from three collections, and **54 of 84 collections have no by-ear labels at all**. The reason to expect more labels to help is no longer volume — it is domain coverage.

## The allocation

| | |
|---|---|
| files selected | 600 |
| vendors covered | 76 |
| **collections never labelled before** | **50** |
| packs covered | 244 |
| with no filename evidence | 289 |
| redundant duplicates excluded from the pool | 30,218 |

## Selection rules

* **Breadth first.** Every eligible pack contributes one file before any pack contributes a second.

* **Exact duplicates excluded.** 43.5% of the library is byte-identical redundancy; ignoring it would waste roughly half the budget.

* **One file per normalised sample family**, so velocity layers and round robins cannot consume the budget. Adjacent numbered variants are excluded by construction.

* **Natural distribution preserved.** Classes are not forced to equal counts — the product meets libraries as they are.

* **Files with no filename evidence are included**, since that is the population the classifier actually decides.


## Sealed evaluation set

These collections are reserved and must never be used for model selection, threshold fitting, prompt exemplars or error-driven relabelling:

* `Drum Recollection` — 1,528 files
* `Minimal Audio` — 1,312 files
* `Old Movies 1 - Vintage Collection (Drum Kit)` — 1,668 files

## What to measure next

Acquisition policies must be compared on **vendor-held-out learning curves**, not random CV. The prior finding that selection strategy does not matter was measured under random CV, which Phase 1 shows is the wrong metric. Whether breadth beats random remains genuinely open until measured that way.

## Reproduction

```
python3 labelling_allocation.py --n 600 --emit-manifest
```
