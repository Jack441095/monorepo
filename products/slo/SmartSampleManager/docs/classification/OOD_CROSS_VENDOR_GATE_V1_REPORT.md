# SLO OOD Cross-Vendor Gate V1 Report

**Generated for:** SLO Master Plan V2, Phase 6 (B-007)
**Corpus:** 168 real, genuinely out-of-SLO-taxonomy files across 2 vendors — 80 from a park-equipment field recording ("Syd Park Play Equipment"), 80 from a location field recording ("Leichhardt 14-3-15"), 8 real guitar loops (guitar has no dedicated slot in SLO's 17-class taxonomy). Cross-checked against the 620-file known-population audio-only slice already produced for B-006 (`REAL_CORPUS_CROSS_VENDOR_V1_REPORT.md`) — no new scan needed for that half.

**Ground truth:** these are content categories SLO's taxonomy (Kick/Snare/.../Music Loop, 17 classes) has no slot for. Filenames are fully generic (`SYDPARK-LONG-001.wav`, `LEICH-4-3-15-002.wav`) — no taxonomy keyword collisions, confirmed matched purely via `DSP` evidence in every case (i.e. these results reflect the actual OOD gate's behavior, not a filename shortcut bypassing it).

## Headline numbers

| Metric | Population | Rate |
|---|---|---|
| **False-known** (genuinely OOD content confidently classified as a known category) | 168 real out-of-taxonomy files | **72.0%** (121/168) |
| **False-unknown** (genuinely known content wrongly flagged Unknown) | 620 real known-taxonomy files (audio-only, forced through DSP path) | **17.7%** (110/620) |

**Context**: the previously-recorded false-known baseline (`SLO_CLASSIFICATION_V4_FINAL_CLOSEOUT_REPORT.md`) was 41.6% full-corpus / 47.2% holdout — measured entirely on the single-vendor KSHMR calibration corpus. This is the first cross-vendor, genuinely-novel-content measurement, and it's meaningfully worse (72.0% vs ~42-47%). This is not necessarily a regression — the prior number likely measured near-miss confusions *within* the known taxonomy's own calibration set, while this measurement is against content the gate has never seen anything resembling. Both numbers are honest; they are not measuring quite the same thing, and that distinction matters more than which one is "worse."

## Per-source breakdown (false-known)

| Source | Rate |
|---|---|
| Guitar loops (real instrument, no taxonomy slot) | **100%** (8/8) |
| Syd Park field recording | 75.0% (60/80) |
| Leichhardt field recording | 66.2% (53/80) |

Every single guitar loop was confidently misclassified rather than flagged Unknown — small sample (n=8) but a clean, unambiguous signal given 100% concordance.

## What the false-known predictions were labeled as

`Percussion` dominates (69/121, 57%) — plausible: field recordings of playground equipment and outdoor location sound have real percussive transient characteristics acoustically, even though they aren't percussion instruments. Mean confidence on these wrong predictions was 0.778 — the gate isn't hedging, it's confidently wrong.

## Per-class false-unknown rate (known population)

Ranges from 0% (Clap) to 55% (Foley) — classes with more acoustically-diffuse signatures (Foley, Atmosphere, Impact) get wrongly flagged Unknown far more often than classes with sharp, distinct transients (Clap, Kick, Snare). Full table in this report's generating script output.

## Interpretation

The gate is biased toward accepting content as known rather than flagging it Unknown — consistent with a threshold calibrated to minimize disruption on the training/calibration vendor's own content, at the cost of poor discrimination against genuinely novel material. This is a real, actionable finding for whoever next tunes the OOD threshold, not a reason to distrust the gate's basic architecture (see `SLO_CLASSIFICATION_V4H_FINAL_CALIBRATION_REPORT.md` for the calibration methodology this measurement builds on).

## UI-visibility fix landed alongside this report

Found and fixed a separate, concrete gap while investigating this blocker's "visible Unknown behavior" requirement: `PluginEditor.cpp` showed the identical "not yet classified" text for both never-scanned files and genuinely OOD-cleared files — there was no way for a user to tell "hasn't been scanned" apart from "was scanned and doesn't fit any category." Fixed using the already-existing `taxonomyVersion` field (0 = never classified under this taxonomy system) to distinguish the two states; OOD-cleared samples now show "Unknown (doesn't match a known category)" instead. See commit on `engineering/slo-v2-phase6-ood-gate`.

## Scope limitations

- Negative set is 2 vendors, not a broad sample — field-recording/found-sound content and one real-instrument gap (guitar). Other genuinely-OOD content types (other missing instrument families, other field-recording styles) are unmeasured.
- Ground truth for the negative set is judgment-based (this content clearly isn't in the 17-class taxonomy), not independently verified by a second reviewer.
- Per-source counts (80/80/8) are capped for runtime, not exhaustive of the source folders (210 and 260 files respectively were available).
