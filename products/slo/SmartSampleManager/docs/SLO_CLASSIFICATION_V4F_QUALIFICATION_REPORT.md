# SLO Classification & Audio Analysis — V4-F Qualification Report

**Engineering branch:** `engineering/slo-classification-analysis-v4`
**V4-A–E commit under test:** `195902d`
**Pre-V4 comparison commit:** `ab1de91` (direct parent of `195902d`)
**Date:** 2026-08-22

## Executive Result: **PASS WITH LIMITATIONS**

The integrated V4 hybrid classifier is **materially and measurably better** than the pre-V4
heuristic classifier on a real 1,607-file commercial sample corpus (accuracy +21.5pp, macro
F1 +0.198, Kick precision 26.8%→93.5%, zero harmful ML overrides observed). One code-level
defect was found, evidenced, fixed, and re-verified during this phase (one-shot BPM safety
net). **One serious, unresolved gap remains: the OOD gate has an 89.6% false-known rate on
hard real-world OOD material** and is not acceptable for shipping as-is. BPM trustworthiness
is mixed: metadata/filename precedence and one-shot safety (post-fix) are sound, but acoustic
tempo estimation accuracy on musical loops is weak. See §15 Ship Recommendation.

---

## 1. Answers to the Two Framing Questions (§39 of the spec)

**Is SLO's new hybrid classification system actually better?**
Yes, on the evidence gathered. Overall accuracy 45.6% → 67.0% (+21.5pp), macro F1 0.396 →
0.594 (+0.198), Kick precision 26.8% → 93.5% with recall unchanged at 100%, Kick false-positive
rate 18.1% → 0.46%, Vocal recall 44.4% → 63.4%. Of 539 ML overrides observed, 353 were
corrective and 0 were harmful (override precision 1.00) on this corpus — but this dataset does
not contain deliberately adversarial confusion pairs, so "0 harmful" should be read as "0
harmful in this sample," not "harm-proof."

**Is SLO's BPM analysis trustworthy enough to expose to users?**
Not fully, yet. The metadata→filename→acoustic→unknown precedence chain is implemented and
behaves correctly. A real one-shot BPM-safety defect was found and fixed during this phase
(see §10). Acoustic tempo estimation on real musical loops, however, is inaccurate (only
11.6% of filename-tempo-labelled loops matched within 0.5 BPM; mean absolute error ~52 BPM)
and long non-loop one-shots (FX/Foley/Impact/Riser/Vocal Phrase ≥2s) still frequently receive
a plausible-but-meaningless tempo value. BPM should not be presented to users as a confident
number without further work; a "confidence: low" or "estimated" qualifier is recommended.

---

## 2. Dataset

**Corpus:** `SmartSampleManager/tools/classification_benchmark/fixtures/scan_subset` — 1,607
real, 24-bit commercial WAV files from KSHMR "Sounds of KSHMR Vol.3" (single vendor; already
existed as committed benchmark tooling from a prior research phase — commits `0a43ce2`,
`77608e2`, `593ce78`, all ancestors of `195902d`). Ground truth: `dataset_manifest.json`,
label authority `TRUSTED_PACK_LABEL` / `OWNER_VERIFIED`, `HIGH` confidence, `sha256`-identified.
Corpus and all generated results live outside Git (`fixtures/` and `v4f_results/` are
gitignored) and are read-only local copies — nothing in the owner's live sample library or
production cache was touched (all scans ran through `ClassificationBenchmark`'s isolated
`fixtures/cache` override).

**Class counts (support):**

| Class | n | Class | n |
|---|---|---|---|
| Kick | 100 | Music Loop | 75 |
| Snare | 100 | Synth Loop | 47 |
| Clap | 100 | Vocal Loop | 53 |
| Hi-Hat | 85 | Vocal Phrase | 100 |
| Percussion | 100 | Bass Loop | 90 |
| Bass One-Shot | 98 | Riser | 100 |
| Synth | 40 | Impact | 68 |
| FX | 100 | Foley | 100 |
| Atmosphere | 1 | **OOD** | 250 |

