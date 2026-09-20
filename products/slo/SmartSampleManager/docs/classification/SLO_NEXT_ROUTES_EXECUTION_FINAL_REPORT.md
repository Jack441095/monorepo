# SLO Next-Routes Execution — Final Report

_Phases 0–5 plus gating and taxonomy repair. Every figure is
collection-held-out unless explicitly labelled a diagnostic._

---

## 1. Starting state

576 by-ear drum labels, 30 collections, 55% of them from three packs. Roughly
twenty method-side routes already closed. The canonical grouped harness existed;
the incumbent was nearest centroid at **65.31% ± 1.10**.

## 2. Current git baseline

`main`, pushed. Commits this programme: label schema and allocation validation,
frozen incumbent v1, 100/200/500-label evaluations, sound anatomy, pack-mastering
augmentation, gating, taxonomy repair, factorised taxonomy, incumbent v2.

## 3. The incumbent

Nearest centroid on frozen Perch+CLAP, receipt `incumbent_receipt_v2.json`.

| | v1 (524 files, 30 colls) | **v2 (764 files, 70 colls)** |
|---|---|---|
| accuracy | 65.31% ± 1.10 | **68.60% ± 0.46** |
| macro-F1 | 56.0 | **63.95** |
| coverage @90/95/98% | 49.1 / 28.1 / 13.7% | 41.0 / 18.8 / 5.4% |
| Other/none false accept | 36.59% | **18.70%** |
| worst collection | MGF Mega Pack 34.5% | personal:Impluse Responce 12.5% |

Coverage fell because the corpus is now far harder — 40 additional collections
of unfamiliar material. It is a more honest benchmark, not a regression.

## 4. Labelling and collection coverage

500 new by-ear labels across 76 collections, merged by path into a 1,069-row
corpus spanning 80 collections. Ten classes were added on request during the
session (Bass Reese, Synth One-Shot, Vocal One-Shot/Loop, SFX, Riser, Impact,
Pad, Atmosphere, Weather/Nature Atmos, Drum Fill, Synth Loop, Bass Hit), always
appended so no existing key assignment moved.

## 5. Every experiment attempted

| phase | experiment | result | verdict |
|---|---|---|---|
| 1 | allocation validation (18 checks) | all pass | ✅ |
| 1 | backward-compatible label schema | 24 tests pass | ✅ |
| 2 | freeze incumbent v1 | verifiable receipt | ✅ |
| 3 | pack-mastering augmentation ×5 families | −0.76 to +0.26pp | ❌ |
| 4 | 100 / 200 / 500 labels | **+0.87 / +1.92 / +3.29pp** | ✅ |
| 4 | breadth vs count | **+2.5 to +6.3pp** | ✅ |
| — | per-class gating | precision −12.1pp | ❌ |
| — | taxonomy repair by clustering | −0.28 to −2.08pp | ❌ |
| 5 | factorised taxonomy ×4 formulations | −0.11 to −4.22pp | ❌ |
| — | sound anatomy (definitions) | 3 clean subtypes found | ✅ |

## 6. Negative results

**Pack-mastering augmentation.** Five families, ~7,900 augmented embeddings, all
between −0.76 and +0.26pp, and rejection got *worse* under every policy. The
mechanism test is the real finding: augmentation barely changes collection
decodability (59.3% → 57.3–60.3%), and the family that reduces it most is the
worst on accuracy. **The vendor shortcut is not a mastering shortcut** — more
likely content selection and sample-family structure, neither of which can be
re-EQ'd away.

**Per-class gating.** Appears to add +21.5pp coverage at a 0.98 target. Every
point is bought by accepting errors: precision delivered 82.9% against a 95%
promise. Rejected.

**Taxonomy repair by clustering.** Splitting Percussion doubles its recall
(12.5% → 25–27%) but costs more elsewhere than it gains. Physics-derived splits
beat embedding-derived ones at every setting, but none clears the gate. A
taxonomy cannot be repaired by clustering it; it needs by-ear subtypes.

**Factorised taxonomy.** All four formulations lose. Subtype accuracy *given the
correct family* is **99.4%** — there is no subtype confusion for a hierarchy to
resolve. The error is entirely at the family level. This also retires the v2.0
plan's three-stage coarse-to-fine cascade: measured collection-held-out, it is
the worst of the five formulations at −4.22pp.

## 7. Raw repeated-seed results

Incumbent v2, 8 seeds: 68.6% ± 0.46. Breadth vs count, 14 runs, paired:
+4.41 (t 2.12) / +6.04 (3.95) / +4.58 (4.01) / +4.17 (4.11) / +2.53 (2.31) at
budgets 120–360. Augmentation, 3 seeds: none / spectral / dynamics / space /
format / combined = 65.52 / 65.08 / 65.59 / 65.20 / 64.76 / 65.78.

