# LaunchAgent installer placeholders and stale doc pointers — 2 October 2026

A3 slice. It supports [KENN_PLAN.md](../../KENN_PLAN.md) and is the first part of the document-pointer
and container-path audit. The audit itself stays open; the open findings are listed below.

## Reproduced defect and changed behavior

`tooling/scripts/install_launchagent.sh` filled the plist template with
`s#<WORKSPACE_ROOT>/Nite-DSP-Operations/Shenrendao/KENN#${PRODUCT_ROOT}#g`. The template
(`apps/desktop/launchd/com.shenrendao.kenn.companion.plist`) now uses `<KENN_REPO_ROOT>` (three times)
and `<USER_HOME>` (twice), so that expression matched nothing and the installed agent kept literal
`<KENN_REPO_ROOT>` paths. It would have loaded and then failed to start the server. The sed now
substitutes `<KENN_REPO_ROOT>`; the `<USER_HOME>` substitution was already right.

Doc pointers that named files that no longer exist, each re-pointed at a target checked to exist:

- `README.md`: `runtime/legacy/` is now `runtime/legacy-salvage/`.
- `docs/guides/KENN_BETA_TESTER_GUIDE.md`: the readiness report, support runbook and gap matrix links.
- `docs/guides/ABLETONOSC_ROUTE.md`: the installer path (`tooling/scripts/install_abletonosc.py`) and
  the current-state report (two references).
- `docs/handover/SLO_ARTIFACT_HANDOFF.md`: the manifest template link now goes through `../evidence/`.

## Verification

From `products/kenn/apps/backend/src`:

```sh
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests/test_launchagent_install_fills_placeholders.py
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests
```

- Scoped: 2 new cases. They run the real script with a temporary `HOME` and a stub `launchctl` on
  `PATH`, then check that no `<UPPER_CASE>` placeholder is left in the installed plist and that it
  points at `apps/backend/src/kenn/server.py` under the product root (the file exists).
- Mutation check: both cases fail against the `HEAD` copy of the script and pass with the fix.
- Full backend: 3,534 passed, 12 skipped, no failures (118.75 s).
- The real `~/Library/LaunchAgents/com.shenrendao.kenn.companion.plist` was not touched.

## Open findings (not changed)

- `Audio_Too/studio/kenn` is a symlink that lands on `products/kenn`, not on the package directory, so
  `studio/kenn/kenn` does not resolve. Callers that expect it: `Audio_Too/main.py` (lines 294, 412, 609),
  `Audio_Too/server/app/ableton_bridge.py`, scripts and tests under Audio_Too, `Audio_Too/Dockerfile:44`
  and `audio-too-ci.yml` (manual dispatch only). Audio_Too is the frozen legacy tree and has other
  people's uncommitted edits, so it needs a decision, not a drive-by fix.
- `chat/Dockerfile` and `packages/chat/Dockerfile` (identical) copy `Audio_Too/studio/kenn` and install
  `Audio_Too/studio/kenn/kenn/requirements.txt`, which does not exist for the same reason.
- Stale labels in `chat/eval_runner.py:327`, `packages/chat/app.py:36` and the mix-review adapters.
- Backticked paths in `docs/handover/HANDOVER_2026-09-14.md`, `HANDOVER_2026-09-06.md`,
  `SLO_HANDOFF_AUDIT_2026-09-09.md` and `KENN_MIGRATION_RECEIPT.md` point at the pre-consolidation layout.
  They are dated records, so they were left as written.
- `notes_server_preflight.sh:34` uses a remote-host, git-ignored data path; low risk.

## Limits

- The Dockerfiles, the Audio_Too CI workflow and a real `launchctl load` on this Mac were not run. The
  test uses a stub `launchctl`, so it proves the file the script writes, not that launchd accepts it.
- The pointer fixes were checked by existence of the target, not by a link checker over the whole docs tree.

## Exact changed files

Paths are relative to `products/kenn`.

- `tooling/scripts/install_launchagent.sh`: placeholder in the sed expression.
- `apps/backend/src/kenn/tests/test_launchagent_install_fills_placeholders.py` (new, 2 cases).
- `README.md`, `docs/guides/KENN_BETA_TESTER_GUIDE.md`, `docs/guides/ABLETONOSC_ROUTE.md`,
  `docs/handover/SLO_ARTIFACT_HANDOFF.md`: pointer fixes.
- `docs/evidence/KENN_LAUNCHAGENT_AND_DOC_POINTERS_2026-10-02.md`: this receipt.
- `KENN_PLAN.md`: A3 sub-bullet.
