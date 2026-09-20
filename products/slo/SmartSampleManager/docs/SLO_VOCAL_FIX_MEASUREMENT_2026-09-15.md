# SLO Vocal Loop Fix — Real-Corpus Measurement

**Measured 2026-09-15 on the rebuilt 1,607-file real-vendor corpus.**
Closes the `[PENDING BUILD]` "Before vs After" / "Vocal Family Metrics"
sections of `SLO_CLASSIFICATION_V4_FINAL_CLOSEOUT_REPORT.md`.

This is a measurement of a built binary's output, not a simulation. It
supersedes the pre-build Python simulation in
`SLO_VOCAL_FILENAME_EVIDENCE_REPORT.md` §6 as the authoritative figure, and
both agree on the decisive point (the rule introduces no new Vocal Phrase
errors).

## 1. Corpus reconstruction (the thing that was blocking this)

The measurement had been blocked because `fixtures/scan_subset/` (the derived
qualification corpus) was missing from this machine while only
`dataset_manifest.json` survived.

It is reconstructible. The manifest records each source file's SHA-256, and the
declared source packs are still on disk at
`/Volumes/Jack_Gandy_1TB_SSD/testing-for-NITE-DSP/sample_pack_testing`. The new
tool `tools/classification_benchmark/rebuild_scan_subset.py` (with unit tests
in `test_rebuild_scan_subset.py`, 7 cases) rebuilds the corpus and **verifies
every file by hash before publishing**:

| | |
|---|---|
| manifest entries | 1,607 |
| resolved in source packs | **1,607 / 1,607** |
| hash-verified after copy | **1,607 / 1,607** |
| bytes written | 1,997,344,240 (~2.0 GB) |
| source packs modified | **no** |
| `dataset_manifest.json` rewritten | **no** |

So the corpus used below is byte-identical to the one V4-F/G/H measured
against, and that is *proven*, not assumed.

Two properties the tool refuses to paper over, both covered by tests:
ambiguous basenames across packs are resolved by content hash or reported as
unresolved, and nothing is published if any hash fails.

Measured on this corpus, so the capability is characterised rather than
asserted:

| | |
|---|---|
| basenames present more than once across the packs | **1,454** (e.g. `Organic - Kick (101).wav` exists in both `Organic Drum Kit/1 Kicks/` and `.../Maschine Kits/Head Trauma Kit Samples/`) |
| basenames ambiguous **among the 1,607 selected entries** | **0** |
| entries disambiguated by hash in this rebuild | **0** |
| entries left unresolved | **0** |

So collisions are common in the packs generally, but the manifest's own
selection happens to be collision-free, which is why this rebuild needed no
hash disambiguation. The tooling for it is exercised by the unit tests rather
than by this run — stated so the receipt is not over-read.

### 1.1 One manifest entry is label-conflicted (data defect, not a tool defect)

The manifest's 1,607 entries share **1,606** unique basenames. The duplicate is
the same audio file recorded twice under two different labels:

| sample_id | fixture filename | `expected_subcategory` | `sha256` |
|---|---|---|---|
| 1036 | `1035_KSHMR_Ambiance_Drone_18_F_128_EDM_Section_Texture.wav` | `Foley` | `dcc18f69…c801e6` |
| 1357 | `1356_KSHMR_Ambiance_Drone_18_F_128_EDM_Section_Texture.wav` | `Atmosphere` | `dcc18f69…c801e6` |

Identical content, two labels. This is a defect in the frozen ground truth, and
it has three visible consequences:

1. It is the `mixed_families` condition that makes
   `tools/classification_benchmark/prepare_subset.py`'s `validate_class_coverage`
   refuse to publish (observed directly:
   `mixed_families=[('KSHMR/KSHMR_FX_Elements/KSHMR_Ambiance_and_Foley/KSHMR_Ambiance_Drone_18_F', ['Atmosphere', 'Foley'])]`).
2. `Atmosphere`'s entire support (n=1) is this one contested file, so its
   "0.0% recall" in §6 carries no information.
3. It means the 1,607 rows are 1,606 distinct audio files, so any whole-corpus
   accuracy denominator in §6 includes one duplicated sample.

Neither label is changed here — the frozen ground truth is not edited by this
measurement. It is reported because it is the kind of thing a reader of the
scorecard would otherwise attribute to the classifier.

## 2. Measurement

`ClassificationBenchmark scan fixtures/scan_subset /tmp/vocal_fix_scan.json`,
Release build, `_build/ssm-qualification/`.

The harness emits 2,263 rows because its cache DB is persistent and carries
656 stale rows from earlier sessions; only the **1,607 rows under
`fixtures/scan_subset`** were joined to the manifest. All 1,607 manifest
entries matched exactly. All 1,607 embeddings were valid 512-d.

## 3. Before vs After (Vocal family)

