# stem_separation

AI stem separation (Demucs v4) — isolates drums, bass, vocals, and other
(synths/guitars/etc.) from a mixed stereo track.

Isolated in its own venv, same reasoning as `studio/audiogen`: this repo's
shared environment deliberately excludes `torch` (the last Intel-macOS wheel
is ABI-incompatible with NumPy 2.x — see the root `requirements.txt`), and
Demucs is torch-only. Keeping it here means the shared install stays
torch-free while this one tool gets a real, current torch.

## Setup

```bash
./scripts/setup_venv.sh
```

The first real separation run downloads the `htdemucs` pretrained model
(~80MB) into torch's model cache.

## Usage

```bash
.venv/bin/python main_separate.py --input mixdown.wav --output-dir out/
```

Prints progress to stdout, then exactly one JSON line as its result:
`{"ok": true, "stems": {"drums": "...", "bass": "...", "vocals": "...", "other": "..."}, ...}`.

Called from the main app via `business/app/stem_separation_bridge.py`, which
never imports this package directly — always through a subprocess, so the
shared app process never needs torch on its own import path.

## Tests

```bash
.venv/bin/python -m pytest
```

Most tests are pure argument-parsing/contract checks that don't need a real
model. Tests marked `slow` run actual Demucs inference and are skipped by
default.
