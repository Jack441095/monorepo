# Git Notes — Nite-DSP Monorepo

How we use git here, as of 4 October 2026. `REPO_NOTES.md` has the deploy chain; this is the day-to-day side.

## Remotes

| Remote | Points at | Used for |
| --- | --- | --- |
| `origin` | `Nite-DSP/monorepo` | The monorepo. Every push to `main` is mirrored to the personal `Jack441095/monorepo` by `mirror-to-personal.yml`, and Vercel deploys from that one. |
| `kenn-app` | `Nite-DSP/kenn-app` | The shared KENN repo for the collaborator group. Only ever receives a subtree split of `products/kenn`. |

`Nite-DSP/kenn` is the old frozen pre-monorepo repo. Don't push to it.

## What a push to `main` does

It deploys. The website and backend go live through the mirror, including the Stripe checkout code. So `main` only gets pushed on purpose, after the payment commits have been looked at. A local merge into `main` is safe; the push is the step that matters.

## Branches

- `main`: the last pushed state. At the time of writing it is 100 commits behind the KENN working branch.
- `fix/review-critical-2026-10-02`: where KENN work has been landing. It carries about 250 files of changes, including the `website/` and `backend/` payment work, so it is not a KENN-only branch.
- `draft/answer-fits-128-tokens`: drafts not yet measured on the model (the routing fix for "educate me" requests, and the prompt rules for capped answers). Not merged anywhere.

## Worktrees

New worktrees live under `workspace/worktrees/<project>/<task>/`, for example `workspace/worktrees/kenn/answer-fits-128`. Don't use bare `git stash` in a worktree; the stash stack is shared with the main checkout and every other worktree. Use a throwaway WIP commit instead.

## Commits

- One plain line saying what changed and why it matters.
- Never an AI attribution trailer (`Co-Authored-By: Claude ...` or similar). This holds even if a tool's default says to add one.
- Show the diff before committing receipts and plan notes. Evidence receipts say plainly when a gate is still failed.

## Syncing KENN to kenn-app

`products/kenn` in the monorepo is what we edit; `kenn-app` main is kept identical to it. The steps:

1. `git fetch kenn-app main`.
2. `git subtree split --prefix=products/kenn main` gives a commit hash.
3. Check it descends from `kenn-app/main` with `git merge-base --is-ancestor kenn-app/main <hash>`. If it doesn't, stop.
4. Scan the new commits for secrets and AI trailers, and run `products/kenn/tooling/scripts/ci_verification.sh` on a fresh worktree. Compare by content, not just commit lists.
5. Fast-forward push: `git push kenn-app <hash>:refs/heads/main`. Never force. In zsh write `${hash}:refs/heads/main`, because `$hash:refs` is read as a modifier.
6. Verify: `git rev-parse kenn-app/main^{tree}` must equal `git rev-parse main:products/kenn`.

`kenn-app` main can't be branch-protected on the current GitHub plan, so "changes go through a PR" is a convention, written down in `products/kenn/docs/GETTING_STARTED.md`. If `kenn-app` main is ever damaged, the monorepo is the source of truth: re-push the subtree split.

Where it stands: `kenn-app` main was at `9b9ccc9c` (30 September) when last checked on 4 October, about 190 KENN commits and 428 files behind `main`.

## Mac quirks

- `gh` is broken on this Mac ("bad CPU type"). GitHub work goes through the browser, or plain `git` over SSH.
- `timeout` isn't installed, so `timeout 60 git fetch` fails. Run the fetch without it.
- Tests that need `Training_Data_Sources/` or the knowledge index skip on a fresh clone. Around 125 skips is normal.

## Tests

```bash
cd products/kenn && PYTHONPATH="apps/backend/src:tooling" python3 -m pytest -q apps/backend/src/kenn/tests
```

In a fresh worktree four tests in `test_streamed_generation_prefix_guard.py` fail while the main checkout passes them. That predates today's changes and is not yet explained.
