# SLO Producer Taxonomy Requirements V1

**Purpose:** define the fine-grained, producer-facing classification layer Jack asked for — richer than "similarity," genuinely explaining *what a sound is*. This is a requirements + status doc, not a claim that everything below is built. Read `NITE_DSP_SLO_FINE_SUBCATEGORIZATION_V1.md` for the evidence-gated build process this follows.

## Design principle (non-negotiable, already established in the codebase before this doc)

`AbletonTaxonomy.h`'s own header comment: *"Deliberately does NOT attempt distinctions the current DSP feature set can't actually support with real confidence... inventing those would mean presenting a guess as a classification, which the design explicitly rejects."* Every layer below follows the same rule: **measure real separability on real audio before shipping a label.** A subtype or attribute that can't clear a real accuracy bar on held-out data doesn't ship — the system says "likely X, uncertain" instead of guessing.

## The four-layer schema

### 1. Primary type
**Status: exists today, close but not identical to the requested list.** Current production categories (`AbletonTaxonomy::Classification::category`/`subcategory`): Kick, Snare, Hi-Hat, Clap, Percussion, Bass One-Shot, Bass Loop, Synth, Synth Loop, Vocal Phrase, Vocal Loop, Impact, Riser, Foley, FX, Atmosphere, Music Loop (17 classes) + Unknown/OOD. The requested list (kick, bass, snare, clap, hi-hat, percussion, loop, vocal, pad, stab, riser, impact, texture/foley, FX, unknown) is a coarser grouping of largely the same territory — Pad and Stab specifically aren't separate today (currently folded into "Synth"). **Gap to close**: decide whether Pad/Stab need their own primary-type slots or stay as subtype/attribute-level distinctions under Synth — this is a product judgment call, not an engineering one; recommend deciding with real Pad vs Stab audio in front of you (same separability-first method as everything below) rather than assuming.

### 2. Subtype
**Status: methodology proven, one subtype shipped, most of the list not yet attempted.**

| Requested subtype | Status | Evidence |
|---|---|---|
| 808 bass | **Shipped** | 92.9% leakage-free holdout accuracy, real cross-vendor data. `docs/classification/BASS_TIMBRE_TAG_V1_REPORT.md` |
| Reese bass | **Shipped** | Same test as above (paired classification) | 
| Large/small kick | **Shipped** | Honest, stated 0.7s duration threshold (median of real, non-outlier corpus data) — not a discovered natural category, presented as such. `docs/classification/KICK_LENGTH_TAG_V1_REPORT.md` |
| Open hat, closed hat | **Shipped** | 92.3% leakage-free holdout accuracy, 103 real cross-vendor files. `docs/classification/HIHAT_TYPE_TAG_V1_REPORT.md` |
| Sub bass, distorted bass | **Not attempted** | Same embedding-separability test as 808/Reese needs running before building anything |
| Acoustic snare, rimshot | **Not attempted** | ″ — good next candidate, similar acoustic clarity to open/closed hi-hat |
| Crash, ride | **Not attempted** | ″ |
| Vocal chop, tonal loop, drum loop, one-shot | **Partially exists** — Loop vs One-Shot secondary tag already exists (`AbletonTaxonomy.cpp`'s loop-vs-one-shot logic, plus the Vocal Loop/Phrase disambiguation work in V1-V3). "Vocal chop" and "tonal loop" specifically as distinct labels: not attempted. |

**Recommended next 2-3, in priority order** (open/closed hi-hat is the strongest bet — sharp, well-known acoustic distinction, likely high separability; sub vs distorted bass is a natural extension of the 808/Reese work already proven; large/small kick is cheap since duration is already computed) — but this should be confirmed with Jack, not assumed, since "very important for the product's design" implies specific producer workflows matter more than engineering convenience.

### 3. Attributes
**Correction (2026-08-28): this section's original "not started" verdict was wrong** — the result of incomplete research the first time through, not a discovery of a real gap. A separate, richer, already-shipped attribute system exists (`generatePredictedTags()` / `SampleManagerEngine::getPredictedTags()`, wired live into the UI's "Suggested: ..." tags, covered by a passing `TestAutoTagging`). This codebase has **two intentionally separate feature structs**, per `SampleManagerEngine.h`'s own header comment: `AudioFeatures` (taxonomy-only: zcr, low/high energy ratio, decay time, pitch sweep — what `AbletonTaxonomy::classify()` uses) and `AudioAnalysisResult` (the richer set: real FFT-derived spectral centroid, spectral rolloff, crest factor, spectral-flux-based onset count, zero-crossing rate — what predicted-tags and "Find Similar" weighted search use). Missing this the first time was a real research failure worth naming plainly, not glossing over.

