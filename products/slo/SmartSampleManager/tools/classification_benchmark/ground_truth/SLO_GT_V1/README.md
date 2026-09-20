# SLO Ground Truth Dataset V1

**Dataset version 1.0.0 · Taxonomy version 1.0.0 · Built 2026-09-10**

The by-ear labels are the only real ground truth in this project. Every accuracy
figure SLO reports depends on them. This directory is the versioned, checksummed,
backed-up form of that asset.

## Contents

| file | what it is |
|---|---|
| `labels.csv` | 1,069 by-ear labelled files, one row each, 21 columns |
| `taxonomy_v1.json` | class and subtype definitions, with measured physics |
| `splits.json` | deterministic collection-held-out folds + sealed set |
| `percussion_subtype_review.csv` | **47 files awaiting owner subtype review** |
| `manifest.json` | counts, provenance, checksums |
| `CHECKSUMS.sha256` | SHA-256 of every asset |

## What is in it

| | |
|---|---|
| labelled files | **1,069** |
| collections | **80** |
| packs | 260 |
| sample families | 941 |
| impulse responses (flagged, excluded) | 9 |
| in evaluation folds | 964 |
| rare-class files in no fold | 13 |
| sealed collections | 3 (83 files) |

## Label provenance

Every row records where its label came from.

| source | n | how it was sampled |
|---|---|---|
| `drums_v1` | 570 | stratified drum sample, the original labelling round |
| `domain_coverage_v1` | 499 | breadth-first across 76 collections, 50 never labelled before |

The two rounds used different sampling strategies, which matters: measurement
showed a label from an unseen collection is worth roughly two from a familiar
one, so provenance is a meaningful covariate, not bookkeeping.

## Taxonomy

32 classes across function-family and temporal-form axes. Each class carries a
definition, its measured coherence, and a status. Four statuses matter:

- **`coherent`** — safe to use as a class.
- **`incoherent_pending_split`** — measured negative silhouette; names several
  sounds. Includes `Percussion`, `Percussion Loop`, `Synth One-Shot`, `SFX`.
- **`provenance_not_acoustic`** — `Foley`, `Foley Loop`. These describe *where a
  sound came from*, not what it does. **Do not split them acoustically**: their
  clusters are weak (0.103) and that is the correct result for a provenance
  label. Belongs in `source_attributes`.
- **`rejection_by_design`** — `Other/none`. Heterogeneity is intended. Negative
  silhouette (−0.196) is correct and expected. Never an auto-rename target,
  never asked to form a compact prototype.

## Impulse responses

Nine labelled files sit under impulse-response directories and were labelled by
ear as Kick (4), Foley (4) and Other/none (1). They are flagged
`is_impulse_response=true` and **excluded from the default splits**.

An impulse response is a measurement of a *space*, not a musical sample; the
product would never usefully rename one, and the IR collection is the
worst-performing in the corpus at 12.5%. **The labels are retained, never
deleted**, so the decision is reversible: `--include-ir` puts them back.

## Split rules

- **Grouped by collection.** A collection appears in exactly one fold, so a pack
  can never straddle train and test. Verified at build time — a straddling
  collection aborts the build.
- **Deterministic** from a recorded seed (default 1), 5 folds.
- **Rare classes** (fewer than 5 examples) cannot be stratified. They are part of
  the dataset but belong to no fold, and are listed explicitly in `splits.json`
  rather than silently dropped.

## Unseen-library evaluation protocol

The product meets libraries it has never seen, so this is the only protocol that
predicts field behaviour.

1. Evaluate **collection-held-out**. Random cross-validation overstates
   unseen-collection accuracy by ~9.7pp on this corpus and must never be used as
   a promotion baseline.
2. Report **mean and standard deviation over ≥8 seeds**, plus raw per-seed
   scores. Single-split deltas under ~2pp are noise here.
3. Report **coverage at a precision target**, not accuracy alone — the renamer
   is gated, so coverage is the product.
4. **Calibrate ~3pp above the intended precision.** A threshold fitted on
   collections you have seen is systematically optimistic on ones you have not
   (measured shortfall 1.2–2.7pp). To deliver a real 95%, calibrate at 0.98.
5. Report **`Other/none` false acceptance** — 26.8% of remaining errors involve
   the rejection boundary.
6. **The sealed collections are opened once, at the end, after the candidate is
   chosen.** `Drum Recollection`, `Minimal Audio`, `Old Movies 1 - Vintage
   Collection (Drum Kit)`. They must never be used for training, model
   selection, thresholds, prompt exemplars, augmentation-policy selection,
   active-learning decisions, error-driven relabelling or pseudo-labelling.

## Backup policy

- Every build copies the whole directory to
  `~/slo_label_backups/SLO_GT_V1_<timestamp>/`, on the **internal disk** — not
  the sample drive, which has already lost power once during this work.
- The raw source CSVs are copied alongside as `SOURCE_*.csv`, so a build can be
  reproduced even if the working copies are lost.
- `python3 build_ground_truth.py --verify` re-checks every asset checksum and
  reports whether the source CSVs have changed since the build.
- **Known gap:** `verified_*.csv` is gitignored by existing project convention,
  so the labels are not in version control. The CSVs contain file *paths*, not
  audio, so tracking them would not distribute licensed content. This is an open
  owner decision.

## Source audio is never mutated

The builder only ever reads. It records every source file's mtime and size
before the build and re-checks them after, aborting if anything changed. The
last build verified **1,139 source files unmodified**. No sample is renamed,
moved, rewritten, or has metadata written into it.

## Reproduction

```
cd SmartSampleManager/tools/classification_benchmark
python3 build_ground_truth.py            # build + checksum + back up
python3 build_ground_truth.py --verify   # re-check an existing build
python3 build_ground_truth.py --include-ir
```
