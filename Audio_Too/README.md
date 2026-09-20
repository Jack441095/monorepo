# NITE DSP — Product Workspace

Server, studio tools, AI assistants, and website for NITE DSP.

## Structure

- `thursday/` — Thursday AI orchestrator: voice assistant, event bus, DAW watcher, self-healing diagnostics
- `studio/kenn/` — KENN Ableton/studio assistant
- `studio/audio_analysis/` — AutoMix, mix review, podcast analysis
- `studio/audiogen/` — Generative music engine (chorus loops, full-song renders)
- `server/app/` — Web server: public site, control panel, backend API
- `server/agents/` — Admin and Marketing agents
- `nitedsp/` — nitedsp.co.uk Next.js website
- `core/` — Shared boundary contracts and platform primitives
- `docs/` — Architecture, policies, and specs

## Getting started

```bash
python main.py setup
source .venv/bin/activate
cp .env.example .env
python main.py start
```

Opens the server at `http://127.0.0.1:8080` and Ableton chat at `8090`.

## Common commands

```bash
python main.py start          # start server + Ableton chat
python main.py lint           # ruff lint
python main.py test           # test suite
python main.py check          # full local gate (Apple Silicon only)
python main.py agent dashboard
python main.py kenn-ready
```

## Data

Live records in `data/audio_too.db`. Not in git — created on first run.
Backups via `python main.py agent backup`.

## CI

GitHub Actions runs lint + hygiene + ~1,330 tests on every push to `main`.
Full coverage (AudioGen DSP, KENN-LM, TTS) requires Apple Silicon — run `python main.py check` locally before releasing.
See `docs/CI.md`.
