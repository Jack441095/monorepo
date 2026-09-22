# KENN Live 12 Investor Demo Set

`KENN_Live12_Demo.als` is the checked-in Ableton Live 12 topology fixture for
the investor demo. Open this file before running `tooling/scripts/demo_preflight.py`.

## Required topology

The set mirrors `tooling/demo_session_fixture.json`:

1. Kick
2. Snare / Clap
3. Hi-Hats
4. Drum Bus — Compressor
5. Bass — EQ Eight
6. Synth
7. Lead Vocal — Compressor
8. FX Print

Return `A-Reverb` includes Hybrid Reverb. The stock Reverb that precedes it is
intentional and does not weaken the required-device check.

## Scope and rehearsal

This file proves a loadable, deterministic Live topology; it does not contain
licensed or synthetic audio and must not be presented as evidence of audible
mix quality. Use only original or royalty-free material for audio-analysis
segments, and base every finding on the rendered or uploaded audio.

Treat the checked-in set as the reset point. Work in a copy during rehearsal,
then reopen this fixture before the next run. Run the preflight without
`--allow-mutations` first; use that flag only when a disposable rehearsal copy
is open and the exact undo probe is intended.
