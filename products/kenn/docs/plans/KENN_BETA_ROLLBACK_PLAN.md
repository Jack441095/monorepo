# KENN Beta Rollback Plan

## Why rollback is low-risk here

This sprint's changes are entirely code, documentation, and a small,
selectively-approved knowledge-content import on a dedicated branch
(`develop`, created as `beta-audit-2026-09-01` from a clean `main` with no
uncommitted changes at the start of this audit, renamed once its fixes
were verified). Both beta surfaces (Mix Review, Chat) are read-only by
construction -- there is no persisted runtime state, database, or written
audio anywhere in the beta workflow to also roll back beyond the knowledge
index itself, which is regenerable (see below).

## Rollback procedure

### If a specific commit needs reverting

```sh
git log --oneline main..develop   # see what's on the branch
git revert <commit-sha>            # revert one commit, keeps history
```

Each commit on this branch is scoped to one coherent change (see `git log`
messages), so a single problematic change can be reverted without pulling
in unrelated ones.

### If the whole branch needs to be abandoned before merge

Since nothing has been merged to `main` yet, simply do not merge the
branch. `main` is untouched. No further action needed.

### If the branch has already been merged to `main` and needs rolling back

```sh
git revert -m 1 <merge-commit-sha>   # for a merge commit
# or, for a fast-forward merge with no merge commit:
git revert <first-branch-commit-sha>^..<last-branch-commit-sha>
```

Do not use `git reset --hard` on a shared branch. If `main` has already
been pushed anywhere and pulled by others, a force-push to "undo" history
is a much higher-risk operation than a revert commit -- use revert.

### Runtime rollback (environment/config only, no data)

- Mix Review: unset `KENN_MIX_REVIEW_ENGINE` and `KENN_AUDIO_TOO_ROOT` to
  guarantee the default (KENN-owned) engine is used. There is no other
  runtime state to reset -- `KENN_MIX_REVIEW_RUNTIME_DIR` only ever holds
  a temp-directory marker, never audio or results.
- Chat: unset `KENN_ENGINE_ROOT` to return to the default (this repo's own
  `source/` tree). `AUDIO_TOO_LLM_ENABLED` is force-set to `"0"` in code
  before any KENN module import regardless of environment, so there is no
  way to accidentally leave LLM use enabled by a stale environment
  variable.
- No database migrations, schema changes, or persistent stores were
  introduced by this sprint. There is nothing to migrate back.

### Rolling back the imported knowledge content specifically

The knowledge notes/sources/evals under `apps/backend/src/kenn/Training_Data_Notes/`,
`Training_Data_Sources/`, `Training_Data_PDF/`, and `evals/` were added in
one dedicated commit (see `git log`) and can be reverted independently of
everything else:
```sh
git revert <that-commit-sha>
```
The built index (`apps/backend/src/kenn/data/index/`) is gitignored and regenerated,
not committed -- deleting that directory and not re-running
`python3 apps/backend/src/kenn/main.py build` is enough to remove the knowledge
base's effect without touching git history at all, if that's all that's
needed.

### Rolling back the `server.py` fix specifically

`apps/backend/src/kenn/server.py`, `core/tool_registry.py`, and the six ported
modules under `core/` (`platform_contracts.py`, `endpoint_policy.py`,
`request_validation.py`, `action_policy.py`, `path_safety.py`,
`confirmation.py`) plus `scripts/log_setup.py` were added in one dedicated
commit and can be reverted independently:
```sh
git revert <that-commit-sha>
```
Reverting returns `server.py` to its pre-sprint state: blocked at import,
same as before this sprint. No runtime state or data is affected --
`server.py` writes only within `.runtime`-style directories already
covered by `.gitignore`.

## What is explicitly NOT part of this rollback surface

AutoMix, `tool_registry.py`'s ~10 remaining unimplemented specialist
routes (Ableton hardware bridge, stem separation, voice synthesis), the
desktop companion, and the VST3 plugin were not made newly functional by
this sprint (see the gap matrix) -- there is nothing new to roll back for
those beyond the documentation describing their status, and reverting
this branch does not change their already-blocked state.

## Verification after any rollback

```sh
python3 -m pytest mix-review/tests automix/tests chat/tests apps/backend/src/kenn/tests -q
```

Before this sprint: `mix-review/tests` and `chat/tests` both failed to
*collect* at all (import-time `RuntimeError`, 0 runnable tests in either),
and `apps/backend/src/kenn/tests` didn't exist. After this sprint: 89/89 passing
(24 mix-review, 4 automix, 39 chat, 22 apps/backend/src/kenn) -- verified by direct
run as of the final commit; re-run to confirm current numbers, as new
tests may be added after this document is written. If a rollback returns
the suite to a smaller passing count, or to the pre-sprint collection
failures, that is expected for a partial revert and is not itself a new
bug -- check which commit was reverted against the numbers recorded in
`docs/KENN_BETA_READINESS_REPORT.md` Section 7.