**Limitations (reported honestly, not hidden):** single vendor (KSHMR) — no cross-vendor
generalisation evidence; `Atmosphere` has only 1 sample (statistically meaningless; excluded
from headline conclusions); `Synth` (40) and `Vocal Loop` (53) are thin; no calibration/holdout
split was used — the dataset was too small relative to the number of classes to sacrifice a
holdout without making per-class numbers unreliable, so **all reported numbers are from the
full corpus, not a held-out set** (spec §28 limitation, stated explicitly).

---

## 3. Regression Suite (§3, unchanged baseline safety)

Re-ran the existing 8-binary suite, rebuilt against the final candidate (post-instrumentation,
post-BPM-fix): **8 RUN, 8 PASS, 0 FAIL.**
TestTaxonomy, TestAudioFeatures, TestSampleEngine, TestCacheIntegrity, TestSafetyRegression,
TestPersistedCacheHydration, TestPrecisionBrowserSorting, TestAcousticClassifierParity all
pass. `TestAcousticClassifierParity`: max logit error 3.16e-06, max probability error
2.97e-07 — unchanged from the pre-existing figures in the spec.

---

## 4. PRE-V4 vs V4 — Headline Delta

Both classifiers built from source and run against the **identical** 1,607-file corpus with
the identical isolated cache. Pre-V4 = `ab1de91` (parent of `195902d`, built in an isolated
git worktree, deps reused read-only from the existing fetch cache — no network access, no
owner data touched). V4 = `195902d` + the BPM one-shot-safety fix (§10; classification fields
were confirmed byte-identical before/after that fix, so this delta table is not affected by it).

| Metric | PRE-V4 | V4 | Delta |
|---|---|---|---|
| Overall accuracy | 0.4555 | 0.6702 | **+0.2147** |
| Macro F1 | 0.3958 | 0.5936 | **+0.1978** |
| Balanced accuracy | 0.4672 | 0.6701 | **+0.2029** |
| Vocal recall | 0.4444 | 0.6340 | **+0.1895** |
| Vocal→Drums rate | 0.0196 | 0.0131 | **−0.0065** |
| Kick precision | 0.2681 | 0.9346 | **+0.6665** |
| Kick recall | 1.0000 | 1.0000 | 0 |
| Kick false-positive rate (non-Kick called Kick) | 0.1812 | 0.0046 | **−0.1765** |

**Changed-decision analysis (§9):** of 1,607 files, 566 changed prediction between PRE-V4 and
V4: **353 good flips**, **8 bad flips**, 205 neutral/still-wrong. Good:bad ratio ~44:1.

The 8 bad flips are a real, specific regression worth tracking, not papered over:
- 7× `KSHMR_Percussion_High_Rimshot_*.wav` (ground truth Percussion) flipped to Snare — an
  expanded/refined Snare heuristic (V4-B) now over-triggers on rimshots.
- 1× `KSHMR_Vocal_Words_27_Oh_No_C-G.wav` (ground truth Vocal Phrase) flipped to Hi-Hat.

Full lists: `classification_results.csv`, `benchmark_summary.json.flip_examples` (local,
gitignored — reproducible via `analyze.py`).

---

## 5. Confusion Matrix & Per-Class Metrics (V4)

Full matrices: `classification_confusion_v4.csv` / `_prev4.csv`, `per_class_metrics_v4.csv` /
`_prev4.csv` (local). Headline per-class precision/recall/F1, V4:

| Class | Precision | Recall | F1 |
|---|---|---|---|
| Kick | 0.935 | 1.000 | 0.966 |
| Snare | 0.911 | 0.720 | 0.804 |
| Clap | 0.990 | 1.000 | 0.995 |
| Hi-Hat | 0.988 | 1.000 | 0.994 |
| Percussion | 0.979 | 0.930 | 0.954 |
| Bass One-Shot | 0.462 | 1.000 | 0.632 |
| Bass Loop | 0 | 0 | 0 |
| Synth | 0.377 | 1.000 | 0.548 |
| Synth Loop | 0 | 0 | 0 |
| FX | 0.584 | 0.970 | 0.729 |
| Foley | 0.857 | 0.960 | 0.906 |
| Impact | 0.919 | 1.000 | 0.958 |
| Riser | 0.978 | 0.890 | 0.932 |
| Music Loop | 0.255 | 0.560 | 0.350 |
| Vocal Phrase | 0.621 | 0.900 | 0.735 |
| Vocal Loop | 0.292 | 0.132 | 0.182 |

