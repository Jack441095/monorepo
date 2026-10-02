# Backend test isolation — 2 October 2026

This records the A5 diagnosis after `42845978`, supporting
[KENN_PLAN.md](../../KENN_PLAN.md). Existing planner assertions and production
enablement precedence remain unchanged.

## Cause and fix

Collecting the evidence-budget test module left `KENN_LLM_ENABLED=0` in the
process environment. The structural-repair test enabled only the legacy
`AUDIO_TOO_LLM_ENABLED` switch; the higher-priority KENN switch correctly kept
planning disabled. The same collection-time mutation existed in two capture
test modules, and importing the replay tool also changed that switch.

The three evidence test modules now disable generation inside per-test
`monkeypatch` fixtures. The replay tool preserves model policy on import. Its
`main()` sets the offline policy before lazy KENN imports and restores the
caller's previous value in `finally`, including the missing-index exit path.

Eight fresh-process import guards cover unset and enabled caller environments
for the four import targets. Four CLI cases check that replay stays offline and
restores the caller's setting when the index exists or is missing. This does not
change answer thresholds, retrieval, evidence scoring or planner repair behavior.

## Verification

- Minimal failing collection sequence before the fix: one failed, five passed.
- New import guards before the fix: seven failed, one passed.
- New CLI policy/restore guards before the fix: four failed.
- Scoped verification: 173 passed in 3.23 s, including all 130 Live command tests,
  capture/replay tests and configuration/task-switch tests.
- Seven deliberate mutations were caught. Source bytes were restored and
  SHA-256 checked; assertions were not weakened.
- Combined full backend run: 3,171 passed, 12 skipped, six existing dependency/vendor
  warnings in 98.40 s, with no failures. Five MLX cases skip because MLX/MLX-LM
  are unavailable in this environment, five sample-embedding cases require the
  optional PANNs model/runtime, and two training-provenance cases require optional
  Torch. Local-index checks ran; the skips are not model or real-Live qualification.

From `products/kenn/apps/backend/src`, the bounded command is:

```sh
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests/test_evidence_budget_alignment.py kenn/tests/test_measure_capture_evidence.py kenn/tests/test_rescore_capture_evidence.py kenn/tests/test_evaluation_import_isolation.py kenn/tests/test_live_command.py kenn/tests/test_llm_config_discovery.py kenn/tests/test_llm_task_switch.py
```

The full command from the same directory was:

```sh
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests
```

This result includes the request-local knowledge and public rewrite-readiness fixes.
It predates the next reference/status/cancellation fixes; those require their own
verification. The full log is `/tmp/kenn-parallel-suite-2026-10-02.log`.

Local receipts include `/tmp/kenn-a5-minimal-before.log`,
`/tmp/kenn-a5-import-before.log`, `/tmp/kenn-a5-cli-before.log`,
`/tmp/kenn-a5-scoped-final-2026-10-02.log` and
`/tmp/kenn-a5-mutations-2026-10-02.json`.

## Exact changed files

Paths below are relative to `products/kenn`.

- `KENN_PLAN.md`: records the verified A5 result.
- `docs/evidence/KENN_TEST_BASELINE_2026-10-02.md`: this receipt.
- `apps/backend/src/kenn/tests/test_evidence_budget_alignment.py`: scopes its
  offline policy to tests.
- `apps/backend/src/kenn/tests/test_measure_capture_evidence.py`: scopes its
  offline policy to tests.
- `apps/backend/src/kenn/tests/test_rescore_capture_evidence.py`: scopes its
  offline policy and verifies CLI restoration.
- `apps/backend/src/kenn/tests/test_evaluation_import_isolation.py`: eight
  fresh-process import guards.
- `tooling/scripts/rescore_captured_answers.py`: keeps replay policy inside CLI
  execution and restores the caller's switch.
