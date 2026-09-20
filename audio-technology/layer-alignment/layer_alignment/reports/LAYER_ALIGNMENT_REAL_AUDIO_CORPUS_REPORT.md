# LAYER ALIGNMENT REAL AUDIO CORPUS REPORT (V1 — AUTHORISED IMPORT)
### Sources: Audio_Too/sample_pack_testing + Audio_Too/testing_track_stems (owner-authorised, READ-ONLY)

## Provenance & safety

- Authorisation receipts: `real_audio_import/LICENCE_sample_pack_testing.json`,
  `LICENCE_testing_track_stems.json` — local internal R&D validation only;
  modification/redistribution/commit/push/upload forbidden.
- Originals referenced in place by sha256; **zero audio committed**.
  Derived fixtures under `results/real_v1/derived/` (gitignored).
- `_automix_out` excluded: derived output of another sprint, not source.
- Rate-mismatched pairs: B resampled (derived copy, flagged
  `processing.resampled_b`).

## Selection methodology

Filename keywords shortlist → audio-evidence verification (duration,
spectral centroid, low-frequency energy fraction, onset density) recorded
per used file in `results/real_v1/used_sources.json` → rejection only on
strong contradiction. Diversity guard: ≤3-5 sources per pack group.

## Built corpus (387 cases)

| class | n | construction |
|---|---|---|
| CONTROLLED | 102 | verified one-shots × exact perturbations (int ±delay, fractional, polarity, min-phase filter, tanh distortion; rotated grid, 2 variants/source) |
| HEALTHY | 176 | identity copies (6 sessions), cross-pack same-domain decorrelated pairs (kick 20 / hat 14 / snare 8 / clap 6 / perc 14 slots), LR4 crossover recombinations (dispersive), different-envelope pairs, tonal loop ambiguity pairs, unrelated cross-domain complements |
| NATURAL | 109 | curated intra-session production relationships across 8 multitrack sessions + systematic role-pair fallback sweep |

Natural relationship coverage includes kick+sub (atlantisbound KickSub),
layered kicks (angeloboltini Drumkit1_Kick vs Kick), snare top/bottom
(atlantisbound, amyhelmand Kick In/Out, Snare Top/Bottom multimic),
snare+claps, hat layers/shakers, kick+bass, drum-bus relationships, synth
stacks (arp/pad), and room-mic relationships.

## Source diversity

Controlled sources span ≥15 distinct packs; healthy cross-pack pairs span
≥12 packs; naturals span all 8 sessions. Per-group caps enforced during
selection. Full hash inventory: `used_sources.json`.

## Known corpus limitations (disclosed)

- Natural ground truth is NOT known a priori (per brief): correctness of the
  107 NO_ACTIONs requires the blind review / owner judgement.
- Resampled-B fixtures carry linear-interpolator artefacts (analysis-grade
  caveat recorded).
- Vocal domain thin (few one-shot vocal sources passed duration checks).
