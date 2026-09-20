# SLO Classification — V4 Final Engineering Closeout Report

**Engineering branch:** `engineering/slo-classification-analysis-v4`
**Baseline:** V4-H (`5561291`)
**Date:** 2026-08-22
**Status: DRAFT — build/qualification in progress, numeric sections marked [PENDING BUILD] until the full-LTO rebuild and real-corpus rescan complete.**

## Repository / Branch / SHA

Canonical repo `Nite_DSP/Nite_DSP_01`. Verified before mutation:
`git status` clean at start, `engineering/slo-classification-analysis-v4`
at `5561291` matching `origin/engineering/slo-classification-analysis-v4`
exactly (single worktree, no concurrent agent activity observed in
`git worktree list`/`git reflog`). `main` at `ab1de91`, matching
`origin/main` exactly and matching `CANONICAL_WORKSPACE.md`'s recorded R4
state ("R4 complete, 2026-08-22"). `ab1de91` is also the literal fork
point of `engineering/slo-classification-analysis-v4` (confirmed via
`git log` lineage) — i.e. `main` has not moved past this branch's own
base since it was cut. `OWNERSHIP.md`'s current-state table did not
already list this branch; a claim record was added (see §Git / Integration
Status).

## Baseline

V4-H accepted result taken as-is (re-verified against
`SLO_CLASSIFICATION_V4H_FINAL_CALIBRATION_REPORT.md`, not re-derived):
Classification architecture FREEZE; verdict PASS WITH LIMITATIONS; OOD
false-known 41.6% full corpus / 47.2% holdout (2.15x better than
pre-V4-G's 89.6%); harmful ML overrides 0; FX/Foley/Riser recall
recovered +3pp/+12pp/+16pp; Vocal Loop recall recovered only +5.7pp
(7.5% full corpus / 11.5% holdout) because 88% of its damage was
root-caused to upstream FILENAME-evidence disambiguation, not the OOD
gate — explicitly left unfixed and out of scope for V4-H.

## Vocal Loop Root Cause

Full forensics in `SLO_VOCAL_FILENAME_EVIDENCE_REPORT.md`. Summary:
`AbletonTaxonomy::classify()` decided the Vocal Loop-vs-Vocal Phrase
*subcategory* using a DSP-only duration/decay proxy
(`detectLoopVsOneShot`), never consulting filename/folder evidence for
this specific decision (the module's own doc comment stated so
explicitly) — even though filename evidence had already decided the
*category* ("Vocal") upstream, and the evidence hierarchy
(`EMBEDDED_METADATA > FILENAME > FOLDER > DSP`) meant ML was never
consulted to override that FILENAME-tier answer either way.

**Correction to a naive first assumption**: the real V4-F/G/H
qualification corpus (KSHMR vendor, 1,607 files) essentially never spells
out the literal words "loop"/"phrase" in filenames. Direct measurement
(`dataset_manifest.json`) found the actual, near-perfectly-separating
signal is a **BPM+musical-key filename suffix** (e.g. `..._128_D.wav`) —
52/53 (98%) of real Vocal Loop ground truth carries this suffix, 0/100
Vocal Phrase ground truth does. This is a standard, vendor-independent
sample-library naming convention (not specific to this corpus), and is
the dominant evidence this fix relies on in addition to the literal
loop/phrase word tokens the spec's own adversarial test list names.

## Fix

Smallest-scope, Vocal-only override in `AbletonTaxonomy::classify()`:
when `existingInstrumentType == "Vocal"` and exactly one of {loop evidence
(literal "loop" word token OR BPM+key filename suffix), one-shot evidence
(literal "phrase"/"chop"/"oneshot" word token)} is present, that decides
the subcategory (confidence `effectiveBaseConfidence * 0.9`); when both or
neither are present, falls through unchanged to the pre-existing DSP-only
heuristic. No ML/OOD/embedding/centroid/ONNX code touched. No acoustic
BPM production code touched (the new BPM-adjacency check is a
filename-string heuristic, entirely separate from
`estimateBpmFromAudio`/the acoustic tempo estimator). `AbletonTaxonomy::kTaxonomyVersion`
bumped 1 -> 2 so previously-cached rows get selectively reclassified via
the existing `lightReanalyzeFile` path.

Files changed: `SmartSampleManager/Source/AbletonTaxonomy.h`,
`SmartSampleManager/Source/AbletonTaxonomy.cpp`,
`SmartSampleManager/Source/SampleManagerEngine.cpp`,
`SmartSampleManager/Source/test_taxonomy_main.cpp`. Full
CURRENT/FAILURE/PROPOSED-RULE/EXPECTED-EFFECT/REGRESSION-RISK writeup in
`SLO_VOCAL_FILENAME_EVIDENCE_REPORT.md` §2.

## Adversarial Test Set

`test_taxonomy_main.cpp` extended with the full spec §Phase D list (positive:
`vocal_loop_01.wav`, `vox_loop_174.wav`, `female_vocal_loop.wav`,
`acapella_loop.wav`, `choir_loop.wav`, `lead_vocal_loop.wav`,
`vocal_lead_loop.wav`; negative: `vocal_phrase.wav` (given a deliberately
loop-shaped DSP signal), `spoken_phrase.wav`, `vox_phrase.wav`,
`vocal_chop.wav`, `vocal_one_shot.wav`; ambiguous: `vocal_phrase_loop.wav`;
scope-leakage: `bass_loop.wav`, `drum_loop.wav`/`fx_loop.wav`,
`synth_lead.wav`/`lead_synth.wav`, a Synth sample with a BPM+key-suffixed
filename), plus real-corpus-representative BPM+key cases (KSHMR
Vocal_Energy_Booster/Vocal_Melody/Numbers patterns) and BPM-adjacency edge
cases (bare index number, BPM with no key neighbor, key-then-BPM order).

**Result: all tests pass.** `build-test/TestTaxonomy` (pure-logic, no
JUCE/ONNX/audio-decode dependency) exit code 0, built and run
independently of the full-LTO relink (fast, dependency-free target).

## Before vs After

[PENDING BUILD — full-LTO rebuild of `SampleManagerEngine.cpp`-linked
targets was in progress at report draft time. This section will be filled
with the real end-to-end C++ rescan (`ClassificationBenchmark` mode=scan
against `fixtures/scan_subset`, the same 1,607-file corpus V4-F/G/H used)
comparing pre-fix (`5561291`) vs post-fix classification output.]

**Pre-build Python simulation** (forensics/design-validation only, NOT a
substitute for the real rescan above — see
`SLO_VOCAL_FILENAME_EVIDENCE_REPORT.md` §6 for the full method): an
independent re-implementation of the exact tokenization/adjacency rules,
run against all 153 real Vocal-family (Vocal Loop + Vocal Phrase) ground
truth entries in `dataset_manifest.json`, found the rule fires with
unambiguous evidence on 52/153 samples, **100% of which are the correct
label** (0 wrong), with 0 ambiguous cases and 101 unaffected (no evidence,
falls through to unchanged DSP behavior — i.e. the fix is inert for those
samples, not harmful). This is consistent with recovering the large
majority of real Vocal Loop ground truth (52 of 53) without introducing
new Vocal Phrase errors — but is a simulation of the rule, not a
measurement of the built binary's actual output, and is reported as such.

## Vocal Family Metrics

[PENDING BUILD]

## Whole-Corpus Metrics

[PENDING BUILD]

## OOD Metrics

[PENDING BUILD — re-run of V4-H's own OOD evaluation against the rebuilt
binary, per spec Phase G. Expectation, not yet confirmed: unchanged, since
this fix does not touch the ML/OOD gate and only affects samples whose
`winningEvidence` was already FILENAME/FOLDER/EMBEDDED_METADATA (i.e.
samples the OOD gate was never evaluating a subcategory choice for in the
first place — the fix operates entirely downstream of where ML/OOD would
have had a chance to run). If this expectation is not confirmed by the
real rescan, that will be investigated and reported here rather than
silently compensated for, per spec §7/§Non-Negotiable-Architectural-Freeze.]

## Harmful ML Overrides

[PENDING BUILD]

## Frozen Architecture Verification

No changes made to: embedding architecture, `AcousticClassifierWeights.h`/
`AcousticClassifierCentroids.h` (byte-identical, unmodified), V4-H
per-class OOD thresholds, empirical-Bayes shrinkage method, ML override
threshold architecture, `MlOverrideGate` semantics, evidence hierarchy
ordering (`EMBEDDED_METADATA > FILENAME > FOLDER > DSP`, ML overrides only
`DSP`/`FOLDER`/empty — unchanged), taxonomy *architecture* (category/
subcategory/tags shape unchanged — only the Vocal subcategory *decision
logic* gained one new, narrowly-scoped input), ONNX inference. Verified by
`git diff` against `5561291` touching only the four files listed under
§Fix, none of which are ML/OOD/embedding files.

## Regression Tests

[PENDING BUILD — full-LTO rebuild in progress at report draft time.
`TestTaxonomy` (pure-logic subset, buildable independently) already run:
**RUN, PASS** (0 failures, including all new Vocal adversarial tests).
Remaining suite (TestAudioFeatures, TestSampleEngine, TestCacheIntegrity,
TestSafetyRegression, TestCachedReclassification [note: spec's
"TestPersistedCacheHydration" does not exist as a target name in this
codebase's `CMakeLists.txt`; `TestCachedReclassification` is the actual
target covering that cache-reclassification-on-version-bump behavior, and
is treated as the intended target here], TestPrecisionBrowserSorting,
TestAcousticClassifierParity) requires the full-LTO relink and will be
run and reported honestly (RUN/PASS/FAIL/SKIPPED/NOT RUN) once that
completes. TestLicensing: SKIPPED (would create real owner
`license.json`), per spec instruction.]

## Numerical Parity

[PENDING BUILD — `TestAcousticClassifierParity` requires the full rebuild.
Expectation, not yet confirmed: unchanged from V4-H's `3.16082e-06` max
logit error, since no ML head/weights file was touched by this fix.]

## Acoustic BPM Status

ACOUSTIC BPM: EXPERIMENTAL — SEPARATE DEVELOPMENT TRACK. Not touched by
this phase. The new BPM-adjacency filename check added for the Vocal Loop
fix (§Fix) is a distinct, filename-string-only heuristic inside
`AbletonTaxonomy.cpp`, unrelated to and not calling into
`estimateBpmFromAudio`/`parseBpmFromFilename`/the acoustic tempo
estimator's production code paths. [PENDING BUILD for the honest
verification pass: one-shot safety intact, unknown-BPM stays honest, no
fake-120-BPM regression — will be confirmed against the rebuilt binary
before this section is finalized.]

