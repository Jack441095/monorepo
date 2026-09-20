# SLO universal attribute taxonomy — V1

## Decision

Use a factorised description for every sound. Do not make every combination a
new class. A result should be assembled from independent claims:

`domain + source/family + event/role + form + acoustic attributes + provenance`

The current flat class remains as a compatibility view while these claims are
learned and validated.

## Shared axes

| axis | examples | usually learned from |
|---|---|---|
| Domain | music, animal, human, environment, mechanical, material | human/teacher label |
| Source/family | kick, snare, piano, guitar, bird, engine, water | human label + name evidence |
| Event/role | hit, note, chord, phrase, call, rev, impact | human label + temporal evidence |
| Form | one-shot, loop, phrase, fill, sustained, ambience | periodicity/onsets + human label |
| Pitch | pitched, unpitched, ambiguous; register; estimated F0 | waveform measurement |
| Envelope | transient, decaying, sustained; attack/decay | waveform measurement |
| Spectrum | low/mid/high emphasis, tonal/noisy, harmonicity, brightness | waveform measurement |
| Rhythm | tempo, meter estimate, swing, onset density, periodicity | waveform measurement |
| Spatial | mono, stereo, width, phase correlation | waveform measurement |
| Processing | dry, reverberant, distorted, filtered, clipped | waveform measurement + review |
| Provenance | pack, collection, vendor, filename tokens | metadata |
| Certainty | confidence, alternatives, unknown, taxonomy gap | policy/review |

## Examples

### Drum loop

`domain=music`, `family=drum kit`, `event=groove`, `form=loop`,
`rhythm=periodic`, `attributes=multiple percussive roles`.

### Piano phrase

`domain=music`, `family=piano/keys`, `event=melodic phrase`, `form=phrase`,
`pitched=pitched`, `attributes=harmonic, transient notes`.

### Bird call

`domain=animal`, `family=bird`, `event=call`, `form=one-shot` or `phrase`,
`pitched=pitched/ambiguous`, `certainty=animal_family_supported`.

### Engine loop

`domain=mechanical`, `family=engine`, `event=running/rev`, `form=loop` or
`ambience`, `rhythm=periodic`, `attributes=low-frequency, harmonic/noisy`.

## What waveform data can and cannot do

Waveform analysis can provide strong, checkable attributes: attack, decay,
periodicity, pitch confidence, spectral balance, harmonicity, loudness,
clipping, stereo width, and onset density. It cannot reliably identify every
source on its own: a tom, kick, low synth, and processed impact can overlap in
those measurements. Source/family claims therefore remain separate semantic
heads backed by human labels, metadata, and retrieval evidence.

## Benefits for classification and renaming

- A new form such as `loop` can be learned once and reused across drums, bass,
  piano, animals, and machines.
- Search can ask for `pitched + sustained + bright` without requiring a class
  named “Bright Sustained Synth.”
- Explanations can show measurable evidence instead of only a class name.
- Unknown, not-in-list, not-enough-info, and taxonomy-gap remain explicit.
- Naming can be generated from approved claims while preserving the original
  file and provenance.

## Training and safety rule

Each semantic head still needs collection-held-out evaluation. Physical
attributes may be emitted as observed evidence before a source classifier is
qualified, but they must not silently become a semantic label or enable an
automatic rename. The current 600-file breadth batch is the next source of
labels for validating the family/form heads.
