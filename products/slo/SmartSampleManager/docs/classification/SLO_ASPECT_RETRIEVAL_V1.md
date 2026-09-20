# SLO Aspect Retrieval V1

## Purpose

SLO now exposes a decision-neutral similarity layer that can rank samples by
independent audio aspects instead of treating one embedding distance as the
whole answer. This follows the useful interaction pattern established by
Sononym (overall, spectrum, timbre, pitch, and amplitude controls), while
remaining compatible with Soundly-style metadata and text search.

## Contract

`SloAudioSimilarity::score()` returns:

- embedding similarity;
- spectrum similarity (centroid, rolloff, zero-crossing rate);
- timbre similarity (centroid, zero-crossing rate, stereo correlation, crest);
- pitch similarity (when explicit pitch/tempo evidence exists; otherwise neutral);
- amplitude similarity (duration, decay, crest, RMS);
- a weighted overall score.

Missing measurements are neutral (`0.5`), not a fabricated mismatch. Negative
weights are clamped to zero, and a zero total weight produces an overall score
of zero. The layer has no taxonomy, confidence, rename, or filesystem side
effects.

`SampleManagerEngine::findSimilarByAspects()` over-fetches the existing HNSW
candidate pool, recomputes the evidence record when needed, scores each
candidate, and sorts deterministically by overall score then path. It is
retrieval-only: the existing auto-rename policy is unchanged.

The in-app Find Similar overlay now renders all six ratings per result and
provides independent non-negative weights for embedding, spectrum, timbre,
pitch, and amplitude. The selected query path is pinned while the user tunes
weights, so clicking a result does not silently change the search reference.

## Evidence mapping

The shadow evidence record now carries the physical measurements already
computed by the production analysis path: duration, centroid, rolloff, ZCR,
crest, RMS, onset count, decay time, energy-decay ratio, stereo correlation,
and BPM when available. These are versioned by their existing DSP source tags;
no cache schema or persisted classification decision was changed.

## Verification

- `TestAudioSimilarity` passes.
- `TestAudioEvidence` passes.
- `ClassificationBenchmark` builds successfully.
- Focused Python tests: 10 passed for the schema, manifest, aspect scorer,
  and aspect search demo.

## Next product step

Wire these results into a read-only similarity panel with per-aspect sliders
and ratings. Add synonym/metadata filters and a correction event containing
`not_in_list`, `not_enough_info`, and `taxonomy_gap`. Only after those surfaces
are useful should their events be used to propose new labels or recalibrate
rename gates.
