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

The Bass EQ has more than one band near 200 Hz. The investor-demo command must
name the verified active band explicitly: `Boost amplitude by 3 dB at 200 Hz
on track 5 band 2A.` See `docs/runbooks/KENN_INVESTOR_DEMO.md` for the canonical
script.

## Original demo audio

The tracked `.als` remains a small, deterministic topology reset point. Build
the matching original composition locally (WAVs are intentionally git-ignored):

```sh
python3 tooling/scripts/build_investor_demo_audio.py \
  --out-dir .runtime/investor-demo-audio
```

The generator renders eight 32-second stems in the exact track order above,
a full-mix analysis render, an isolated vocal analysis render, and a manifest
with SHA-256 hashes and a fail-closed rights statement. It uses no samples,
external recordings, model weights, or third-party composition. Import the
eight stems into a disposable copy of the Live fixture; never overwrite the
tracked reset point.

Start KENN with the manifest-bound analysis paths printed in
`.runtime/investor-demo-audio/manifest.json`:

```sh
export KENN_LIVE_AUDIO_CAPTURE_PATH="$PWD/.runtime/investor-demo-audio/KENN_Demo_Mix_Analysis.wav"
export KENN_LIVE_VOCAL_CAPTURE_PATH="$PWD/.runtime/investor-demo-audio/KENN_Demo_Lead_Vocal_Analysis.wav"
```

The mix contains documented low-end-heavy and near-clipping cues for the
advisory demo. KENN still describes them as measured hypotheses, not a quality
score or automatic EQ instruction.

## Scope and rehearsal

The reset file alone proves topology, not audible mix quality. Audio claims are
valid only when preflight verifies the generated manifest and hashes and the
matching stems are present in the disposable rehearsal set.

Treat the checked-in set as the reset point. Work in a copy during rehearsal,
then reopen this fixture before the next run. Run the preflight without
`--allow-mutations` first; use that flag only when a disposable rehearsal copy
is open and the exact undo probe is intended.