## Performance

[PENDING BUILD — `ClassificationBenchmark` mode=perf run planned once the
target is built. Reported honestly: mean/median/p95 where feasible, no
micro-optimization performed regardless of findings, any hotspot flagged
for future work only.]

## Cache / Owner Data Safety

Production owner cache/sample libraries/installed plugins/licensing state:
not touched by any command run in this phase. All builds target
`build-test/` (a generated, gitignored build tree per
`CANONICAL_WORKSPACE.md`'s "Generated State" table). All scans/tests use
isolated fixture cache directories (`fixtures/cache/` under
`tools/classification_benchmark/`, or engine-internal test-only cache
overrides), never the owner's real sample-cache database. No
`TestLicensing` run (would create real `license.json`). [Byte-identical
before/after verification of any owner-adjacent path touched incidentally
by the build process, if any, to be confirmed and recorded here rather
than merely asserted, per spec §15.]

## Git / Integration Status

Narrow commits planned (Vocal fix + report separate from research-doc
commits, separate again from any integration/ownership bookkeeping
commit), no AI attribution, no force-push/rebase/history-rewrite.
`OWNERSHIP.md` did not previously list `engineering/slo-classification-analysis-v4`
as a claimed branch; a claim record entry is being added as part of this
phase's Phase A/N bookkeeping (see the top-level `Nite_DSP/OWNERSHIP.md`
diff, not part of this git repository — tracked separately per
`CANONICAL_WORKSPACE.md`'s note that `Nite_DSP/` itself is not a git repo).

**Integration decision**: `main` (`ab1de91`) is exactly this branch's own
fork point, so a fast-forward is structurally valid right now with no
ancestry conflict. However, per spec §Phase N's explicit caution ("err
toward stopping at 'ready for controlled integration' rather than
merging, if there is any ambiguity") and because this branch had no
recorded ownership claim in `OWNERSHIP.md` prior to this phase (unlike
the R4 restructuring lineage, which was explicitly tracked there
end-to-end), this phase **does not perform the fast-forward merge to
main** without the qualification numeric sections above being filled in
and confirmed clean first. [Final integration decision recorded once
qualification (Phases F-M) completes — see final status block.]

## Build / Artifact Status

[PENDING BUILD]

## Install / auval Status

Not attempted. No installation, no backup/overwrite of installed AU/VST3,
no `auval` run. Per spec §Phase O: stop at READY FOR CONTROLLED INSTALL
unless build+qualification fully succeeds and installation is clearly
authorized — that gate is not yet reached at report draft time.

## Ableton Acceptance Status

Not performed — no GUI interaction capability in this environment, per
spec's explicit instruction. Checklist for the owner's manual smoke test
provided in the spec itself (plugin loads; library/cache opens; categories
visible; Vocal Loop examples classify correctly; search/sort intact;
LIST/SPLIT/MAP intact; preview intact; favorites/history intact;
drag-to-DAW intact; no obvious performance regression) — no PASS claimed
for any of these items.

## V5 Research Findings

Full document: `SLO_CLASSIFICATION_V5_RESEARCH_BASELINE.md`. Headline
findings: (1) the entire V4-F/G/H/this-phase qualification corpus is a
single vendor (KSHMR), single pack — the largest external-validity risk
in the whole system, and the recommended #1 V5 priority, ahead of any
model change; (2) no error source investigated so far (OOD threshold
uniformity, Vocal Loop filename-evidence precedence) is attributable to
raw embedding-space separation quality — an actual embedding-quality audit
has never been run and is a cheap, high-value next research step; (3) a
ranked, evidence-based list of 9 candidate investments, with multi-vendor
dataset expansion and a generalized filename/evidence heuristic audit
(this phase's method, applied beyond Vocal Loop) ranked highest value for
lowest cost, and embedding-backbone replacement/retraining ranked lowest
(no current evidence it's the bottleneck). V5 IS NOT IMPLEMENTED.

Companion design-only documents (Phases K/L, same closeout):
`SLO_VOCAL_ACTIVE_LEARNING_AND_UX_DESIGN.md` — a structured
`CorrectionRecord` data model and opt-in, privacy-respecting path for a
future user-correction pipeline (reusing the existing
`tagUserOverridden`/`user_tag_overrides` foundation, not rebuilding it),
plus five classification-confidence UX states (HIGH-CONFIDENCE KNOWN,
LOW-CONFIDENCE KNOWN, AMBIGUOUS, UNKNOWN/OOD, USER-CORRECTED) respecting
the "machine proposal = provisional, user decision = authoritative"
grammar. Neither is implemented.

## Remaining Risks

- Numeric qualification sections above are PENDING BUILD at time of this
  draft; a full-LTO rebuild was in progress. [To be resolved before this
  report is considered final — see final status block below for whether
  it was resolved by session end.]
- The Vocal Loop fix's BPM+key-suffix signal, while a genuine
  industry-standard convention (not invented for this benchmark), has only
  been validated against a single vendor's corpus (§ same single-vendor
  gap V5 research flags as the top-priority risk generally). Real-world
  effectiveness against other vendors'/users' naming conventions is
  unverified.
- Vocal Loop samples with neither an explicit "loop"/"phrase" word nor a
  BPM+key suffix (101/153 in the real corpus, including the one Vocal
  Loop ground-truth sample lacking the suffix,
  `KSHMR_Whistle_01_Fm.wav`) remain governed by the pre-existing DSP-only
  heuristic, unchanged — this fix does not claim to resolve Vocal Loop
  recall to 100%, only to recover the portion attributable to the
  specific, diagnosed filename-evidence defect.
- `AbletonTaxonomy.h` has no explicit runtime version marker for the
  frozen ML head/centroids (noted as an open item for the active-learning
  design, `SLO_VOCAL_ACTIVE_LEARNING_AND_UX_DESIGN.md` §1.7) — not a defect
  introduced by this phase, but a prerequisite gap for that future design.

## Recommended Next Engineering Step

[Finalized once qualification numbers land — see final status block.]

---

**This report is being finalized as the underlying full-LTO build and
real-corpus rescan complete. See the session's final status block (V4
CLASSIFICATION / CLASSIFICATION ARCHITECTURE / etc.) for the authoritative
close-out state.**
