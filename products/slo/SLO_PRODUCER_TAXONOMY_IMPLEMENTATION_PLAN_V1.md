# SLO Producer Taxonomy Implementation Plan V1

**Purpose:** map Jack's full taxonomy spec (primary type / subtype / attributes / confidence / never-force-a-label) against what's actually shipped in this codebase, verified by direct code inspection this pass, and give a smallest-safe-next-step plan for the genuine gaps. This supersedes re-deriving from scratch — `SLO_PRODUCER_TAXONOMY_REQUIREMENTS_V1.md` (earlier this session) already did most of this analysis; this doc re-verifies it against the current code and adds the pieces the new spec asks for that weren't covered before (rimshot, pad/stab, saturated/distorted/clean, confidence bands).

## Primary type

**Spec asks for:** kick, snare, clap, hi-hat, percussion, bass, 808, loop, vocal, vocal chop, pad, stab, riser, impact, FX, texture/foley, unknown.

**Shipped today** (`AbletonTaxonomy`, 17 classes): Kick, Snare, Hi-Hat, Clap, Percussion, Bass One-Shot, Bass Loop, Synth, Synth Loop, Vocal Phrase, Vocal Loop, Impact, Riser, Foley, FX, Atmosphere, Music Loop, plus Unknown.

**Verified gaps** (grepped directly against `AbletonTaxonomy.cpp`/`.h`, confirmed absent, not assumed): **Vocal Chop, Pad, and Stab do not exist as distinct labels.** Pad/Stab content currently falls under "Synth"; Vocal Chop content falls under "Vocal Phrase" or "Vocal Loop" depending on length. "808" isn't a primary type here — it's a subtype under Bass (see below), which is arguably the more correct taxonomic level (808 is a bass sound, not a separate instrument family) but differs from the spec's flat list.

**Recommendation**: don't add these as new *primary* categories without real separability evidence first, matching this session's established discipline. Pad-vs-Synth and Stab-vs-Synth are exactly the kind of distinction `AbletonTaxonomy.h`'s own design principle warns against forcing without real DSP/embedding evidence of separability. Vocal Chop specifically is more tractable (a chop is characterized by being short + rhythmically edited, which duration + the existing loop-vs-one-shot heuristic can approximate) — **recommended as the one new primary-type-level addition worth attempting**, using the same real-corpus evidence-gated method as every other classifier this session (measure real separability before shipping).

## Subtype

**Spec asks for:** large/small/short-punchy/long-decay kick, clean/distorted 808, Reese bass, sub bass, distorted bass, acoustic/electronic snare, rimshot, closed/open hat, drum loop, melodic loop, tonal one-shot.

**Shipped and evidence-validated**: kick length (Large/Short by duration), 808/Reese bass (`BassTimbreClassifier`, 92.9% holdout accuracy), Open/Closed hi-hat (`HiHatTypeClassifier`, 92.3%).

