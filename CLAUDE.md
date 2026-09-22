# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

The canonical NITE DSP engineering estate. **Everything is tracked directly in this single repository** — there are no git submodules on `main` (no `.gitmodules`, no gitlinks; the `submodule.*` entries in `.git/config` are vestigial from the Sept 2026 consolidation). The machine-readable current-state file is `docs/NITE_DSP_STATE.json`; the operating-decision document is `docs/NITE_DSP_FOUNDER_MASTER_PLAN.md`.

Directory map: `products/kenn` (KENN), `products/slo` (SmartSampleManager), `products/nite-submit`, `products/kenn-evaluation`, `backend/`, `website/`, `shared/`, `Audio_Too/` (preserved legacy), `audio-technology/`, `autonomous-systems/`, `validation/`.

**KENN lives here.** `products/kenn/` is the KENN source of truth, tracked directly in this monorepo (backend under `products/kenn/apps/backend`, tooling, plugins, docs). The former standalone repo (`Shenrendao/KENN`) was absorbed during the Sept 2026 consolidation; a frozen pre-monorepo snapshot is kept outside git under the local `Products/Kenn/archive/` data home.

## Working rules specific to this repo

- **Never add an AI attribution trailer to commits in this repo.** Commits here must not contain `Co-Authored-By: Claude ...` or similar (the `commit-metadata.yml` gate exists on the `kenn-production-hardening` branch; its script `tools/check_commit_metadata.py` is not currently present on `main` — re-add before re-enabling CI enforcement). This overrides the default Claude Code commit-attribution behavior — do not append `Co-Authored-By: Claude ...` when committing here.
- New worktrees go under `workspace/worktrees/<project>/<task>/`; builds/caches go under `workspace/` or already-ignored project-local dirs.
- `Audio_Too` is a preserved legacy boundary that was *not* bulk-migrated during the Sept 2026 cleanup — it overlaps heavily with `products/slo` (both descend from the SLO codebase) but is kept as a frozen reference; don't assume they mirror each other.
- Owner audio and corpora are data, not source — kept outside this code estate entirely.

## Commands

The root `tools/` helper suite referenced by earlier versions of this file (`estate_check.sh`, `run_all_product_checks.sh`, `check_commit_metadata.py`, …) is **not currently present on `main`** — its only copies live on the `kenn-production-hardening` branch. Restore before relying on those commands.

Product-level verification that does run today:

```bash
cd products/kenn && PYTHONPATH="apps/backend/src:tooling" python3 -m pytest -q apps/backend/src/kenn/tests
```

There's no root-level build/test/lint config — each product (`products/kenn`, `backend/`, `website/`, and the submodules) has its own toolchain; `cd` into the relevant tree and check its own README/CLAUDE.md rather than expecting root-level commands to reach into it.

## CI

`.github/workflows/`: `backend.yml`, `website.yml`, `kenn-core.yml`, `kenn-dsp-native.yml`, `kenn-integration.yml`, `smart-sample-manager.yml`, `nite-submit-ci.yml`, `audio-too-ci.yml`, and `mirror-to-personal.yml` (mirrors every push to `main` from `Nite-DSP/monorepo` to the personal `Jack441095/monorepo`, which is what Vercel actually deploys from — see `REPO_NOTES.md` for the deploy chain).
