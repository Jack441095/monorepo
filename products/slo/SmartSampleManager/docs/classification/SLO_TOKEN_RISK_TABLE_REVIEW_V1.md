# SLO Token Risk Table — Review V1

**No token risk was changed in this sprint.** The remaining risky tokens are
granularity problems, and granularity cannot be resolved by re-reading the same
corpus that produced the current numbers. The labels to settle them are now
exported; the table is re-measured *after* they come back, not before.

## Current table, with evidence counts

| token | risk | measured | n | error type | policy | note |
|---|---|---|---|---|---|---|
| `bd` | low | 100% | **4** | — | boost | ⚠ tiny evidence base |
| `clp` | low | 100% | **6** | — | boost | ⚠ tiny evidence base |
| `clap` | low | 97% | 91 | — | boost | solid |
| `kick` | low | 89% | 80 | — | boost | solid |
| `snare` | low | 87% | 102 | — | boost | solid |
| `crash` | low | 86% | **7** | — | boost | ⚠ tiny |
| `cymbal` | low | 83% | 12 | — | boost | thin |
| `tom` | low | 82% | 11 | — | boost | thin |
| `hat` | medium | 78% | 40 | granularity | suggest | Hi-Hat vs Hi-Hat Loop |
| `fx` | medium | 77% | 26 | — | suggest | |
| `impact` | medium | 71% | **7** | — | suggest | ⚠ tiny |
| `foley` | medium | 69% | 26 | granularity | suggest | Foley vs Foley Loop |
| `rim` | medium | 67% | 12 | — | suggest | thin |
| `808` | medium | 55% | 29 | — | suggest | |
| `reese` | medium | 50% | 10 | — | suggest | thin |
| `shaker` | high | 43% | 14 | granularity | family only | usually Percussion **Loop** |
| `top` | high | 40% | 10 | granularity | family only | half are Hi-Hat Loop |
| `perc` | high | 29% | 58 | granularity | family only | usually Percussion **Loop** |
| `snap` | high | 14% | 7 | **identity** | **deleted** | Foley, not Clap |
| `sub` | high | 11% | 18 | **identity** | family only | Reese / Synth Bass |
| `loop` | high | 2% | 112 | granularity | family only | a *specific* loop type |
| `bass` | high | 0% | 30 | granularity | family only | a *specific* bass type |
| `sd` | high | 0% | 8 | **identity** | **deleted** | **KICK — 6 of 8** |
| `hit` | high | 0% | 6 | identity | deleted | Foley |
| `chord` | high | 0% | 12 | identity | deleted | Synth |
| `texture` | high | 0% | **6** | identity | family only | ⚠ tiny |

## Warnings on thin evidence

Four "low-risk" tokens rest on **fewer than 10 observations**: `bd` (4), `clp`
(6), `crash` (7), `impact` (7). A 100% score on four files is not evidence that
a token is safe — it is evidence that we have not yet seen it fail. They are
flagged rather than trusted, and the sprint adds material that will test them.

The same caution applies in reverse: `texture` scores 0% on six files, which is
suggestive but not conclusive.

## Unmeasured shorthand stays medium

`snr`, `sn`, `kik`, `hh`, `chh`, `ohh`, `bs`, `lp` have **no** observations in
the corpus. They default to **medium**, never low. Assigning them high
confidence because they look obvious would repeat exactly the mistake `sd` made:
`sd` also looks like obvious snare shorthand, and it is a kick six times out of
eight.

## What would change the table

| token | needs | currently |
|---|---|---|
| `top` | Top Loop vs Hi-Hat Loop labels | 6 and 13 |
| `sub` | Sub Bass labels | **2** |
| `perc`, `shaker` | Percussion vs Percussion Loop subtypes | overlap unresolved |
| `bd`, `clp`, `crash`, `impact` | more observations | 4–7 each |

All are in the export.
