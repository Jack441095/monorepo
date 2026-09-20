# Local sample WAVs

WAV sample packs are **not committed** to git (see `.gitignore`: `samples/`). You need them on disk for realtime playback, DSP gates, and benchmarks that render audio.

## Layout

Paths are relative to the repo root and match `data/sample_packs.py`:

```text
samples/
  default/
    bass.wav
    chords.wav
    melody.wav
    arp.wav
    drone.wav
  dark/
    ...
  eurphoric/
    ...
```

Pack names (`default`, `dark`, `ambient`, …) map to these folders. Packs without explicit `file_path` entries still expect `samples/<pack>/<sampler>.wav` after you scaffold a pack:

```bash
python3 main.py --scaffold-sample-pack my_pack
```

## Getting started without your Mac library

1. Copy your existing `samples/` tree into the repo root, **or**
2. Place minimal placeholder WAVs under `samples/default/` (any short mono/stereo files; root MIDI in `sample_packs.py` must match your material).

Composition-only workflows (offline render, `tools/song_quality_audit.py`) do **not** require WAVs.

## Benchmarks and CI

| Workflow | Needs `samples/`? |
|----------|-------------------|
| `tools/song_quality_audit.py` | No (symbolic generation + scoring) |
| `pytest -m "not slow"` | Usually no |
| `scripts/run_system_performance_benchmark.sh` | Yes for realtime/DSP gates |
| `scripts/run_rt_performance_gate.sh` | Yes |

Cloud agents and fresh clones often show `Sample not found` during RT benchmarks; that is expected until you add local WAVs.

## Related docs

- [docs/COMMANDS.md](COMMANDS.md) — CLI and audit commands
- [artifacts/quality_audits/README.md](../artifacts/quality_audits/README.md) — song quality audit output
