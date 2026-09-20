# SLO real-world sound taxonomy scaffold V1

Date: 2026-09-11

This is a **dormant design artifact**, not a production taxonomy change. It
defines how SLO could later recognise animals, people, environmental sounds,
machines, and materials without forcing those sounds into music-sample classes.

The machine-readable contract is
`SmartSampleManager/tools/classification_benchmark/real_world_taxonomy_v1.json`.
The readiness audit is read-only and cannot create labels, scan audio, alter the
production classifier, or apply renames.

## Design

Use separate axes rather than one ever-growing flat class list:

1. domain — animal, human, environment, mechanical, or material;
2. source — bird, mammal, vehicle, water, metal, and so on;
3. event — bark, chirp, engine start, splash, impact, etc.;
4. form — one-shot, loop, ambience, sustained, or mixture;
5. acoustic attributes — tonal/noisy, pitched/unpitched, transient/sustained,
   dry/processed, and confidence.

Species-level names are intentionally conservative. If the recording supports
only “bird”, the system must return `animal_unknown` rather than guessing a
species. Multiple sources or genuinely ambiguous recordings remain rejection
outcomes.

## Activation gate

Nothing in this scaffold is eligible for auto-renaming. Activation requires
human-by-ear labels from multiple collections, collection-held-out evaluation,
95% precision for any auto-action class, and explicit owner approval to keep the
new domain separate from the music-sample taxonomy.

## Reference vocabularies

AudioSet is a useful broad hierarchical reference, FSD50K is a more manageable
open sound-event vocabulary, and ESC-50 is a compact environmental benchmark.
They are references for naming and hierarchy only; no external dataset has been
downloaded or merged into SLO by this scaffold.

## Current result

The companion audit runs against existing prediction receipts only. It records
future or unmapped candidate labels separately from current production labels,
so taxonomy exploration cannot silently change classification or rename policy.