**Bass Loop and Synth Loop are never predicted as such by V4 (0/0/0)** — every Bass Loop
sample is called Bass One-Shot and every Synth Loop sample is called Synth or Music Loop.
This is a pre-existing taxonomy gap (identical failure exists in PRE-V4, so it is not a V4
regression), but it means the taxonomy currently cannot distinguish loop vs one-shot for
these two families at all, and should be flagged for a future phase — not fixed here per the
"no taxonomy redesign in V4-F" constraint.

**Snare↔Clap:** 28 Snares misclassified as Foley in V4 (not Clap directly); Clap itself is
clean (99.0% precision, 100% recall) — no material Snare↔Clap confusion found.
**Hi-Hat↔Percussion:** clean in both directions (no material confusion found).
**Bass↔Synth:** Bass One-Shot precision is dragged down mainly by OOD bleed-through (see §7),
not by genuine Synth confusion.

---

## 6. ML Override Audit (§10)

| | Count |
|---|---|
| Total ML overrides applied | 539 |
| Corrective | 353 |
| Harmful | **0** |
| No-effect-equivalent (heuristic and final both wrong, different labels) | 186 |
| **Override precision** (corrective / (corrective+harmful)) | **1.00** |

Zero harmful overrides is a strong result but should be read against dataset composition: this
corpus is mostly clean, well-labelled commercial one-shots/loops, not adversarial confusion
pairs. It demonstrates the override gate does not actively destroy correct heuristic decisions
on realistic material — it does not prove harm is impossible in general.

**Disagreement matrix (top families, heuristic-pre-ML vs raw ML class, all evaluated
samples):** heuristic=Kick / ml=Music Loop (97), heuristic=Bass One-Shot / ml=Bass Loop (85),
heuristic=(empty) / ml=FX (79), heuristic=(empty) / ml=Riser (79), heuristic=Kick / ml=Foley
(46), heuristic=Vocal Phrase / ml=Vocal Loop (44), heuristic=Synth / ml=Synth Loop (41). Full
table: `benchmark_summary.json.top_disagreements_heuristic_vs_ml`. In the "heuristic=Kick /
ml=Music Loop" family the override gate correctly does **not** apply (heuristic evidence was
FILENAME/EMBEDDED_METADATA, which V4-D protects), so this large raw-ML disagreement does not
translate into overrides or errors — it is evidence the precedence guard is doing its job, not
a live problem.

---

## 7. OOD Qualification (§13) — the weak point

Ground truth includes 250 real, `OWNER_VERIFIED` "hard OOD" samples: genuine KSHMR audio
(mostly full musical Bass Loops) that the dataset curator deliberately marked as outside the
classifier's clean training distribution, per spec §13's instruction not to tune/test OOD using
only obvious noise.

| | V4 |
|---|---|
| OOD correctly rejected (`tagSource=ml_ood` or unclassified) | 26 / 250 (10.4%) |
| OOD incorrectly accepted as a confident known class (false-known) | 224 / 250 (**89.6%**) |
| Known samples incorrectly marked `ml_ood` | 5 / 1,357 (0.4%) |

Of the 224 false-knowns, most were accepted via `ml_v3` (181) — i.e. AcousticClassifier itself
was confident and wrong — with the rest via heuristic evidence not gated by ML at all (43).
Top classes OOD material was misfiled into: Music Loop (122), Bass One-Shot (22), Synth Loop
(20), Synth (18), Vocal Loop (17).

**This is a genuine, serious gate weakness, not a dataset artifact of "obvious noise vs subtle
OOD"** — these are real musical bass loops from the same vendor, acoustically close to
in-distribution content, which is exactly the hard case the OOD gate exists for. Per ship-gate
criterion 7 (§35), this is **not acceptable** as-is. No threshold sweep value tested (§8 below)
meaningfully improves this, because raising the ML-confidence threshold reduces overrides
generally — it does not specifically target OOD detection quality, which is a separate score
(`isOod`) computed independently of the confidence threshold.

