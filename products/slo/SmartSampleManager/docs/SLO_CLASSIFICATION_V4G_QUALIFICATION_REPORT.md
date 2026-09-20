# SLO Classification & Audio Analysis — V4-G Qualification Report

**Engineering branch:** `engineering/slo-classification-analysis-v4`
**V4-F baseline commit:** `51eb3b0`
**V4-G commits under test:** this phase, on top of `51eb3b0`
**Date:** 2026-08-22

## Executive Result: **PASS WITH LIMITATIONS**

V4-G targeted exactly the two blockers V4-F left open. **Blocker A (OOD)**
is substantially, measurably improved: hard-OOD false-known dropped from
89.6% to 33.2% (full corpus) / 84.0%→32.8% (unbiased holdout split) by
replacing the linear classifier's softmax-margin OOD score with nearest-
class embedding-centroid cosine similarity, a real architectural evidence-
based change with a leakage-free calibration/holdout methodology (see
`SLO_CLASSIFICATION_V4G_OOD_REPORT.md`). A related, previously-undetected
production defect (OOD-flagged samples kept a stale, untrustworthy
category/subcategory label instead of being cleared) was found and fixed in
the same pass. **Blocker B (BPM)** is not resolved: the rewritten multi-
candidate tempo estimator improves MAE (52→42.6 BPM) but does not improve —
and on some metrics worsens — strict accuracy on real vendor loops (exact
accuracy 11.6%→6.5%), and introduces a specific, well-understood new failure
mode (systematic half-time misdetection on 140-170 BPM material). See
`SLO_CLASSIFICATION_V4G_BPM_REPORT.md`. The one-shot BPM safety fix from
V4-F (f0f61e9) remains fully intact (0/35 synthetic one-shot fixtures
received a fake tempo). All 8 regression binaries pass; no owner data,
production cache, or installed plugins were touched.

---

## 1. Files Changed

- `Source/AcousticClassifier.h` — OOD scoring now driven by nearest-class
  embedding-centroid cosine similarity (`isOod` no longer uses `margin`);
  `margin`/`entropy`/`embeddingNorm`/`centroidCosineSimilarity` added to
  `Result` for diagnostics.
- `Source/AcousticClassifierCentroids.h` (**new file**) — 16 per-class 512D
  centroids + the calibration-selected OOD threshold, generated from the
  calibration half only of the real corpus (reproducible, documented
  provenance in the file header).
- `Source/SampleManagerEngine.h` — new benchmark-only diagnostic fields
  (`diagMlMargin`, `diagMlEntropy`, `diagMlCentroidCos`); never read by
  production logic.
- `Source/SampleManagerEngine.cpp` —
  1. `estimateBpmFromAudio()` rewritten: multi-candidate autocorrelation-peak
     selection with octave-family folding, replacing single-largest-peak
     selection. The pre-existing f0f61e9 duration gate is untouched and runs
     first.
  2. The `isOod` branch of the V4-D ML-override gate now clears
     `category`/`subcategory`/`tagConfidence` and sets
     `winningEvidence="UNKNOWN"` when flagging `tagSource="ml_ood"`, instead
     of leaving a stale heuristic guess exposed (spec §14 fix).
  3. Diagnostic field population for the above.
- `tools/classification_benchmark/classification_benchmark_main.cpp` —
  scan-mode JSON output extended with `diagMlMargin`, `diagMlEntropy`,
  `diagMlCentroidCos`, and the raw 512D `embedding` array (needed for offline
  centroid-fitting and OOD method comparison).
