# SLO Vocal Loop / Vocal Phrase Disambiguation — State & Remaining-Lever Proposal
**Phase 5 of `SLO_OPTIMIZATION_EXECUTION_PLAN_2026-09-15.md`**
**Date:** September 15, 2026
**Status:** Lever (a) already implemented and tested; end-to-end confirmation BLOCKED on missing corpus audio; lever (b) OWNER-GATED.

---

## 1. What this proposal is (and is not)

The execution plan called for a proposal with two levers before any
implementation. During Phase 5 evidence-gathering it was established that
**lever (a) is already implemented, tested, and reported** in the
2026-09-14 qualification session's work (now in HEAD via the Phase 1
commit's disclosed sweep-in). This document therefore records the true
current state, the one blocked verification, and the genuinely open
decisions — it does not re-propose what already shipped.

## 2. Established evidence chain (all cited, none new)

1. **V4-H freeze** (`SLO_CLASSIFICATION_V4H_FINAL_CALIBRATION_REPORT.md`):
   Vocal Loop recall 1.9% (full corpus). Root-cause forensics: **88%
   (46/53)** of wrong Vocal Loop samples were pre-empted by FILENAME-tier
   evidence deciding "Vocal Phrase" before ML ever ran (and ML's own
   prediction was correct in those cases); 12% were OOD-gate-driven. The
   freeze explicitly named this as the one bounded unresolved blocker.
2. **Forensics + fix** (`SLO_VOCAL_FILENAME_EVIDENCE_REPORT.md`):
   - The real KSHMR corpus (1,607 files) essentially never uses the words
     "loop"/"phrase" in filenames. The actually-separating signal is a
     **BPM+musical-key filename suffix** (e.g. `..._128_D.wav`):
     present on **52/53 (98%)** of Vocal Loop ground truth, **0/100** of
     Vocal Phrase ground truth. Duration does not separate the classes.
   - Fix: Vocal-only override in `AbletonTaxonomy::classify()` — when
     exactly one of {loop evidence, one-shot evidence} is present it
     decides; both/neither falls through to the unchanged DSP heuristic.
     `kTaxonomyVersion` bumped 1 → 2 (cached rows reclassify via
     `lightReanalyzeFile`). No ML/OOD/embedding/ONNX code touched.
   - Adversarial tests (positive/negative/ambiguous/scope-leakage/
     BPM-adjacency edge cases, §5 of that report): **all pass** —
     re-verified 2026-09-15 (`TestTaxonomy` on `ssm-qualification`, exit 0).
   - **1,607-file simulation** (Python mirror of the rule, §6): rule fires
     unambiguously on 52/153 Vocal-family rows, **52/52 correct, 0 wrong,
     0 ambiguous, 101 inert** (no evidence → unchanged behavior).
3. **Closeout** (`SLO_CLASSIFICATION_V4_FINAL_CLOSEOUT_REPORT.md`):
   describes the same fix; its "Before vs After" section is marked
   **[PENDING BUILD]** — the real end-to-end
   `ClassificationBenchmark` rescan was never completed.

## 3. RESOLVED: the confirmatory end-to-end rescan has now run

**Status changed 2026-09-15.** This section previously read "BLOCKED: the audio
is absent from this machine". That finding was true of the *derived*
`fixtures/scan_subset/` tree but false of the corpus as a whole: the declared
source packs remain on disk at
`/Volumes/Jack_Gandy_1TB_SSD/testing-for-NITE-DSP/sample_pack_testing`, and
because `dataset_manifest.json` records a `sha256` for every entry, the corpus
can be **reconstructed and proven byte-identical** rather than merely hoped
for.

That is now tooling, not an ad-hoc script:
`tools/classification_benchmark/rebuild_scan_subset.py` (+
`test_rebuild_scan_subset.py`, 7 tests). Actual run:

| | |
|---|---|
| entries resolved | 1,607 / 1,607 |
| hash-verified | 1,607 / 1,607 |
| bytes written | 1,997,344,240 (~2.0 GB) |
| source packs modified | no |
| manifest rewritten | no |

The measurement itself then ran:
`ClassificationBenchmark scan fixtures/scan_subset`, Release, joined against
the manifest. Full record:
**`docs/SLO_VOCAL_FIX_MEASUREMENT_2026-09-15.md`**.

**Headline result (measured, not simulated):** Vocal Loop recall
**1.9% (1/53) → 90.6% (48/53)**; Vocal Loop precision 71.6%; Vocal Phrase
recall 84.0% *unchanged*.

It is not a 96%+ recovery, and the difference is now understood rather than
unknown:

- **46 of 46** of V4-H's diagnosed FILENAME-evidence damage bucket is
  recovered — attributions verified by a confidence signature unique to the
  new rule (`0.5985` tempo+key / `0.5320` tempo-only) versus the unchanged DSP
  fallback (`0.665·(0.5+0.5c)`).
- **Zero** Vocal Phrase false-loops carry the rule's signature. All 5 flips
  are pre-existing DSP fallback (decay confidence 0.85). The rule introduced
  no new errors — confirming the simulation's 0-wrong prediction.
- The 5 remaining Vocal Loop misses are all `KSHMR_Whistle_*`, whose filenames
  contain **no Vocal token at all**: category detection never reaches `Vocal`,
  so this is a *different* root cause (category detection / ground-truth
  convention), not the ambiguity fixed here.