---

## 8. Threshold Sweep (§11)

Offline simulation over the 1,607-sample corpus, re-deriving the final label at each threshold
from the captured heuristic-pre-ML state + raw ML class/confidence/OOD flag (no rebuild
required per threshold — `threshold_sweep.csv`):

| Threshold | Accuracy | Overrides | Corrective | Harmful | Override precision |
|---|---|---|---|---|---|
| **0.40 (current)** | **0.6702** | 539 | 353 | 0 | 1.00 |
| 0.45 | 0.6696 | 537 | 352 | 0 | 1.00 |
| 0.50 | 0.6696 | 534 | 352 | 0 | 1.00 |
| 0.55 | 0.6689 | 526 | 351 | 0 | 1.00 |
| 0.60 | 0.6683 | 519 | 350 | 0 | 1.00 |
| 0.65 | 0.6677 | 511 | 349 | 0 | 1.00 |
| 0.70 | 0.6658 | 503 | 346 | 0 | 1.00 |
| 0.75 | 0.6621 | 481 | 340 | 0 | 1.00 |
| 0.80 | 0.6565 | 462 | 331 | 0 | 1.00 |
| 0.85 | 0.6484 | 429 | 318 | 0 | 1.00 |
| 0.90 | 0.6385 | 396 | 302 | 0 | 1.00 |

Accuracy is monotonically non-increasing as the threshold rises; harmful-override count is 0
at every threshold on this corpus. **Evidence supports keeping 0.40** — there is no accuracy
or safety benefit to raising it on this dataset, and raising it strictly reduces the number of
corrective overrides. **No threshold change was made.** (This sweep cannot speak to OOD
quality — see §7.)

---

## 9. Confidence Calibration (§12)

| Confidence bucket | n | Accuracy |
|---|---|---|
| 0.40–0.50 | 255 | 0.600 |
| 0.50–0.60 | 368 | 0.731 |
| 0.60–0.70 | 308 | 0.938 |
| 0.70–0.80 | 41 | 0.366 |
| 0.80–0.90 | 66 | 0.439 |
| 0.90–1.00 | 396 | 0.765 |

**Confidence is not monotonically calibrated.** Accuracy rises through 0.60–0.70 then *drops*
in 0.70–0.90 before recovering at 0.90–1.00. Root cause: `tagConfidence` mixes two
incompatible scales — V4-C's fixed evidence-tier values (DSP=0.75, FOLDER=0.85, FILENAME=0.95,
EMBEDDED_METADATA=1.00) and AcousticClassifier's continuous ML confidence — on the same
nominal 0–1 axis. The 0.70–0.90 buckets are dominated by DSP/FOLDER-sourced heuristic labels
that are frequently wrong (e.g. the Kick/Music Loop DSP-fallback confusion), while 0.90–1.00
mixes high-accuracy FILENAME/METADATA evidence with lower-accuracy high-confidence ML calls.
ECE/Brier were not computed — the dataset is not large enough per confidence bucket (as low as
n=41) to make those numbers meaningful, and this limitation is stated rather than a false
precision implied. **Recommendation (not implemented): report evidence-source alongside
confidence rather than presenting a single unified confidence number to users.**

---

## 10. One-Shot BPM Safety — defect found, fixed, and re-verified (§21, §26–27)

**Before any calibration was made**, baseline measurement of untouched `195902d` found: of
1,092 true one-shot-category files (Kick/Snare/Clap/Hi-Hat/Percussion/Bass One-Shot/Synth/FX/
Foley/Impact/Riser/Vocal Phrase, all real duration < a few seconds), **87.5% received a
non-zero ("fake") acoustic BPM value** — including **100/100 Kicks**, median real duration
~0.5s, well under the documented 2-second minimum for acoustic tempo estimation.

**Root cause (source-level, not a threshold):** `estimateBpmFromAudio()` in
`Source/SampleManagerEngine.cpp` gated its "≥2s" duration check on the size of the fixed
5-second zero-padded/truncated embedding-analysis buffer (`numSamples / sampleRate`), which is
**always** ~5.0s regardless of the source file's real length — so the safety net could never
actually reject anything. This is a genuine defect in existing V4-E logic, not a calibration
knob; per §26 it was evidence-justified (baseline measured first) and low-risk (defensive only
— it can only move samples toward `UNKNOWN`, never invent a new false positive), so it was
fixed in-branch rather than merely reported.

