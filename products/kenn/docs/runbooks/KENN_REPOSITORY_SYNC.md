# KENN sharing and local cloud catch-up

Jack approved this setup on 3 October 2026. `products/kenn/` in the monorepo
is authoritative. A pushed KENN change exports that committed folder to the
same branch in the private `Nite-DSP/kenn-app` sharing repository. This is
eventual sync after a successful GitHub Actions run, not sync of unsaved files.

## Sharing mirror

The workflow is `.github/workflows/kenn-app-sync.yml` in the monorepo. It has
read-only source access and uses `KENN_APP_SYNC_TOKEN`, a fine-grained personal
access token restricted to `Nite-DSP/kenn-app`. Existing personal mirror
automation is unchanged.
It checks the exact exported tree, blocks private paths, audio, model weights,
runtime files and common credential formats, and uses ordinary fast-forward
pushes. It never deletes destination branches or rewrites their history.

Activation is pending: GitHub rejected a repository deploy key because deploy
keys are disabled for this repository. No organization policy was changed and
no broad personal token is reused. Jack must provision a fine-grained token
with only `kenn-app` selected, **Contents: read and write** and **Workflows:
read and write**, then store it as the monorepo Actions secret
`KENN_APP_SYNC_TOKEN`. Workflow access is needed because the exported KENN
folder already contains its own `.github/workflows/` files. The token is never
saved in a remote URL or the checkout. Until that secret exists, automatic
sharing sync stops with an explicit missing-credential error.

New feature branches preserve destination `main` as their parent. Existing
branches require matching source markers and stop on independent destination
edits or rewritten source history. Import colleagues' changes explicitly into
the monorepo and review the reconciliation before resuming sync.

`kenn-app/main` needs a reviewed baseline because the existing split histories
do not share a commit ancestor. A later review step must prepare a reconciliation branch
from committed monorepo `main`, not from unfinished feature work. Neither
`main` is changed by preparing the PR. Merge that PR using **Create a merge
commit**, preserving the source marker in its ancestry. Squash/rebase without
that marker blocks future sync. A bounded monorepo automation PR also needs to be
prepared, reviewed and merged before expecting automatic sync from monorepo
`main`. Neither review PR has been created by this cleanup.

From the monorepo root, manual equivalents are:

```bash
products/kenn/tooling/scripts/sync_kenn_app.sh \
  --branch fix/review-critical-2026-10-02 --bootstrap --push

products/kenn/tooling/scripts/sync_kenn_app.sh \
  --source-ref origin/main --branch main \
  --destination-branch sync/reconcile-main-2026-10-03 --reconcile --push
```

Omit `--push` to prepare an object without publishing it. Automation ignores
`sync/**` setup branches and fetches the latest source branch tip before export.
The Actions page shows success or a stopped sync. Manual dispatch is available
after the workflow reaches the default branch.

## Mac catch-up

The opt-in user LaunchAgent `com.nitedsp.kenn-git-catchup` checks at login and
every five minutes while awake. After waking, allow up to the next timer check;
opening a laptop is not itself a Git event. An unavailable external drive or
network produces a pause, retried on the next check. No server is restarted.

It fetches the checked-out branch's `origin` upstream and fast-forwards only
when the whole monorepo checkout is clean and the local tip is an ancestor.
It preserves dirty, staged and untracked files; divergent or ahead local
commits require review. It never pushes, stashes, resets, switches branches,
merges conflicts or copies local audio to GitHub. Current unrelated local work
therefore pauses automatic pulls. Commit or otherwise resolve that work yourself
before expecting automatic updates to the working files.

Installed on Jack's Mac on 3 October 2026. Its first check fetched the current
feature branch and paused the pull because local files were dirty. To reinstall
after reviewing script changes:

```bash
python3 products/kenn/tooling/scripts/install_local_sync.py --repo "$PWD"
```

The installed script and logs live under
`~/Library/Application Support/KENN/git-catchup/`, outside the checkout. Inspect
`sync.log` for fetched/updated/paused status. Source changes do not reinstall
the local script automatically; rerun the installer after reviewing them.
To pause the user agent without deleting anything:

```bash
launchctl bootout "gui/$(id -u)/com.nitedsp.kenn-git-catchup"
```

Claude Cloud must use the monorepo and the intended feature branch, commit and
push completed work. Changes made only in `kenn-app` stop the one-way mirror
and need explicit import. This setup does not qualify runtime performance,
memory pressure or Live audio behavior. C1, C2 and C3 remain unticked.
