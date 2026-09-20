# LLM AudioGen — Markov fine-tune

Generative song composition with **Markov melody models**, harmony/section planning, realtime playback, and offline training/audit pipelines.

## Quick start

Use **Python 3.12** locally (matches CI; see `.python-version`).

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python3 main.py
```

Offline full song (Phase C profile is default):

```bash
.venv/bin/python main_render_full_song.py --emotion grief --k 3
```

One-shot LLM chorus loop (random seed, JSON stdout, optional WAV):

```bash
.venv/bin/python main_llm.py --emotion joy --no-play --wav-out /tmp/joy_chorus.wav
```

See [llm_commands.md](llm_commands.md) for integration details.

## Documentation

| Doc | Contents |
|-----|----------|
| [docs/COMMANDS.md](docs/COMMANDS.md) | CLI, offline export, training commands |
| [llm_commands.md](llm_commands.md) | `main_llm.py` integration + `main_llm_chorus_only.py` |
| [docs/SAMPLES.md](docs/SAMPLES.md) | Local WAV packs (not in git), benchmark notes |
| [docs/SONG_UPGRADE.md](docs/SONG_UPGRADE.md) | Phases A–C+ roadmap and audit workflow |
| [docs/TRAINING_COMMANDS.md](docs/TRAINING_COMMANDS.md) | JSONL / Markov retrain pipelines |
| [docs/GIT_SETUP.md](docs/GIT_SETUP.md) | Remote, SSH, branch layout (`main` vs `wip/markov-audio-refactor`) |

## Branches

- **`main`** — song-upgrade phases, audits, tests (stable track)
- **`wip/markov-audio-refactor`** — large Markov/audio/composition refactor (not merged)

## Tests

```bash
# Fast subset (matches CI `test` job)
pytest -m "not slow"

# Realtime / audio-heavy tests (each runs in a fresh subprocess)
pytest -m slow

# Disable subprocess isolation for debugging a single RT test
AUDIOGEN_TEST_NO_ISOLATE=1 pytest tests/test_player_runtime.py -q
```

On pushes to `main`, CI also runs `tests/test_song_upgrade_profile.py` and `tests/test_section_generation_snapshots.py`.

Full local runtime audit:

```bash
.venv/bin/python tools/rt_full_audit.py --output-dir .cache/rt_full_audit
```

Whole-system performance benchmark (offline + realtime):

```bash
scripts/run_system_performance_benchmark.sh

# or via pytest (slow / isolated)
pytest -m benchmark -q
```