**Verified gaps**: clean/distorted 808 split (no distortion/THD analysis exists anywhere in the codebase — confirmed by grep, zero hits); sub bass / distorted bass as sibling subtypes to 808/Reese; acoustic/electronic snare and rimshot (zero hits, not attempted); drum loop / melodic loop / tonal one-shot as an explicit distinct labeling (the Loop-vs-One-Shot secondary tag already exists and is a reasonable proxy for "loop" but doesn't distinguish drum-loop from melodic-loop specifically).

**Recommendation, in priority order** (matches the existing requirements doc's own ranking, re-confirmed): acoustic snare / rimshot is the strongest next candidate — sharp, real acoustic distinction, same profile as the already-successful hi-hat open/closed work. Clean/distorted 808 and sub/distorted bass need new DSP work (harmonic distortion analysis) that doesn't exist yet, a bigger lift than the centroid-classifier pattern used so far. None of these are implemented in this pass — each needs the same real-corpus, leakage-free validation as the shipped ones, which is real, multi-hour work per subtype, not something to rush inside this audit turn.

## Attributes

**Spec asks for:** punchy transient, long/short decay, tonal, noisy, bright, dark, saturated, clean, distorted, wide, mono, low-end heavy, transient-heavy, sustained, percussive.

**Shipped and evidence-validated** (10 of 15): Punchy, Long Decay, Short Decay, Tonal, Noisy, Bright, Dark, Wide, Mono, Transient (via onset count — close to "transient-heavy").

**Investigated and explicitly rejected** (a real null result, not an oversight): Sustained/Percussive — tested via the decay/duration ratio, found confounded by where a sound's envelope peak falls within its own file (Riser scored *lowest* sustain despite being the most sustained-sounding category) — see `docs/classification/DECAY_ATTRIBUTE_TAG_V1_REPORT.md`. Does not ship as currently designed; would need a different signal to revisit.

**Verified gaps**: Saturated/Distorted/Clean (needs harmonic-distortion/THD analysis, doesn't exist anywhere in the codebase); Low-end Heavy (the taxonomy-only `lowEnergyRatio` field exists but is not wired into `generatePredictedTags()`). The required redundancy audit is now recorded in `tools/classification_benchmark/receipts/low_end_heavy_redundancy_audit_1850_20260914.json`: the candidate flag covers 38.3% of the corpus and overlaps the Dark band for only 46.7% of flagged rows, with heterogeneous class concentration. That is useful physical evidence, not an attribute ground truth, so the producer tag remains unshipped pending explicit owner labels.

**Recommendation**: Saturated/Distorted/Clean is the largest remaining attribute gap and, unlike everything shipped so far, needs genuinely new DSP research (THD estimation), not a bridging job — scope it as its own dedicated effort, not a quick add. Low-end Heavy is cheaper (bridging an existing field) but should get the redundancy check first.

## Confidence

**Spec asks for:** confidence + uncertainty_reason if low, surfaced per result.

**Shipped**: `tagConfidence` (0-1 float, signal-agreement based), a single "NEEDS REVIEW" UI threshold (`PluginEditor.cpp`), `BassTimbreClassifier`/`HiHatTypeClassifier` each carry their own `confidence` field following the same pattern.

**Verified gap**: no persistent `uncertainty_reason` field exists in the
cache — the UI now derives a presentation-only reason (OOD, weak agreement,
filename-only or mixed evidence) from existing provenance, so it can explain
*why* without adding a second mutable label column. A structured persisted
reason remains a future schema decision.

**Recommendation**: banding the existing float into high/medium/low is cheap (a UI-layer mapping, no new data needed) and directly serves this spec's ask — **recommended as the smallest safe implementation in this pass**. A real `uncertainty_reason` field is more valuable but requires threading a reason string through from wherever a result becomes low-confidence (OOD gate, DSP fallback, close margin) — more code paths to touch, scoped as a near-term follow-up rather than done in this same pass.

## `taxonomy_version` / `classifier_version`

**Shipped**: `taxonomyVersion`, `featureVersion`, `embeddingModelVersion` all exist on `SampleItem` and are already used to gate cache invalidation and distinguish "never classified" from "classified but Unknown" in the UI. This part of the spec is already fully met — confirmed directly in `SampleManagerEngine.h`.

## Never force a label

**Shipped and already a first-class design principle**, not something added for this spec: `AbletonTaxonomy.h`'s own header comment states this explicitly, predating this session. The OOD gate (`AcousticClassifier`) exists specifically to allow "Unknown" as a real outcome rather than forcing every embedding into one of the known classes. This session's own investigation (Stage 2/3 OOD work, both reverted) treated "don't ship a change that makes the system more likely to confidently guess wrong" as a hard constraint throughout, consistent with this principle.

## What's actually implemented in this pass

Given the scale of the full gap list and that most of it requires the same multi-hour, real-corpus-evidence-gated process as the already-shipped classifiers (not something to rush inside a single audit pass), the one item implemented as part of this program is **confidence banding** (high/medium/low, mapped from the existing `tagConfidence` float) — cheap, safe, no new data collection, directly serves the spec, and is a UI/presentation-layer change with no risk to the underlying classification logic. See the Fix Implementation section of `SLO_WORKING_PROPERLY_TEST_REPORT_V1.md` for what was actually built and tested. Everything else in this doc is a scoped, evidence-based plan for future work, explicitly not attempted in this pass to avoid shipping guessed labels under time pressure — which would violate the taxonomy's own core design principle.