**Fix:** pass the sample's true original duration (already computed by
`loadAndResampleWaveform`) into `estimateBpmFromAudio` and gate on that instead.

**Before/after, same corpus, same build otherwise:**

| | Before fix | After fix |
|---|---|---|
| False-tempo rate, true one-shots (n=1,092) | 87.5% | **27.0%** |
| False-tempo rate, files genuinely < 2s real duration (n=661) | — | **0.0%** |
| False-tempo rate, one-shot-category files ≥ 2s real duration (n=431) | — | 68.5% |
| Kick false-tempo rate | 100/100 | **0/100** |
| Classification fields (category/subcategory/tagSource) changed by this fix | — | **0 / 1,607** |

The residual 68.5% false-tempo rate is on one-shot-*taxonomy* files (FX/Foley/Impact/Riser/
Vocal Phrase, etc.) that are genuinely ≥2s of real audio — these correctly pass the (now
honest) duration gate per the documented rule, but the estimator still frequently returns a
musically-meaningless tempo for non-periodic sound-design material. That is a separate,
unresolved limitation of the estimator itself (over-eager 1.8x peak-to-mean confidence gate on
quasi-random ODF), not the duration-gate bug, and was **not** fixed in this phase (would be an
algorithm change, not a narrow calibration — out of scope per §26).

**Regression check:** all 8 test binaries re-run after this fix — 8/8 pass (§3).

---

## 11. BPM Precedence & Loop Accuracy (§18–22)