Pre-fix figure is V4-H's own measured production baseline on this same corpus
(`SLO_CLASSIFICATION_V4H_FINAL_CALIBRATION_REPORT.md`, Vocal Loop recall
1.9%). Post-fix figure is measured here.

| Metric | Pre-fix | Post-fix | Change |
|---|---|---|---|
| **Vocal Loop recall** | 1/53 = 1.9% | **48/53 = 90.6%** | **+88.7pp** |
| Vocal Loop precision | — | 48/67 = 71.6% | — |
| Vocal Phrase recall | — | 84/100 = 84.0% | unchanged |
| Vocal Phrase precision | — | 84/87 = 96.6% | — |
| Vocal Phrase falsely labelled Vocal Loop | — | **5/100** | see §4 |

### 3.1 The recovered bucket is exactly the diagnosed bucket

V4-H's root-cause table attributed **46 of 53** Vocal Loop misses to
"Pre-ML evidence = FILENAME, heuristically (and wrongly) classified as Vocal
Phrase" (the other 6 to the OOD gate / DSP).

Attribution here uses a property of the code rather than a guess: the new
Vocal filename rule is the *only* path that yields confidence
`0.7 × 0.95 × 0.9 = 0.5985` (tempo+key, or loop token) or
`0.7 × 0.95 × 0.8 = 0.5320` (tempo-only marker), while the unchanged DSP
fallback yields `0.7 × 0.95 × (0.5 + 0.5·c)`.

Of the 53 Vocal Loop ground truth:

| Path that produced the (correct) Vocal Loop label | n |
|---|---|
| **new Vocal filename rule** | **46** |
| high-confidence ML override | 2 |

## 4. No new Vocal Phrase errors — verified, not assumed

All 5 Vocal Phrase → Vocal Loop flips carry the **DSP fallback** signature
(decay confidence 0.85). **Zero** carry the new rule's signature.

So the rule introduced **zero** new false-loop errors, and the 5 flips are
pre-existing `detectLoopVsOneShot()` behaviour that the fix neither caused nor
addressed. This confirms the simulation's 0-wrong prediction by measurement.

These 5 are a genuine remaining defect, now precisely attributable:

| file | why |
|---|---|
| `KSHMR_Hype_Vocal_27/39_...` | no tempo/key/loop evidence → DSP judged loop-shaped |
| `KSHMR_Vocal_Words_09_Fuck_G` / `17_Hey_G` / `26_No_C` | ordinal index (`09`) and key token are **not** adjacent-plausible-BPM pairs; `isPlausibleBpmToken` correctly rejects `09` (range 40–220) → DSP judged loop-shaped |

## 5. Residual 5 misses: false-OOD suppression, not an ambiguity

The 5 remaining Vocal Loop misses are all `KSHMR_Whistle_*`. Examining the
whole 7-file whistle family shows the cause precisely — and it is *not* the
filename ambiguity that was fixed:

| file | `subcategory` | pre-ML sub | `winningEvidence` | `diagMlIsOod` | ML's own `diagMlSubcategory` | override |
|---|---|---|---|---|---|---|
| `0806_...Whistle_01_Fm` | *(empty)* | Music Loop | UNKNOWN | **True** | Vocal Loop (0.99983) | no |
| `0807_...Whistle_02_85_Dm` | *(empty)* | Music Loop | UNKNOWN | **True** | Vocal Loop (0.99969) | no |
| `0808_...Whistle_03_86_Dm` | *(empty)* | Riser | UNKNOWN | **True** | Vocal Loop (0.99977) | no |
| `0809_...Whistle_04_92_Fm` | *(empty)* | Music Loop | UNKNOWN | **True** | Vocal Loop (0.99985) | no |
| `0810_...Whistle_05_104_Am` | **Vocal Loop** | Bass Loop | DSP | False | Vocal Loop (0.99979) | **yes** |
| `0811_...Whistle_06_125_Cm` | *(empty)* | Bass Loop | UNKNOWN | **True** | Vocal Loop (0.99981) | no |
| `0812_...Whistle_07_128_Fm` | **Vocal Loop** | Bass Loop | DSP | False | Vocal Loop (0.99935) | **yes** |

**For all 7, the ML head's own prediction is the correct `Vocal Loop`** (at
0.99935–0.99985 confidence, i.e. margin ≥ 0.998751). The split between success
and failure is entirely the OOD gate:

- rows the gate marked OOD (`diagMlIsOod=True`) → subcategory left **empty**,
  ML's correct answer discarded;
- rows the gate passed (`False`, evidence `DSP`) → override applied → correct.

So the residual 5 are **false-OOD rejections of in-distribution samples** on
which the classifier is near-certain (margin ≥ 0.9987), not a category-detection
or ground-truth-convention problem. Two secondary observations that correct
earlier framing:

