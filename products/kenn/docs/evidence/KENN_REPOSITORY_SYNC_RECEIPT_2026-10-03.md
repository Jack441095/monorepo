# KENN repository sync receipt — 3 October 2026

Source commit: `08f4f28b821c3206c8f550b0105bd40db290d97f` on `fix/review-critical-2026-10-02`.

The committed KENN folder can be exported to the matching sharing branch with an exact tree check and ordinary fast-forward push. Independent destination edits, rewritten source history, private paths, runtime files, audio, model weights and common credential formats stop the export. The installed local agent fetches at login and every 300 seconds while awake, and updates only a clean checkout by fast-forward.

## Verification

From the repository root:

```sh
PYTHONPATH=products/kenn/tooling python3 -m unittest discover -s products/kenn/tooling/tests -p test_sync_kenn_app.py -q
```

Result: 24 passed in 16.227 s. Temporary local repositories cover exact export, clean catch-up, dirty/divergent pause behavior, independent destination edits, rewritten history, reconciliation boundaries and privacy guards.

From `products/kenn`:

```sh
PYTHONPATH=apps/backend/src:tooling KENN_LIVE_BACKEND=fake python3 -m pytest -q apps/backend/src/kenn/tests/test_personal_path_gate.py -o cache_dir=/tmp/kenn-sync-privacy-20261003-final
```

Result: 24 passed. The previous full KENN run had 4,133 passed, 12 skipped and one personal-path failure in the existing handoff; replacing its personal volume path with a portable example resolves the scoped privacy check. The whole suite was not rerun for these tooling/document changes.

Shell syntax and workflow YAML checks passed. The first installed-agent check fetched cloud work and paused because the local checkout was dirty.

Manual sharing verification from the repository root:

```sh
products/kenn/tooling/scripts/sync_kenn_app.sh --branch fix/review-critical-2026-10-02 --bootstrap --push
```

Result: source `08f4f28b821c3206c8f550b0105bd40db290d97f` exported to sharing commit `3982bed0c09a` on the matching feature branch. Remote readback confirmed an exact committed tree match. This receipt is a subsequent documentation commit; rerun the same command after committing it to include these docs in the mirror.

## Limits

The GitHub mirror workflow is prepared but cannot activate until `KENN_APP_SYNC_TOKEN` is provisioned with destination-only Contents/Workflows write access. Existing policy rejected a deploy key; no organization policy or permissions were widened. Neither main is changed, and main reconciliation/review PRs remain future steps. Unsaved work never syncs. Dirty local work pauses catch-up. This does not measure model latency, memory pressure or real Live audio behavior; C1/C2/C3 remain unticked and the 15 s gate remains failed.

The [cleanup receipt](../../../../validation/reviews/2026-10-03-working-tree-cleanup.md) records all source commits, exact changed files, other-product checks and remaining failures.