**Precedence chain** (TagLib metadata → filename → acoustic → unknown) was verified correct
by code inspection of `prepareFile()`: metadata is read first via `readWavMetadata`, filename
is only consulted `if (loadedSample.bpm <= 0.0f)`, acoustic is only reached if filename parsing
also fails. No conflicting-precedence bug found. None of the 1,607 real files carried embedded
BPM metadata (checked via raw RIFF chunk inspection — no `bext`/`acid`/`iXML` chunks present in
this vendor's files), so the metadata-wins-over-filename case could not be exercised on real
audio in this pass; this is a **known limitation**, not a claim of full coverage.

**Loop tempo accuracy:** 95 real Loop-family files had a plausible BPM literally embedded in
their vendor filename (e.g. `..._Bass_Loop_04_128_Am.wav` → 128), usable as real ground truth.
Against these: exact (±0.5 BPM) 11.6%, ±1 BPM 21.1%, ±2 BPM 33.7%, unknown rate 21.1%
(estimator returned 0 rather than a wrong guess), mean absolute error ~52 BPM including several
catastrophic mismatches (e.g. true 60–66 BPM Psy-Bass loops estimated at ~101 BPM — not a
clean octave-doubling relationship, a genuine wrong answer, not an octave-folding artifact).
6 of 95 showed a half/double-time-consistent relationship to ground truth. **Loop tempo
accuracy is weak and should not be presented to users as reliable without further work** — this
finding stands independent of, and was not touched by, the one-shot safety fix in §10.

**Octave normalization (§20):** could not be directly stress-tested with real audio at true
174/180/190 or 60/65 BPM ground truth within this pass (the filename-derived loop ground truth
set skewed toward 100–135 BPM). Recommendation carried forward unimplemented per spec: store a
primary BPM plus an alternate octave hypothesis rather than silently folding.

---

## 12. Filename Evidence Qualification (§15)

134 real files contained at least one vocal-related filename token (`vox`, `vocal`, `voice`,
`adlib`, `acapella`, `choir`, `phrase`, `spoken`, etc.); 114/134 (85.1%) correctly resolved to
a Vocal subcategory. The 20 mismatches are a genuine, reportable finding, not fabricated:

- **Label injection in the wrong direction:** 9 files literally named
  `KSHMR_Sweep_Down_NN_Vocal_<key>.wav` (ground truth: Riser — a vocal-formant-processed riser,
  not a vocal recording) were classified as Vocal Phrase purely because the word "Vocal"
  appears in the filename. This is exactly the "uncontrolled label injection" risk the spec
  warned about in §15 — the vocal-token rule does not check word context.
- **Incomplete precedence in the other direction:** several `KSHMR_Hype_Vocal_NN_<spoken
  phrase>.wav` files (genuinely vocal hype tags) were classified as Clap, Impact, FX, or Bass
  One-Shot instead of Vocal, because words later in the phrase (e.g. "...Go_Boom" → Impact,
  "...Clap_Clap_Clap..." → Clap) out-ranked the earlier "Vocal" token. V4-B's stated "Vocal
  token precedence over generic Synth tokens" does not fully generalize to precedence over
  *other drum/impact* tokens in the same filename.

Neither of these was fixed in this phase (heuristic/taxonomy changes are out of scope for V4-F
calibration per §26) — they are documented as findings for a future pass.

---

## 13. Performance (§23)

Measured with `ClassificationBenchmark perf` on a 170-file subset (`fixtures/slice_a`),
3 iterations, isolated cache, current (post-fix) build:

| | Value |
|---|---|
| Cold scan (from empty cache) | 11.10s mean (10.78–11.44s), 170 files → ~65ms/file |
| Cached/warm re-scan | 0.79s mean (0.68–0.85s) → ~4.6ms/file |
| RSS before / peak / after | 14.3 MB / 2,972 MB / 2,812 MB |

No pre-V4 comparison is possible for this specific harness (the `ClassificationBenchmark perf`
mode did not exist before V4-era tooling was added), but the added V4-D/E work (one ONNX
linear-head evaluation + one acoustic-BPM pass per file, both already inside the existing
per-file ONNX/DSP pipeline) does not introduce any new per-file I/O or blocking work beyond
what was already measured. No real-time-thread involvement: all classification, ONNX
inference, and acoustic BPM analysis run on the background inference/scan worker thread, not
the audio callback (confirmed by code path — `prepareFile`/`runInferenceBatch` are called from
the engine's async scan queue, never from `processBlock` or similar).

---

## 14. Owner-Data & Scanner Safety (§24)

- All scans used `SampleManagerEngine::setCacheDbDirectoryOverrideForTesting()` pointing at
  `fixtures/cache`, never the production cache path.
- Production cache (`~/Library/Application Support/.../sample_cache.sqlite3`) confirmed
  0 bytes, mtime unchanged (2026-08-13, before this session) throughout.
- No files under `fixtures/scan_subset` were modified, renamed, or moved; benchmark ran in
  `scan`/`perf` read-only modes only.
- No AU/VST3 was installed or overwritten; no installation qualification was run.
- The PRE-V4 comparison build used a temporary `git worktree` (removed at the end of this
  session) with its own isolated build directory and a copy of `JuceHeader.h` reused
  read-only from the existing `build-test` artefacts — no shared/installed JUCE state touched.

---

## 15. Files Changed / Commits

**Source changes (both additive/defensive, no taxonomy or threshold change):**
- `SmartSampleManager/Source/SampleManagerEngine.h` — added benchmark-only diagnostic fields
  to `Sample` (heuristic-pre-ML snapshot, raw ML class/confidence/OOD, override-applied flag).
  Never read by production logic; does not change any classification decision.
- `SmartSampleManager/Source/SampleManagerEngine.cpp` — (a) populate the above diagnostic
  fields alongside the existing V4-D override check; (b) **fix**: `estimateBpmFromAudio()` now
  gates its one-shot-safety duration check on the sample's true original duration instead of
  the fixed 5s analysis-window sample count (§10).
- `SmartSampleManager/tools/classification_benchmark/classification_benchmark_main.cpp` —
  extended `scan` mode JSON output with the new diagnostic fields.
- `SmartSampleManager/tools/classification_benchmark/.gitignore` — added `v4f_results/` (this
  run's generated output; kept local per §33).
- `SmartSampleManager/docs/SLO_CLASSIFICATION_V4F_QUALIFICATION_REPORT.md` — this report.

**Local-only, not committed (per §33 — reproducible from the above + the fixtures corpus):**
`tools/classification_benchmark/v4f_results/` — `classification_results.csv`,
`classification_confusion_{v4,prev4}.csv`, `ml_override_analysis.csv`, `threshold_sweep.csv`,
`confidence_calibration.csv`, `bpm_results.csv`, `benchmark_summary.json`, raw scan JSON dumps,
`analyze.py` (the analysis script used to produce all numbers in this report).

**Commits on `engineering/slo-classification-analysis-v4`, on top of `195902d`:**
1. `test(classification): instrument V4-F benchmark with heuristic/ML override diagnostics`
2. `fix(classification): gate acoustic BPM one-shot safety net on true audio duration`
3. `docs(classification): record V4-F qualification report`

No merge to `main`. No force-push. No AI attribution in commit trailers.

---

## 16. Known Limitations (stated explicitly, not hidden)

- Single vendor (KSHMR) real corpus — no cross-vendor/cross-genre generalisation evidence.
- No calibration/holdout split (dataset too small per-class to sacrifice a holdout credibly).
- ECE/Brier not computed (insufficient per-bucket sample sizes for a meaningful number).
- Full 60–190 BPM controlled click-track sweep (§18) not constructed — loop BPM ground truth
  came from real vendor filenames, which skewed toward 100–135 BPM; extreme tempos (60–70,
  174–190) were not directly exercised on real audio.
- Metadata-vs-filename BPM precedence conflict case (§22) not exercised on real audio — no
  file in the corpus carried embedded BPM metadata.
- OOD corpus (250 samples) is single-vendor "hard OOD" (real musical loops flagged
  out-of-distribution by the owner), not a broad cross-domain OOD stress test.
- Bass Loop / Synth Loop taxonomy classes are never correctly predicted by either PRE-V4 or V4
  (pre-existing gap, not scored as a V4 regression, not fixed here).

---

## 17. Ship Recommendation

**Do not promote to `main` / installation yet.** Per §35's 15-point gate:

| # | Criterion | Status |
|---|---|---|
| 1 | Vocal→Drums materially reduced | ✅ (1.96%→1.31%) |
| 2 | Vocal recall improves/strong | ✅ (+18.9pp) |
| 3 | Kick precision up, recall intact | ✅ (26.8%→93.5%, recall unchanged) |
| 4 | Macro F1 no regression | ✅ (+0.198) |
| 5 | ML override precision acceptable | ✅ (1.00 on this corpus) |
| 6 | Harmful overrides controlled | ✅ (0 observed) |
| 7 | OOD false-known understood & acceptable | ❌ **89.6% false-known rate — not acceptable** |
| 8 | Confidence not grossly misleading | ⚠️ non-monotonic; needs the source-mixing fix in §9 |
| 9 | One-shots don't get widespread fake BPM | ✅ **after the §10 fix** (was a real FAIL before) |
| 10 | BPM performs reasonably on real loops | ❌ weak (11.6% exact, ~52 BPM MAE) |
| 11 | Half/double-time quantified | ⚠️ partially (6/95 observed; not exhaustively tested) |
| 12 | Scanner performance acceptable | ✅ (~65ms/file cold, ~4.6ms/file cached) |
| 13 | Phase-1 cache hardening tests pass | ✅ (8/8) |
| 14 | No owner data modified | ✅ |
| 15 | No real-time-thread regression | ✅ |

**Classification is ready to ship.** BPM is not — recommend exposing it as a low-confidence/
"estimated" hint rather than a trusted number until loop-tempo accuracy improves, and the OOD
gate needs real work (it is currently close to non-functional on hard real-world material)
before ML overrides are allowed to run unsupervised on OOD-heavy libraries. Recommended next
phase: (a) improve/replace the OOD score used for gating (current MSP/Entropy/Margin-style
scores, per the pre-existing `ood_results.json` research artifact, show only ~0.70 AUROC even
in isolation — consistent with the 89.6% integrated false-known rate found here), (b) revisit
the acoustic tempo estimator's confidence gate and/or restrict acoustic BPM to files whose
taxonomy is loop-like, (c) fix the two filename-token-precedence findings in §12, (d) resolve
the 8 documented bad flips (§4) in the Snare/rimshot heuristic.
