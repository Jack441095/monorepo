# SLO Sample Library Inventory — V1

_Generated 2026-09-10T11:55:16 · read-only walk of the live disk_

## 1. What is actually there

| | |
|---|---|
| readable audio files | **69,495** |
| unreadable / corrupt | 13 |
| total size | 142.5 GB |
| vendors / collections | 84 |
| packs | 275 |
| normalised sample families | 20,519 |

Counts by root:

| root | files |
|---|---|
| packs | 36,176 |
| testing | 28,330 |
| personal | 4,989 |

## 2. The library is 43% redundant

Exact byte-identical duplicates, resolved by SHA-256 within signature-collision groups:

| | |
|---|---|
| duplicate groups | 26,942 |
| files in a duplicate group | 57,160 |
| **redundant copies** | **30,218 (43.5% of library)** |
| duplicate groups spanning more than one vendor | 116 |

This matters for two reasons. Any random split over this library trains and tests on identical bytes, and any labelling budget spent without deduplication buys far fewer distinct sounds than it appears to.

## 3. Label coverage is 0.9%

| | |
|---|---|
| by-ear labelled files | 597 |
| share of library | 0.86% |
| labelled files still present on disk | 570 |
| labelled files missing from disk | 27 |
| vendors in library | 84 |
| vendors with at least one label | 30 |
| **vendors with zero labels** | **54** |

### Largest collections with no by-ear labels at all

These are the domain-coverage targets: unseen-vendor accuracy cannot be measured or improved for collections the model has never been shown.

| files | vendor |
|---|---|
| 1,281 | personal:Impluse Responce |
| 915 | Soundbox - Impacts, Risers & Drops 7 (2021) |
| 901 | Soundbox - Maximum FX (2019) |
| 627 | personal:2024 |
| 500 | personal:2021 |
| 431 | personal:2026 |
| 367 | Origin Sound - Soul Soundscapes (2025) |
| 359 | Flume Ultimate Community Kit |
| 351 | personal:2025 |
| 295 | Production Music Live - Ben Böhmer - Sound Pack |
| 264 | personal:2023 |
| 240 | personal:Ableton Sampler |
| 224 | Black Lotus Audio x Dianna Artist Pack |
| 220 | personal:Sound For Games |
| 201 | Analog Percussion Vol.3 by Donit |

### Labelled-file distribution across vendors

| labels | vendor |
|---|---|
| 147 | Sounds of KSHMR Vol.3 |
| 95 | Organic Drum Kit |
| 95 | Mike Shinoda Drums |
| 63 | Breaks |
| 40 | Drum Recollection |
| 29 | MGF Mega Pack |
| 24 | Minimal Audio |
| 19 | Old Movies 1 - Vintage Collection (Drum Kit) |
| 19 | Organic Electronics 2 J.Views |
| 11 | Koan Sound |
| 8 | Loaded Samples - Lo-Fi Memphis 2 |
| 7 | SIIK Sounds - Eclipse (Full Pack) |

## 4. Method notes

* Vendor is never empty. Three structurally different roots are parsed separately, and Jack's personal year/category folders are namespaced `personal:<dir>` so they can never be mistaken for a commercial vendor during grouped evaluation. Unrooted paths get `_unrooted`.

* Hashing is two-stage: every file gets a cheap signature (size plus first and last 256 KB) and full SHA-256 runs only inside collision groups. Duplicate detection stays exact while reading a fraction of the 136 GB.

* Family IDs strip only variation markers (numeric suffixes, note names, BPM, velocity, round robins) and preserve class words, so `Snare.wav` and `Kick.wav` never merge while `Snare_C3_vel120` and `Snare_C3_vel80` do. Separators are normalised *before* token matching, because `_` is a word character and `\bvel\b` does not match `_vel120`.

* Source audio is never modified, moved or copied into the repository.

## 5. Reproduction

```
cd SmartSampleManager/tools/classification_benchmark
python3 sample_library_inventory.py --workers 8
```
