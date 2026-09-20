# SLO FX/Foley/Riser Forensic Audit V1

**Generated for:** SLO Master Plan V3 (accuracy improvement follow-on to V2)
**Method:** the same per-sample forensic method that found the Vocal Loop "BVs" defect — cross-referencing ground truth against predicted subcategory and winning evidence — applied to the other three classes V4-H's original forensics flagged as OOD-threshold-attributed (FX, Foley, Riser), per the V5 research baseline's #2-ranked recommendation ("filename/evidence heuristic audit beyond Vocal Loop, generalized"). Reuses the existing B-006 `results_real_corpus_full.json` scan — no rescan needed.

## Honest headline: this audit did NOT find a clean, fixable defect like Vocal Loop's

Unlike Vocal Loop (one dominant cause, 88% of errors, a one-line fix), FX and Foley's errors are a mix of two different things, neither of which is a quick heuristic patch:

### 1. A ground-truth quality problem in this session's own B-006 corpus (not a classifier defect)

Several "FX" ground-truth entries are actually individual instrument stems from a track ("Koan Sound — Sentient"), each filename literally naming its own real content: `Sentient - Hi-Hat.wav`, `Sentient - Snare.wav`, `Sentient - Kick.wav`, `Sentient - Bass Guitar.wav`, `Sentient - Vox.wav`, `Sentient - Percussion.wav`. The classifier calling these "Hi-Hat," "Snare," "Kick," etc. via FILENAME evidence is **correct** — the "FX" label these got in B-006's corpus-sampling was wrong, most likely from a folder-keyword match (`fx` in a parent "stems" folder name) that didn't account for individually-named stems inside it. Similar pattern in "Drum Recollection" (`Snap 1/2.wav`, `Static Perc.wav`, `Gulag Perc.wav` — all keyword-labeled FX via folder, but filenames clearly indicate Snare/Percussion-family content).

**Action taken: none to the classifier.** This is a correction to how future sessions should read B-006's FX numbers, not a code defect. Recorded here so nobody re-derives it from scratch, and so `REAL_CORPUS_CROSS_VENDOR_V1_REPORT.md`'s FX accuracy figures are read with this caveat in mind.

### 2. A real, but not cheaply fixable, Foley-specific weakness

Foley's real accuracy (excluding the mislabeled entries above) is genuinely low — a large fraction of real Foley content (water bottles, skateboards, rain, bubble wrap, eating chips) gets flagged **Unknown** (matching B-007's independently-measured 55% Foley false-unknown rate), and much of the rest gets **high-confidence wrong** DSP-based predictions (`Metal Water Bottle-7.wav` → Percussion at 94-97% confidence; `Log Crunch 3/7/9.wav` → FX at 91-100% confidence). This is not a filename-precedence issue the way Vocal Loop was — these are mostly generically-named files reaching the DSP/embedding classifier honestly, and the classifier is confidently getting them wrong. Fixing this for real would mean either embedding-space work or threshold recalibration — both are the higher-cost, evidence-gated items the V5 research baseline already ranks below dataset expansion (see its §6, items 6-9), and threshold recalibration specifically touches the spec-frozen per-class OOD mechanism (see `SLO_PRIVATE_BETA_READINESS_V1.md`'s note on that freeze — not reopened here).

### Riser: too small a sample to conclude anything (10/15 correct, n=15)

A couple of filename-precedence-shaped misses (`Riser - Bass Pulse - 85 BPM.wav` → Bass One-Shot via the "bass" keyword outranking the Riser folder context; `Riser - Impact Rise.wav` → Impact via the "impact" keyword) look superficially similar to the Vocal Loop pattern, but n=15 (and only 5 errors) is too small to justify a scoped fix the way Vocal Loop's 46/52-sample pattern was. Flagged for a future session with more Riser-specific data, not acted on here.

## Why nothing was fixed here (beyond documenting it)

Per this plan's own discipline: don't invent a heuristic fix without the kind of clear, dominant, well-evidenced single cause Vocal Loop had. FX's real problem is upstream in this session's own corpus-sampling (fixed by reading the numbers correctly, not by changing product code); Foley's real problem needs data/model-level work explicitly out of scope for a same-session patch; Riser's sample is too thin to act on. Reporting a null/mixed result honestly is the correct outcome of an audit, not a failure of it.