So the earlier "simulation-backed, not binary-measured" caveat no longer
applies: the result is binary-measured, on a proven-identical corpus. The
simulation's 52/52 figure and the measured 46/46 bucket recovery agree on the
substantive claim (complete recovery of the diagnosed bucket, no new errors)
while differing on the raw count — the simulation counted fires (52), the
measurement counts correct *outcomes* (46 recovered by the rule + 2 by ML
override), and 5 were never reachable by the rule at all.

### 3.1 One ground-truth data defect surfaced

The manifest's 1,607 entries are 1,606 distinct files: the same audio
(`sha256 dcc18f69…c801e6`) is recorded twice with **two different labels** —
`sample_id 1036` as `Foley` and `sample_id 1357` as `Atmosphere`. This is the
`mixed_families` condition that `prepare_subset.py`'s validator refuses to
publish on, and it makes `Atmosphere`'s n=1 support a contested sample. The
frozen labels are **not** edited here; it is reported so it is not
misattributed to the classifier. It is a candidate item for the owner-review
queue.

## 4. Remaining levers, in decision order

### Lever A-remaining (no owner decision needed, data needed):
**Cross-vendor generalization check of the BPM+key rule.** The entire
evidence base is one vendor (KSHMR). The convention is argued to be
industry-standard (Splice/Loopmasters-style), but that is assertion, not
measurement.

**Correction (2026-09-15, measured):** the existing owner-review queue is
**not** a validation path for this rule, contrary to what this section
previously claimed. Audited directly, the 624-row adjudication queue
(`slo_taxonomy_gap_adjudication_queue_merged_v1.csv`) contains **zero Vocal
Loop rows**: its entire Vocal-family coverage is 19 rows, every one of them
`observed_label = Vocal One-Shot` with candidate group `Vocal Phrase|OOD`,
and **0** rows whose labels mention both Vocal and Loop. Batch 04 (264 rows,
26 collections, now issued and integrity-verified: 0 overlap with batches
01–03, 0 duplicates, 100% queue coverage) is genuinely multi-vendor, but its
Vocal content is 2 rows, both one-shots.

So cross-vendor validation of the BPM+key rule requires **new sampling that
targets Vocal Loop across vendors** — it cannot be answered from the existing
queue at any batch size. That is the owner action, and it is cheap to state
precisely: sample N Vocal-Loop-labelled files per vendor from vendors other
than KSHMR, then score the rule's fire-rate/correctness on the reviewed
subset.

### Lever B (owner-gated, spec §17 territory):
**Allow ML to override FILENAME evidence for the Vocal Loop/Phrase pair
when filename evidence is absent** (the 101/153 no-evidence population,
plus future vendors that don't use the convention). Mechanism would be a
scoped `MlOverrideGate` extension: ML consulted for Vocal subcategory only
when `filenameEvidence` is empty on both sides, current DSP heuristic
disagrees with ML, and ML is non-OOD with sufficient margin. V4-H's own
data shows ML was *already correct* on the 46 filename-pre-empted samples;
the no-evidence population is unevaluated. **Do not implement** until:
(a) batch 04 review supplies labeled no-evidence Vocal rows to evaluate
on, and (b) the owner accepts the evidence-hierarchy change explicitly.
Harm risk is asymmetric: a wrong Vocal Phrase→Loop flip pollutes
tempo-locked grouping; the V4-H-recorded 0-harmful-overrides record does
not extend to this new population.

### Explicitly out of scope (frozen per V4-H, unchanged):
OOD threshold re-tuning (its residual 12% attribution), evidence-hierarchy
reordering beyond the scoped Lever B, Music Loop's related but distinct
filename-ambiguity problem (tracked separately in V4-H).

## 5. Requested owner actions

1. ~~Re-acquire the KSHMR corpus audio~~ — **DONE (2026-09-15).** The corpus
   was reconstructed and hash-verified; the rescan ran. See §3. The decision
   point this item represented (accept simulation as final evidence vs measure)
   is therefore moot: it was measured.
2. **Issue Phase 6 batch 04** — **DONE (264 rows, 26 collections)**, integrity
   verified: 0 overlap with batches 01–03, 0 intra-batch duplicates, queue
   coverage now 624/624. Note the corrected scope in §4: it does **not**
   unblock Lever A validation (zero Vocal Loop rows in the queue).
3. **New sampling request (replaces the Lever A-remaining path in §4):**
   sample Vocal-Loop-labelled files from vendors other than KSHMR so the
   BPM+key rule can be tested for cross-vendor generalization. The existing
   queue cannot answer this at any batch size.
4. **Rule on Lever B** (approve / defer / reject) once (3) supplies data.
5. **Rule on the §3.1 ground-truth defect:** `sample_id 1036` (`Foley`) and
   `sample_id 1357` (`Atmosphere`) are the same audio with two labels. One of
   the two labels should be withdrawn or the entry de-duplicated. It is the
   sole reason `prepare_subset.py`'s validator refuses to publish.
6. **Rule on the residual false-OOD suppression** (measurement report §5): 5
   Vocal Loop samples where the ML head is correct at ~0.9998 confidence but
   `diagMlIsOod=True` discards the answer. This touches the frozen V4-H OOD
   architecture, so it is an owner decision, not an engineering fix.
