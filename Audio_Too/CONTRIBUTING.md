# Contributing to Audio_Too

This repo is a private business workspace. All contributions are reviewed
by Jack Knowlton Gandy.

## Quick start (also try `make help`)

```bash
git clone https://github.com/Jack441095/Audio_Too.git
cd Audio_Too
python3 main.py setup      # create .venv, install deps, symlink pre-commit hook
source .venv/bin/activate
cp .env.example .env    # set AUDIO_TOO_DASHBOARD_PASSWORD (or python3 main.py start)
python3 main.py start       # launch the dashboard
```

## Stay in sync

Since multiple people contribute:

```bash
git pull          # get latest changes before working
# ... make your changes ...
git add -A
git commit -m "description of your changes"
git push          # share your changes with everyone
```

The pre-commit hook will run hygiene checks before each commit. If it blocks you, run `python3 main.py check` to see what's wrong.

## Before you commit

The repo has a pre-commit hook that runs a hygiene check before every commit:

- **Blocked patterns**: `__pycache__/`, `tmp_pytest/`, `studio/kenn/kenn/artifacts/training/`,
  `studio/kenn/kenn/data/index/`, etc.
- **Large files**: Tracked files over 10 MB are flagged (except portfolio WAVs).
- **Generated artifacts**: Scan outputs, benchmarks, and training JSON are not committed.

If the hook blocks your commit:

```bash
python3 main.py check       # see what's wrong
python3 main.py check --fix # auto-remove any blocked tracked files
```

The hook is installed automatically by `python3 main.py setup`. To install it manually:

```bash
ln -sf ../../.git-hooks/pre-commit .git/hooks/pre-commit
```

## Code standards

- **Python**: Ruff linting (configured in `pyproject.toml`).
- **JavaScript/HTML/CSS**: Inline in `business/app/static/`.
- **Markdown notes**: KENN training notes live in `studio/kenn/kenn/Training_Data_Notes/`.

Run the linter:

```bash
python3 main.py lint
```

Run tests:

```bash
python3 main.py test
```

## What goes in git

**Track these:**
- Python, JS, HTML, CSS, shell scripts
- Curated markdown training notes
- Tests and documentation
- Small JSON seed data (`business/agents/Shared/data/seed/`)
- `business/portfolio/audio/README.md` (directory sentinel stays in git)
- `studio/kenn/kenn/Training_Data_PDF/audio-too-workflow-checklist.pdf`

**Do not track:**
- `business/portfolio/audio/*.wav` (regenerable via AudioGen)
- `studio/kenn/kenn/data/index/chunks.jsonl` or `terms.json`
- `studio/kenn/kenn/artifacts/benchmarks/`, `studio/kenn/kenn/artifacts/audits/` (regenerable)
- `studio/kenn/kenn/artifacts/training/*.json` or `*.jsonl` (exported from KENN)
- `artifacts/` — one-off analysis scan outputs
- `tmp_pytest/` — test fixture artifacts
- Downloaded PDFs
- `.env`, `.venv/`, `__pycache__/`
- Mix Review uploads/reports (`studio/agents/MixReview/data/mix_reviews/`)
- studio/audiogen/audiogen runtime files

## Questions

Ask in Slack or open an issue.