**Already shipped, already live** (via `generatePredictedTags()`):
- **Bright** (spectralCentroid ≥ 4000Hz) / **Dark** (< 1200Hz) — real FFT spectral centroid, not a crude proxy.
- **Punchy** (crestFactor ≥ 4.0, real peak/RMS ratio).
- **Transient** (onsetCount ≥ 3, spectral-flux-based onset detection).
- **Noisy** (zeroCrossingRate ≥ 0.15) / **Tonal** (< 0.03) — a *different*, more carefully calibrated ZCR field than the taxonomy-only one this session's decay-time fix touched.
- **Long Decay** (decayTimeSeconds ≥ 2.0s) / **Short Decay** (< 0.12s) — bridged from the taxonomy-only `AudioFeatures` struct into `AudioAnalysisResult` via a shared `computeEnvelopeDecayTimeSeconds()` helper; thresholds calibrated against the real 620-file B-006 corpus. See `docs/classification/DECAY_ATTRIBUTE_TAG_V1_REPORT.md`.
- **Wide** (stereoCorrelation < 0.5) / **Mono** (originalChannels == 1, or stereoCorrelation ≥ 0.98) — new `AudioAnalysisResult::stereoCorrelation` field (L/R Pearson correlation), calibrated against the real 620-file corpus and found to match known mixing convention (bass/kick/vocals kept mono/centered; risers/pads/foley routinely stereo-widened). See `docs/classification/WIDE_MONO_ATTRIBUTE_TAG_V1_REPORT.md`.

That's 10 of the requested 16 attributes already done, with better signal quality than this document originally assumed was possible.

**Investigated and explicitly rejected** (not a gap — a measured null result):
- **Sustained/Percussive** — tested as a `decayTimeSeconds/duration` ratio (the same shape of signal `detectLoopVsOneShot()` uses, at a different threshold). Real corpus data showed this ratio is dominated by where a sound's envelope peak falls within its own file length, not by genuine sustain character: Riser scored the *lowest* median ratio and Bass One-Shot the *highest*, backwards from any producer's intuition. Does not ship. Full evidence in `docs/classification/DECAY_ATTRIBUTE_TAG_V1_REPORT.md`.

**Genuinely still missing** (checked directly against `AudioAnalysisResult`'s actual fields — no distortion/THD field exists anywhere):
- **Saturated/distorted/clean** — needs harmonic-distortion analysis (e.g. THD estimate); not computed anywhere. The largest remaining gap: unlike everything shipped so far, this needs genuinely new DSP work, not bridging an already-computed signal.
- **Low-end heavy** — the taxonomy-only `lowEnergyRatio`/`highEnergyRatio` exists but isn't wired into `generatePredictedTags()`. The redundancy audit is now complete on 1,850 physical cards: a 0.60 low-band threshold flags 709/1,850 (38.3%) and overlaps the existing Dark band for only 331/709 (46.7%), with substantial heterogeneous-class coverage. This remains a physical descriptor, not an attribute ground truth; explicit owner labels are required before shipping the tag. See `tools/classification_benchmark/receipts/low_end_heavy_redundancy_audit_1850_20260914.json`.

**Recommendation**: don't rebuild what already works. The real remaining work is new DSP feature work for Saturated/distorted/clean, plus a redundancy check (then possible bridging) for Low-end Heavy — neither attempted in this pass. With 10 of 16 shipped and 1 honestly rejected, the attribute layer is close to as complete as this feature set supports; the two remaining items are lower-value or higher-cost than what's already shipped, making this a reasonable point to check in on product priority for what's left versus moving on to the subtype list.

### 4. Confidence
**Status: infrastructure already exists, needs extending to new tags.** `tagConfidence` (0-1 float) and a "NEEDS REVIEW" UI threshold at 0.5 already exist and are wired into the UI (`PluginEditor.cpp`). `BassTimbreClassifier::Result::confidence` already follows this pattern. **Recommendation**: standardize on three UI-facing bands (high/medium/low) mapped from the underlying float, rather than inventing a new confidence representation — reuse what's proven, don't add a second parallel confidence system.

## Unknown handling

**Status: exists and just got more honest.** The OOD gate (`AcousticClassifier`) already exists; B-007's work this session measured its real cross-vendor false-known rate (72%) and fixed a UI bug where "Unknown" was indistinguishable from "never scanned." The requirement "never force a confident label... return likely category, possible subtype, useful acoustic attributes, and confidence" is **not fully met yet** — today's Unknown handling is binary (known-class label, or Unknown) rather than the graduated "likely category + possible subtype + attributes + confidence, all at once" behavior requested. This is a real UX/data-model gap: closing it means restructuring how a classification result is represented (a single best label today, vs. a bundle of graduated guesses) — flagged here as real future work, not attempted in this pass.

## Versioning (already partially exists, needs extending)

`AbletonTaxonomy::kTaxonomyVersion` and `SampleItem::taxonomyVersion` already exist and gate whether cached classifications get recomputed after a taxonomy change (bumped twice already this session's lineage: Vocal Loop fix, BVs fix). **Gap**: no equivalent version field exists yet for the *embedding model* itself, the *feature-extraction* version specifically (separate from taxonomy), or a structured way to track *user-corrected* labels distinctly from machine-produced ones at the schema level (today `tagUserOverridden` is a bool, not a structured correction record). Building the full versioning matrix (taxonomy/model/feature/scan version, re-analysis-needed flag, correction provenance) is real schema work — scoped here, not built in this pass.

## What this doc is NOT

Not a claim that SLO now has "very high level" classification across the full requested list. It has: one real, validated subtype (bass timbre), a proven methodology for adding more, and a clear map of what's cheap (attributes derivable from existing features) vs. what needs new DSP work (spectral/stereo/distortion analysis) vs. what needs product judgment (which subtypes matter most, Pad/Stab primary-type question). Treat this as the honest starting map, not the finished territory.