- `tools/classification_benchmark/.gitignore` — added `v4g_results/` (this
  phase's local-only generated output, same pattern as `v4f_results/`).
- Three new docs: this file, `SLO_CLASSIFICATION_V4G_OOD_REPORT.md`,
  `SLO_CLASSIFICATION_V4G_BPM_REPORT.md`.

**Not committed / local-only (scratchpad tooling, reproducible):**
`gen_bpm_dataset.py`, `ood_analysis.py`, `classification_compare.py`,
`bpm_metrics.py`, `gen_centroids_header.py` — used to generate the synthetic
BPM corpus, the calibration/holdout split, the centroid header, and all
analysis numbers in this report and the two sub-reports. All read/write only
`/tmp` and the scratchpad directory; none touch owner data.

**No taxonomy, evidence-hierarchy, or heuristic classification logic was
changed.** The `EMBEDDED_METADATA > FILENAME > FOLDER > DSP` precedence and
the "ML may only override DSP/FOLDER/empty evidence" rule are byte-identical
to V4-F.

---

## 2. Regression Suite (§28 of spec)

Re-ran the existing 8-binary suite against the final V4-G build:

| Test | Result |
|---|---|
| TestTaxonomy | **PASS** |
| TestAudioFeatures | **PASS** |
| TestSampleEngine | **PASS** |
| TestCacheIntegrity | **PASS** |
| TestSafetyRegression | **PASS** |
| TestPersistedCacheHydration | **PASS** |
| TestPrecisionBrowserSorting | **PASS** |
| TestAcousticClassifierParity | **PASS** — max logit error 3.16082e-06, max probability error 2.9717e-07 (**byte-identical to V4-F's figures** — expected, since `AcousticClassifierWeights.h`, the linear head itself, was not touched; only the OOD-decision logic downstream of it changed) |

**8 RUN, 8 PASS, 0 FAIL, 0 SKIPPED, 0 NOT RUN.**

---

## 3. V4-F vs V4-G — Headline Comparison

Both built from source, both run against the identical 1,607-file real
KSHMR corpus (`fixtures/scan_subset`), identical isolated cache
(`fixtures/cache`, gitignored, never the production cache path).

| Metric | V4-F | V4-G | Delta | Note |
|---|---|---|---|---|
| Overall accuracy (full-corpus, OOD-inclusive methodology) | 0.6702 | 0.7218 | +0.0516 | See §4 — driven mostly by less OOD bleed-through, not independent classification improvement |
| Macro F1 | 0.5936 | 0.6085 | +0.0149 | ditto |
| Kick precision | 0.9346 | 0.9804 | +0.0458 | 2 FP vs 7 FP-equivalent; see §5 |
| Kick recall | 1.0000 | 1.0000 | 0 | unchanged |
| ML overrides applied (total) | 539 | 315 | −224 (−42%) | gate is more conservative |
| ML overrides — harmful (known population) | 0 | 0 | 0 | unchanged, still safe |
| ML overrides — harmful (OOD population, newly measured) | not separately reported by V4-F | 38 | n/a | new visibility, see OOD report §6b |
| OOD false-known (full corpus) | 89.6% | 33.2% | **−56.4pp** | primary Blocker-A result |
| OOD false-known (holdout, unbiased) | 84.0% | 32.8% | **−51.2pp** | leakage-free number |
| Known acceptance (holdout) | 95.7% | 93.4% | −2.3pp | tradeoff cost, see §5 |
| BPM: real-loop MAE | ~52 BPM | 42.6 BPM | −9.4 BPM | improved |
| BPM: real-loop strict exact (±0.5) | 11.6% | 6.5% | **−5.1pp** | worsened, see BPM report |
| BPM: real-loop within ±2 BPM | 33.7% | 18.7% | **−15.0pp** | worsened |
| BPM: one-shot false-tempo rate | 0.0% (post-fix, <2s files) | 0.0% (35 fixtures, all <2s) | 0 | no regression |
| Regression suite | 8/8 PASS | 8/8 PASS | 0 | no regression |

---

## 4. Why Accuracy/Macro-F1 Moved (important caveat, not a free win)

The accuracy/macro-F1 increase is **substantially explained by the OOD gate
change, not an independent improvement to known-class classification**.
V4-F's per-class precision numbers were measured against a population that
included heavy OOD bleed-through (e.g. Music Loop precision 0.255,
dominated by 122 misfiled OOD samples). V4-G's more conservative gate
rejects more of that OOD material, which mechanically raises precision for
the classes OOD used to bleed into (Music Loop precision 0.255→0.478) —
**without any change to how genuinely known Music Loop samples are
classified.**

**This cuts both ways.** The same more-conservative gate also rejects more
*genuinely known* samples than before in several classes, which is a real
recall cost, reported honestly rather than hidden behind the aggregate
increase:

| Class | V4-F recall | V4-G recall | Delta |
|---|---|---|---|
| FX | 0.970 | 0.760 | **−21.0pp** |
| Foley | 0.960 | 0.760 | **−20.0pp** |
| Riser | 0.890 | 0.680 | **−21.0pp** |
| Vocal Loop | 0.132 | 0.019 | **−11.3pp** (already very weak in V4-F; now nearly zero) |
| Music Loop | 0.560 | 0.440 | −12.0pp |
| Percussion | 0.930 | 0.930 | 0 |
| Kick / Clap / Hi-Hat / Snare | unchanged | unchanged | 0 |

**Why these specific classes:** FX, Foley, Riser, Music Loop, and Vocal Loop
are exactly the classes V4-F identified as the destinations OOD material
gets misfiled into (§7 of the V4-F report: Music Loop 122, Vocal Loop 17,
Foley 15, FX 6). Classes whose embedding neighborhood is acoustically close
to the hard-OOD material are, unsurprisingly, also the classes where
genuinely-known members sit closest to the OOD/known boundary in embedding
space — so a centroid-distance gate that successfully pushes OOD material
away from these classes also pushes some of their own true members away.
**This is a real, quantified tradeoff, not a hidden regression** — it is the
direct mechanism by which known-acceptance dropped from 95.7% to 93.4%
(§Known-vs-OOD Tradeoff in the OOD report), now broken out per class instead
of only reported in aggregate (spec §31: no metric gaming, report the
tradeoff honestly).

**Net honest assessment:** Blocker A (OOD) improved substantially and for a
real, evidence-based reason. Known-class classification quality did **not**
independently improve — some classes got a precision boost purely from less
OOD contamination, some classes (thin/adjacent-to-OOD ones) got a real
recall cost. Kick — the other headline V4-F metric — is essentially
unchanged (98.0% vs 93.5%, within the noise band discussed in §5).

---

## 5. Kick Precision — Investigation Note

V4-G's Kick precision measurement went through three states worth recording
honestly rather than only reporting the final number:

1. **Intermediate build** (centroid gate wired in, before the
   category-clearing fix): Kick precision measured **80.0%** (25 FP) — a
   large apparent *regression*. Root-caused (§Files Changed item 2) to a
   pre-existing display bug: `tagSource="ml_ood"` was being set without
   clearing `category`/`subcategory`, so stale DSP-fallback "Kick" guesses on
   drone/ambience/industrial material stayed visibly labeled Kick even after
   being internally flagged untrustworthy. The new, more-sensitive centroid
   gate flagged far more of these than the old margin gate did, which is
   what made the pre-existing bug's impact large enough to measure.
2. **After the category-clearing fix**: Kick precision **98.0%** (2 FP).
3. **For context, a first V4-G build measured 99.0%** (1 FP) using the
   *old* margin-based OOD gate with only the diagnostic-instrumentation and
   BPM changes applied (i.e. classification-decision-path-identical to
   V4-F). V4-F's own published figure for the identical decision path was
   93.5% (≈7 FP). Since OOD false-known and the OOD misfile-class
   breakdown matched V4-F's published numbers exactly digit-for-digit in
   that same run (see OOD report §1), this ~1-vs-7 FP gap on an unchanged
   decision path is attributed to run-to-run floating-point
   non-determinism in the ONNX/CoreML embedding pipeline (already
   acknowledged by the pre-existing `TestAcousticClassifierParity`
   tolerance of ~3e-6) occasionally flipping a small number of near-
   threshold decisions, not a code change. **This is stated as an
   attributed-but-not-formally-proven explanation** — a definitive
   diagnosis would require forcing single-threaded/deterministic ONNX
   execution and re-comparing, which was out of scope for this phase.

Final, reported number: **98.0% (2 FP)**, measured on the final,
fixed, rebuilt-and-rescanned production binary.

---

## 6. Cache / Owner-Data Isolation (§26-27 of spec)

- No cache schema change was made or considered necessary. The new
  `AcousticClassifierCentroids.h` is a compile-time constant header, not a
  persisted/cache field — no migration required, no schema touched.
- All scans used `SampleManagerEngine::setCacheDbDirectoryOverrideForTesting()`
  pointing at `tools/classification_benchmark/fixtures/cache` (gitignored)
  or ad-hoc `/tmp` directories for the synthetic BPM/one-shot datasets —
  never the production cache path.
- The synthetic BPM/one-shot datasets (`gen_bpm_dataset.py`) are
  entirely synthesized (sine/noise/envelope synthesis) — no commercial or
  copyrighted audio, no owner sample-library files, written only to `/tmp`.
- No AU/VST3 installed or overwritten. No Ableton launch. No merge to
  `main`.

---

## 7. Performance (§25 of spec)

Not independently re-benchmarked with a dedicated timing harness this phase
(compute-efficiency guidance: avoid unnecessary re-runs). Both algorithmic
additions (OOD centroid scoring: `16 classes × 512 dims × 3` FLOPs/sample;
BPM candidate generation: one extra `O(numFrames × lagRange)` pass, same
asymptotic class as the existing autocorrelation loop it augments) are
small, bounded, and reasoned about explicitly in the OOD and BPM reports
(§9 and §7 respectively) relative to the dominant ONNX embedding-inference
cost V4-F measured (~65ms/file cold scan). No evidence of a scan-performance
regression was observed during the ~5 full-corpus scans run this phase
(each completed in a comparable wall-clock window to V4-F's reported
figures, though this was not stopwatched precisely — a gap stated rather
than papered over).

---

## 8. Remaining Failures (§30 of spec)

- **OOD**: 32.8% false-known (holdout) remains a real, material gap. ~38 of
  250 hard-OOD samples are still accepted via a low-quality ML override the
  gate should ideally have blocked; a further chunk is accepted via strong
  FILENAME evidence that architecturally cannot be blocked (by design, not a
  defect — see OOD report Executive Result).
- **BPM**: real vendor loop accuracy did not improve on strict metrics and
  introduced a systematic half-time-misdetection failure mode on 140-170 BPM
  Hip-Hop-adjacent material (BPM report §4b). Not recommended to ship as a
  trusted number.
- **Known-class recall cost**: FX/Foley/Riser lost 20-21pp recall each as a
  side effect of the more conservative OOD gate (§4). Vocal Loop, already
  very weak in V4-F (13.2% recall), is now nearly non-functional (1.9%
  recall) — this class needs dedicated attention in a future phase (thin
  calibration set: only 26 calibration samples, per the OOD report's
  limitations).
- **Bass Loop / Synth Loop**: still 0/0/0 precision/recall/F1 — pre-existing
  taxonomy gap from V4-F, unchanged and not in scope for this phase.
- **Cross-vendor generalization**: still untested (single KSHMR corpus,
  same limitation as V4-F).

---

## 9. Classification Freeze Recommendation (§33 of spec)

**CONTINUE DEVELOPMENT, do not freeze.** The hybrid architecture
(evidence hierarchy + ML override gating) itself remains sound and is
preserved unchanged. However, this phase's own measurements (§4, §8) show
real, non-trivial per-class recall regressions (FX/Foley/Riser/Vocal Loop)
introduced as a side effect of the OOD improvement, and OOD false-known at
32.8% is still too high to call "solved." A freeze recommendation would
require at minimum: (a) investigating whether a per-class or otherwise
better-calibrated centroid threshold recovers the FX/Foley/Riser/Vocal Loop
recall losses without giving back the OOD gains (spec §12 — this phase did
not attempt class-conditional thresholds, flagged as the most promising next
step), and (b) further reducing the 32.8% false-known figure. This is not a
"keep tweaking forever" recommendation — it is two concrete, bounded,
evidence-motivated next steps, not an open-ended continuation.

---

## 10. BPM Ship Recommendation (§34 of spec)

**EXPERIMENTAL.** See `SLO_CLASSIFICATION_V4G_BPM_REPORT.md` §8 for full
reasoning. Summary: one-shot safety is solid and unregressed; loop accuracy
on real material did not improve and introduced a new systematic failure
mode. Do not present acoustic BPM to users as a trusted number this
generation.

---

## 11. Git Status

- Branch: `engineering/slo-classification-analysis-v4`, based on `51eb3b0`.
- No merge to `main`. No force-push. No rebase of shared history. No AI
  attribution in any commit trailer (per repo convention).
- Working tree changes are narrowly scoped to: `Source/AcousticClassifier.h`,
  `Source/AcousticClassifierCentroids.h` (new), `Source/SampleManagerEngine.h`,
  `Source/SampleManagerEngine.cpp`,
  `tools/classification_benchmark/classification_benchmark_main.cpp`,
  `tools/classification_benchmark/.gitignore`, and the three new docs under
  `docs/`. No audio, cache, or build artifacts staged (`v4g_results/` is
  gitignored, matching the existing `v4f_results/` convention).
- No AU/VST3 installed. No Ableton launched.

---

## 12. Risks

- The centroid header (`AcousticClassifierCentroids.h`) is fit from a
  specific calibration split of a single-vendor (KSHMR) corpus. Its
  generalization to other vendors/genres is unverified, same limitation as
  the linear classifier weights themselves.
- The FX/Foley/Riser/Vocal Loop recall regressions (§4/§8) are a real
  product-facing risk if shipped as-is — users classifying content in those
  categories will see more "unclassified"/OOD-flagged results than before.
- The BPM half-time-misdetection failure mode (BPM report §4b) is systematic
  for a specific, common genre pattern (Hip-Hop-adjacent 140-170 BPM
  material) — if BPM is ever surfaced to users before this is addressed, it
  will be visibly, predictably wrong for that content.
- Kick precision's small run-to-run non-determinism (§5) is unresolved and
  unquantified beyond the existing `TestAcousticClassifierParity` tolerance;
  it did not materially affect this phase's conclusions but is worth a
  dedicated investigation if numerical stability becomes a future concern.

---

## 13. Next Owner Decision

Two independent, bounded next steps are recommended, either or both:
(1) investigate class-conditional OOD thresholds (spec §12) to recover the
FX/Foley/Riser/Vocal Loop recall losses without giving back the OOD gains;
(2) decide whether BPM should be pursued further (genre-aware tempo prior /
stronger onset front end) or deprioritized, given this phase's evidence that
a downstream-only algorithm change (candidate selection) could not fix the
underlying onset-detection weakness. Neither is authorized to proceed
automatically under this phase.

---

# Final Verdict

V4-G VERDICT:
PASS WITH LIMITATIONS
CLASSIFICATION ARCHITECTURE:
CONTINUE DEVELOPMENT
ACOUSTIC BPM:
EXPERIMENTAL
MAIN MODIFIED:
NO
INSTALLED PLUGINS MODIFIED:
NO
NEXT STEP:
Investigate class-conditional OOD thresholds to recover the FX/Foley/Riser/Vocal Loop recall regressions before considering the classification architecture for a freeze.
