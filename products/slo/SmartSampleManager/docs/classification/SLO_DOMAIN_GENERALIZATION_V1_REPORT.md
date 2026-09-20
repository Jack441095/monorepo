# SLO Domain Generalisation — V1

_Generated 2026-09-10T11:57:59 · 524 by-ear files · 8 seeds × 5 folds_

## 1. The headline

Every previous accuracy figure in this project used ordinary StratifiedKFold. That assumes files are independent. They are not: 55% of the by-ear labels come from three collections, and 175 share a normalised sample family with another labelled file.

| grouping | what is held out | Perch+CLAP accuracy |
|---|---|---|
| `random` | nothing (the old number) | **71.8%** ± 1.0 |
| `family` | sample families (velocity/RR/note variants) | **68.9%** ± 1.0 |
| `pack` | whole packs | **64.2%** ± 1.3 |
| `vendor` | whole collections — the product case | **62.1%** ± 1.8 |
| `packfam` | packs and families | **69.0%** ± 1.0 |

**Random-CV overstates unseen-vendor accuracy by 9.7 percentage points.**

Vendor identity is predictable from the embedding at **62.6%** against a 25.5% majority baseline (8 vendors, n=455), so the representation encodes collection identity, not only sound.

## 2. Full grid

| features | grouping | accuracy | macro-F1 | worst fold | top-2 | P@50% cov |
|---|---|---|---|---|---|---|
| clap | random | 67.4% ± 1.2 | 62.3% | 61.9% | 80.8% | 86.5% |
| clap | family | 65.5% ± 0.9 | 60.4% | 59.0% | 78.6% | 82.5% |
| clap | pack | 59.5% ± 1.3 | 53.1% | 49.7% | 74.5% | 77.2% |
| clap | vendor | 59.0% ± 1.7 | 52.6% | 37.3% | 74.3% | 76.6% |
| clap | packfam | 64.7% ± 1.3 | 59.2% | 57.0% | 78.5% | 82.5% |
| perch | random | 69.4% ± 1.2 | 63.6% | 64.4% | 82.2% | 89.7% |
| perch | family | 66.4% ± 1.5 | 60.3% | 59.3% | 80.0% | 86.6% |
| perch | pack | 60.3% ± 1.2 | 52.8% | 47.5% | 73.7% | 81.0% |
| perch | vendor | 60.0% ± 1.2 | 52.6% | 37.6% | 72.8% | 79.2% |
| perch | packfam | 66.4% ± 0.8 | 60.1% | 60.1% | 80.0% | 86.1% |
| perch+clap | random | 71.8% ± 1.0 | 67.3% | 68.0% | 84.4% | 90.6% |
| perch+clap | family | 68.9% ± 1.0 | 64.1% | 63.0% | 82.2% | 87.4% |
| perch+clap | pack | 64.2% ± 1.3 | 57.7% | 52.2% | 77.0% | 81.6% |
| perch+clap | vendor | 62.1% ± 1.8 | 54.9% | 38.0% | 75.9% | 81.1% |
| perch+clap | packfam | 69.0% ± 1.0 | 63.9% | 63.0% | 82.8% | 88.0% |
| perch+clap-knn | random | 69.8% ± 0.6 | 61.6% | 65.1% | 84.2% | 92.1% |
| perch+clap-knn | vendor | 64.1% ± 0.8 | 52.5% | 32.0% | 74.9% | 85.5% |

### Raw per-seed accuracy

| key | per-seed |
|---|---|
| clap|random | 68.1, 67.4, 65.7, 68.7, 65.7, 67.8, 66.6, 69.1 |
| clap|family | 65.7, 66.8, 63.5, 65.7, 66.2, 64.7, 65.7, 65.7 |
| clap|pack | 59.7, 58.8, 58.6, 62.4, 59.7, 57.8, 59.0, 59.9 |
| clap|vendor | 60.3, 60.9, 58.0, 59.4, 56.9, 59.4, 56.3, 60.9 |
| clap|packfam | 64.5, 65.5, 65.1, 66.6, 63.0, 66.2, 63.0, 63.5 |
| perch|random | 69.7, 69.1, 71.2, 70.0, 66.6, 69.1, 69.7, 70.2 |
| perch|family | 67.4, 66.2, 63.9, 67.6, 68.5, 66.6, 67.0, 64.1 |
| perch|pack | 59.5, 61.1, 59.9, 63.2, 59.7, 59.0, 59.9, 60.3 |
| perch|vendor | 62.2, 59.7, 59.4, 59.2, 58.4, 59.7, 60.1, 61.5 |
| perch|packfam | 64.9, 67.6, 67.2, 65.8, 66.4, 66.4, 66.6, 66.4 |
| perch+clap|random | 72.9, 72.3, 73.7, 70.8, 70.6, 71.2, 71.2, 72.0 |
| perch+clap|family | 69.7, 68.3, 67.4, 69.8, 68.3, 68.3, 70.8, 68.5 |
| perch+clap|pack | 62.4, 63.0, 64.1, 65.7, 66.4, 63.2, 65.1, 63.9 |
| perch+clap|vendor | 64.5, 63.9, 60.9, 61.5, 58.6, 62.4, 61.5, 63.7 |
| perch+clap|packfam | 67.2, 70.2, 69.3, 69.5, 67.8, 69.3, 69.7, 69.3 |
| perch+clap-knn|random | 70.4, 68.9, 70.6, 70.0, 69.1, 70.0, 69.3, 70.0 |
| perch+clap-knn|vendor | 63.7, 65.1, 64.5, 63.2, 63.5, 65.3, 62.8, 64.5 |

## 3. Which classes collapse on unseen vendors

| class | n | recall (random) | recall (vendor) | delta |
|---|---|---|---|---|
| Clap | 90 | 87% | 88% | +1pp |
| Snare | 85 | 75% | 75% | +0pp |
| Kick | 71 | 92% | 86% | -6pp |
| Hi-Hat | 59 | 78% | 70% | -8pp |
| Other/none | 55 | 53% | 34% | -18pp |
| Percussion | 47 | 38% | 15% | -23pp |
| Drum Loop | 41 | 83% | 80% | -2pp |
| Percussion Loop | 28 | 68% | 32% | -36pp |
| Foley | 26 | 31% | 15% | -15pp |
| Crash | 22 | 73% | 77% | +5pp |

## 4. Per-vendor accuracy when that vendor is unseen

| vendor | n | accuracy |
|---|---|---|
| MGF Mega Pack | 29 | 31.0% |
| Organic Electronics 2 J.Views | 11 | 36.4% |
| Old Movies 1 - Vintage Collection (Drum Kit) | 19 | 52.6% |
| Breaks | 53 | 56.6% |
| Minimal Audio | 21 | 61.9% |
| Organic Drum Kit | 93 | 65.6% |
| Sounds of KSHMR Vol.3 | 116 | 67.2% |
| Mike Shinoda Drums | 89 | 70.8% |
| Koan Sound | 8 | 75.0% |
| Drum Recollection | 35 | 77.1% |

## 5. Reproduction

```
cd SmartSampleManager/tools/classification_benchmark
python3 sample_library_inventory.py --workers 8
python3 domain_generalization_eval.py --seeds 8 --report
```
