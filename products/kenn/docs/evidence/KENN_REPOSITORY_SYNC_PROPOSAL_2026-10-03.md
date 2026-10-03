# KENN repository sync proposal, 3 October 2026

Jack uses the private `kenn-app` repository to share KENN with work colleagues
and asked for it to stay in sync with the monorepo. This records the inspected
state and proposed setup. Automation is not enabled and no destination branch
has been changed. [KENN_PLAN.md](../../KENN_PLAN.md) remains the work queue.

## Inspected state

- Monorepo source checkpoint: `b00c262b`, branch
  `fix/review-critical-2026-10-02`.
- `kenn-app/main`: `9b9ccc9c`, dated 30 September. The destination does not yet
  have `fix/review-critical-2026-10-02`.
- Both repositories are private. KENN's sharing layout already exports
  `products/kenn/` as the destination root.
- [The existing manual script](../../tooling/scripts/sync_kenn_app.sh) exports
  monorepo `main` only; it is not automatic and cannot export this feature
  branch. It requires a fast-forward destination update. Its fresh-checkout
  verification also removes a temporary directory; the script was not run.
- Splitting the committed source produced
  `635786ee780bd7e22050ea3f71b7cce1b8cdfdd6`. Its tree exactly matches
  `b00c262b:products/kenn`, but `kenn-app/main` is not its ancestor and there is
  no common commit ancestor. The split and destination histories contain
  rewritten equivalents: the soak receipt exists in both under different IDs.
  Commit counts therefore do not establish how many independent changes exist.
- There are 489 changed tracked paths between the destination's current tree
  and the current KENN tree. This is a tree comparison, not a reviewed list of
  safe changes to publish.
- [The collaborator guide](../GETTING_STARTED.md) still says to develop in
  `kenn-app` and import releases back. That conflicts with the current monorepo
  source-of-truth rule and must be corrected when the sharing workflow is agreed.

## Proposed setup for Jack to approve

1. Keep `products/kenn/` in the monorepo authoritative. Export only committed
   KENN files, with that directory becoming the root of `kenn-app`; exclude
   unrelated products, working-folder changes and untracked runtime data.
2. Map monorepo branches to the same branch names in `kenn-app`. Monorepo `main`
   supplies shared `main`; the current feature branch supplies
   `fix/review-critical-2026-10-02`. Mirroring the feature branch does not merge
   its unfinished work into either `main`.
3. Run synchronization in GitHub Actions after a pushed KENN change, with a
   manual catch-up option. This is eventual synchronization of pushed commits,
   not live synchronization of unsaved or uncommitted edits. Serialize updates
   per destination branch and report failed syncs.
4. Use repository write access restricted to the sharing repository. Do not
   reuse or expand the personal-mirror credential without Jack's approval.
5. Review the initial tree differences and any standalone collaborator changes
   before establishing the shared baseline. Preserve the existing destination
   history and branches. Do not force-push, delete branches or silently replace
   independent colleague changes. If histories cannot fast-forward, prepare a
   reconciliation pull request for review rather than treating the destination
   as disposable.
6. After that baseline, verify the exported tree against the committed source
   on every sync. Stop on unexpected destination edits rather than overwriting
   them. Colleagues should contribute through monorepo pull requests; work
   submitted only to `kenn-app` needs an explicit import and review before sync
   resumes. Automatic two-way merging is outside this proposal.

Activation needs Jack's approval for CI changes and repository write access,
under his standing instructions. No dependencies, CI files, credentials,
permissions, repository visibility or branch protections were changed here.

## Verification and limits

Read-only inspection used repository metadata, destination branch and workflow
lists, and `git fetch --quiet kenn-app main`. No credentials were printed.

```text
git subtree split --quiet --prefix=products/kenn HEAD
git merge-base --is-ancestor kenn-app/main 635786ee780bd7e22050ea3f71b7cce1b8cdfdd6
git merge-base kenn-app/main 635786ee780bd7e22050ea3f71b7cce1b8cdfdd6
```

Results: split succeeded; both ancestry checks exited 1. Tree-ID comparison
confirmed the split exactly matches the committed KENN folder. No files from
the dirty working tree enter that split. No CPU-heavy verification job ran
alongside it and no index was rebuilt.

This is a proposal and repository inspection, not a completed sync or a KENN
runtime qualification. C1, C2 and C3 remain unticked. The previously recorded
personal-path suite failure remains open; neither a fresh clone test nor a
full destination publication/history audit was run for this proposal.