1. These files *do* resolve an `instrumentType` (`Loop`, `Bass`, `Laser`) —
   they are not "never reaching Vocal"; they reach ML, which answers
   correctly, and are then suppressed.
2. Two of the seven are recovered *by ML override* (`tagSource='ml_v3'`), which
   is why the §3 attribution counts "46 by filename rule + 2 by ML override"
   rather than 48 by rule.

This is a concrete, falsifiable example set for any future OOD-threshold work
(the same gate whose false-known rate is quantified in §7) and it is recorded
here rather than compensated for. It is **not** fixed by the Vocal filename
rule and fixing it would touch the frozen V4-H OOD architecture, so it remains
an owner decision.

## 6. Whole-corpus context

Known-class subcategory accuracy over all 1,357 known-class rows: **71.8%**
(974/1,357). Evidence provenance: FILENAME 974, DSP 349, UNKNOWN 34.

| class | n | recall | precision |
|---|---|---|---|
| Kick | 100 | 100.0% | 99.0% |
| Impact | 68 | 100.0% | 90.7% |
| Synth Loop | 47 | 100.0% | 94.0% |
| Bass One-Shot | 98 | 95.9% | 48.7% |
| Synth | 40 | 95.0% | 42.7% |
| Percussion | 100 | 92.0% | 92.9% |
| **Vocal Loop** | **53** | **90.6%** | **71.6%** |
| Clap | 100 | 90.0% | 98.9% |
| Vocal Phrase | 100 | 84.0% | 96.6% |
| Hi-Hat | 85 | 71.8% | 98.4% |
| Snare | 100 | 69.0% | 81.2% |
| Foley | 100 | 69.0% | 84.1% |
| FX | 100 | 47.0% | 39.8% |
| Music Loop | 75 | 37.3% | 96.6% |
| Riser | 100 | 35.0% | 94.6% |
| Bass Loop | 90 | 4.4% | 40.0% |
| Atmosphere | 1 | 0.0% | — |

`Atmosphere` has n=1, which is the label-conflicted duplicate described in
§1.1 — it carries no information. `Bass Loop` (4.4%) and `FX`
(47.0%/39.8%) are the weakest classes after this fix and are *not* addressed
by it. They are pre-existing and reported here so the Vocal improvement is not
mistaken for a whole-corpus improvement.

## 7. OOD (measured, with the exact definition stated)

OOD ground-truth rows receiving a concrete subcategory: **170/250 = 68.0%**.

**Comparability caveat:** V4-H reported 41.6% false-known for its own OOD
evaluation, which used a different (offline, embedding-score) method over
holdout folds. This number is the shipped pipeline's end-to-end output on all
250 OOD rows of the manifest. The two are **not** directly comparable without
a method-mapping check, and no claim of improvement or regression is made here.
Known-class rows flagged OOD by ML: 50/1,357. ML override applied on known
classes: 335.

## 8. What this does and does not change

**Establishes:** the Vocal Loop FILENAME-evidence defect in
`SLO_VOCAL_FILENAME_EVIDENCE_REPORT.md` is fixed in the built binary, with the
complete diagnosed bucket (46/46) recovered, no new Vocal Phrase errors, and
byte-identical corpus provenance.

**Does not establish:** that the frozen ML/OOD architecture should change —
consistent with §7's caveat and the closeout spec's freeze; nor any whole-corpus
accuracy gain beyond the Vocal family; nor a resolution for the 5 whistle
category-detection misses or the 5 DSP-driven false loops, which are
separately attributable and remain open.

**Frozen-architecture verification (this measurement):** the ML/OOD gate was
not exercised differently for the recovered samples beyond the evidence
hierarchy already in force (`diagMlOverrideApplied` false on the 46
rule-driven rows; the rule returns before ML is consulted). The vocabulary and
embedding files were not modified — this measurement required no changes to
`SampleManagerEngine.cpp`'s inference path at all.

## 9. Reproduction

```sh
# 1. rebuild the qualification corpus (hash-verified, ~2.0 GB)
cd SmartSampleManager/tools/classification_benchmark
python3 rebuild_scan_subset.py \
  --corpus-dir /Volumes/Jack_Gandy_1TB_SSD/testing-for-NITE-DSP/sample_pack_testing \
  --receipt-out /tmp/rebuild_receipt.json

# 2. unit tests for the rebuild tool
python3 -m unittest test_rebuild_scan_subset

# 3. measure
cd ../../../_build/ssm-qualification
./ClassificationBenchmark scan \
  ../../SmartSampleManager/fixtures/scan_subset /tmp/vocal_fix_scan.json
```

The corpus is gitignored (`SmartSampleManager/fixtures/`); the tool and tests
are committed, so the measurement is reproducible on a machine that has the
declared source packs.

| *missed (predicted empty subcategory)* | *5* |

**46 of 46** of V4-H's diagnosed FILENAME bucket now resolves correctly —
a complete recovery of the specific defect, not a partial one.