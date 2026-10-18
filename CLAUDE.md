# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

The canonical NITE DSP engineering estate. **Everything is tracked directly in this single repository** — there are no git submodules on `main` (no `.gitmodules`, no gitlinks; the `submodule.*` entries in `.git/config` are vestigial from the Sept 2026 consolidation). The machine-readable current-state file is `docs/NITE_DSP_STATE.json`; the operating-decision document is `docs/NITE_DSP_FOUNDER_MASTER_PLAN.md`.

Directory map: `products/kenn` (KENN), `products/slo` (SmartSampleManager), `products/nite-submit`, `backend/`, `website/`, `shared/`, `audio-technology/`, `autonomous-systems/`, `validation/`.

**KENN lives here.** `products/kenn/` is the KENN source of truth, tracked directly in this monorepo (backend under `products/kenn/apps/backend`, tooling, plugins, docs). The former standalone repo (`Shenrendao/KENN`) was absorbed during the Sept 2026 consolidation; a frozen pre-monorepo snapshot is kept outside git under the local `Products/Kenn/archive/` data home.

## Working rules specific to this repo

- **Never add an AI attribution trailer to commits in this repo.** Commits here must not contain `Co-Authored-By: Claude ...` or similar (the `commit-metadata.yml` gate exists on the `kenn-production-hardening` branch; its script `tools/check_commit_metadata.py` is not currently present on `main` — re-add before re-enabling CI enforcement). This overrides the default Claude Code commit-attribution behavior — do not append `Co-Authored-By: Claude ...` when committing here.
- **Commit as Jack441095.** Author and committer are `Jack441095 <jack.gandy@gmail.com>`, the owner's GitHub account, never `Claude <noreply@anthropic.com>`. Cloud sessions start with the Claude identity configured, so set it first: `git config user.name "Jack441095" && git config user.email "jack.gandy@gmail.com"`.
- New worktrees go under `workspace/worktrees/<project>/<task>/`; builds/caches go under `workspace/` or already-ignored project-local dirs.
- `Audio_Too/` (the legacy platform that `products/slo` and Thursday grew out of) was removed on 18 Oct 2026. Its last state is the tag `archive/audio-too-final`; check that out in a worktree if you need to read it.
- Owner audio and corpora are data, not source — kept outside this code estate entirely.
- **Agent skills**: Matt Pocock's engineering skills are vendored in `.claude/skills` (Claude Code, opencode) and `.agents/skills` (Codex, opencode) — same files in both, see the README beside them. Reach for them to grill a plan, run a diagnosis loop, do TDD, or review a diff on standards and spec. They must not spawn competing plans or tickets: `products/kenn/KENN_PLAN.md` stays the single roadmap.

## Code and comment style

Code should read like a careful human engineer on this team wrote it, not like generated output. One test: would you
be willing to have your name on the diff?

- **Comment generously, and comment the decision.** A comment earns its line when it answers a question the code
  alone raises — why this approach and not the obvious one, what breaks if this number or ordering changes, where
  the value came from (the measurement, the standard, the date, the machine), what was tried and rejected, or what
  this code deliberately does not do.
- **Density target.** A reader who knows Python should never have to stop and ask "why?" more than once inside a
  single function. Comment the seams, not every line.

  ```python
  # Before: correct, and a reader cannot tell why either constant is what it is.
  peaks_db = min(peaks_db, -1.0)
  gain = round(10.0 ** (delta_db / 20.0), 4)

  # After: both constants now carry the constraint that produced them.
  # -1 dBTP is the ceiling: a summed master above it clips in the lossy encode we
  # hand to streaming, and we would rather give up 0.1 dB of peak than ship a
  # master that distorts on someone else's phone speaker.
  peaks_db = min(peaks_db, -1.0)

  # Four decimals, because Live quantises the raw fader to 1e-4, so a finer gain
  # silently rounds on write-back and the next read disagrees with what we measured.
  gain = round(10.0 ** (delta_db / 20.0), 4)
  ```

- **Comment like a person, not a generator.** First person plural is natural ("we read the mixer here because…"),
  dates and what bit us are welcome, and they should sound like the rest of the file's comments.
- **Comments explain why, not what.** Write them the way you'd explain it to a colleague: the reason, the gotcha, the
  thing that bit us ("Live ignores this while the device view is hidden, so select the track first"). A comment that
  only restates its own line gets deleted.
- **Every fallback branch gets a line.** On each `except`, each early `return None`, each degraded path: what happens
  there, and why returning is safe.
- **Every literal gets a unit.** `-1.0` becomes `-1.0 dBTP`, `2048` becomes `2048 samples (46 ms at 44.1 kHz)`, `0.16`
  becomes `0.16 cosine overlap threshold`.
- **Docstrings state the contract.** One line on what it returns or changes, plus any surprising side effect or
  caller obligation. Expand only when the reasoning genuinely needs the room.
- **Match the file you're in.** Naming, docstring format and idioms follow the surrounding code; don't introduce a
  new style into an old file. Match its comment *register* — terse measured notes or chatty explanation — while
  keeping the density target above. A new module or subsystem gets the fuller treatment even if its neighbours are
  bare.
- **Plain, specific English.** Short sentences, real names and numbers. Avoid filler and hype words ("robust",
  "comprehensive", "seamlessly", "leverage", "ensure that", "it's important to note"), and don't open with "This
  function…" or "Note:".
- **No boilerplate.** No banner or divider comments (`# ---- Helpers ----`), no Args/Returns blocks that just repeat
  the signature, no emoji. Plenty of comments still means every comment is load-bearing.
- **Don't over-engineer.** No defensive checks for things that can't happen, no wrapper layers or config options
  nobody asked for. Handle the errors that really occur.
- **Before you report done,** reread your own diff as if you inherit it in six months with no memory of the ticket.
  Every branch, constant and fallback carries a why, or the commenting is not finished.
- **Tests read like examples.** Name them for the behaviour they protect (`test_a_frequency_never_becomes_a_fader_change`);
  a regression test says in one line what broke and when.
- **Commit messages:** one plain line saying what changed and why it matters, like a person would write it. Never
  mention AI or tools (see the attribution rule above).

## Commands

The root `tools/` helper suite referenced by earlier versions of this file (`estate_check.sh`, `run_all_product_checks.sh`, `check_commit_metadata.py`, …) is **not currently present on `main`** — its only copies live on the `kenn-production-hardening` branch. Restore before relying on those commands.

Product-level verification that does run today:

```bash
cd products/kenn && PYTHONPATH="apps/backend/src:tooling" python3 -m pytest -q apps/backend/src/kenn/tests
```

There's no root-level build/test/lint config — each product (`products/kenn`, `backend/`, `website/`, and the submodules) has its own toolchain; `cd` into the relevant tree and check its own README/CLAUDE.md rather than expecting root-level commands to reach into it.

## CI

`.github/workflows/`: `backend.yml`, `website.yml`, `kenn-core.yml`, `kenn-dsp-native.yml`, `kenn-integration.yml`, `smart-sample-manager.yml`, `nite-submit-ci.yml`, `kenn-app-sync.yml`, `kenn-weekly.yml`, and `mirror-to-personal.yml` (mirrors every push to `main` from `Nite-DSP/monorepo` to the personal `Jack441095/monorepo`, which is what Vercel actually deploys from — see `docs/process/REPO_NOTES.md` for the deploy chain).