## 8. Did augmentation reduce collection identity?

**No.** 59.3% baseline versus 60.0 / 60.3 / 59.9 / 57.3 / 57.6. The audio changed
materially; what the encoder knows about the collection did not.

## 9. Did collection breadth matter more than label count?

**Yes, decisively.** At a fixed budget, broad beats concentrated at every budget
tested, 12–13 wins of 14 runs. Learning curves: **+1.81pp per doubling of
labels versus +4.47pp per doubling of collections.** A label from an unseen
collection is worth roughly two from a familiar one. This overturns the earlier
"label in any order" conclusion, which was measured under random CV.

## 10. Best collection-held-out model

The incumbent, unchanged: **nearest centroid on frozen Perch+CLAP, 68.60%**.
Nothing tested this programme beat it. It was improved only by adding labels.

## 11. Precision at useful coverage

**No threshold fully keeps its promise on an unseen collection.** The global
gate undershoots by 1.2–2.7pp and the shortfall grows with the target — a
threshold calibrated on libraries you have seen is systematically optimistic on
libraries you have not.

Correctable, because the offset is stable: to deliver a real 95%, calibrate at
0.98 → measured **95.8% precision at 14.8% coverage**. The honest product
number is 14.8%, not the 18.8% naive calibration claims.

## 12. Other/none false-accept behaviour

36.59% → **18.70%** on the ten-class corpus, and **14.0%** with non-drum labels
mapped to rejection (1,069 files, 80 collections) — roughly 60% of the binding
risk removed, entirely from labels. It is still the largest single error source:
**26.8% of all remaining errors involve the rejection boundary.**

## 13. Percussion taxonomy findings

Percussion contains three physically distinct groups (silhouette 0.159 versus
−0.154 for the class as a whole):

| | Shaker/Tambourine | Tom | Short Perc Hit |
|---|---|---|---|
| centroid | 3859 Hz | 1217 Hz | 2815 Hz |
| energy <200 Hz | 0.00 | **0.40** | 0.08 |
| decay | 0.13 s | 0.26 s | **0.06 s** |
| attack | 36 ms | 16 ms | **0 ms** |

Tom is the only one with real low end and a pitch. Discriminating physics:
centroid d′ 1.70, harmonicity 1.65, decay 1.60.

`Synth One-Shot` is three things and only one is a one-shot — two clusters are
ten-second sustained tones. Duration separates them at d′ 2.47.

`Foley` should **not** be split: its clusters are weak (0.103), which is correct
for a provenance label. `Bass Reese` is the most coherent class in the corpus
(0.507, ahead of Kick at 0.252), and `Bass Hit` is distinct from it despite
having only 11 examples.

## 14. Production integration status

**No production code modified.** Nothing cleared a promotion gate except adding
labels, which is not a code change. The Perch+CLAP stack remains undeployed
pending the model-size decision.

## 15. Remaining owner decisions

1. **Model size** — 210 MB optional download versus lightweight fallback. Blocks
   all deployment.
2. **Label CSVs are gitignored** (`verified_*.csv`) — the only ground truth in
   this project lives solely on the sample drive. Backed up to
   `~/slo_label_backups/`, but worth tracking properly.
3. **Percussion subtypes** — the definitions exist and the schema field exists;
   they need by-ear labels to be usable.
4. **Impulse responses in the corpus** — `personal:Impluse Responce` is the worst
   collection at 12.5% and is not drum material.

## 16. Reproduction

```
cd SmartSampleManager/tools/classification_benchmark
python3 sample_library_inventory.py --workers 8
python3 test_domain_generalization.py && python3 test_label_tool.py
python3 test_labelling_allocation.py
python3 build_corpus_v2.py --workers 6
python3 freeze_incumbent_v2.py --seeds 8
python3 breadth_vs_count.py --runs 14
python3 learning_curves.py --runs 12
python3 aug_experiment.py --eval --family all --seeds 3
python3 per_class_gating.py --seeds 8
python3 taxonomy_repair.py --seeds 8
python3 factorised_taxonomy.py --seeds 8
python3 class_anatomy.py --k 3
```

---

## Conclusion

Nine method-side interventions were tested against a fixed, verifiable incumbent
under collection-held-out evaluation. **All nine failed.** One intervention
succeeded: **adding by-ear labels from unseen collections**, worth +3.29pp
accuracy and −17.9pp false acceptance, and worth roughly twice as much per label
when drawn broadly rather than deeply.

The consistent finding across this programme and the last is that SLO's
remaining error is not a modelling deficit. It is a coverage-of-the-world
deficit, and the only instrument that touches it is a human ear applied to
collections the system has never seen.
