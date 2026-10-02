# Session Doctor remediation closed — 2 October 2026

An A2/A4 slice. It supports [KENN_PLAN.md](../../KENN_PLAN.md). It came from the route trace:
one finding from the first pass (a track-0 default) turned out to sit on a route that never worked.

## Reproduced defects and changed behavior

- `POST /api/session/doctor/remediate` (`routes/doctor_handler.py`) called
  `SessionDoctor.formulate_surgical_remediation_proposal(issue_code=..., track_index=..., ...)`, a
  signature that method does not have. Reproduced: every request, with or without a token, answered
  500 "unexpected keyword argument 'issue_code'". Its confirmed branch, had it been reached, answered
  `status: "applied"` and "applied to track N" without any Live write, and a missing `track_index`
  defaulted to 0. The route now answers 410 and says it is disabled until it has a typed, reversible
  proposal with readback, the same wording pattern the tempo and scene-launch routes use.
- The MCP tool `kenn_session_doctor` with `auto_remediate` posted the batch to
  `/api/kenn/autonomous-execute-batch`. That path appears in neither `server.py` nor
  `routes/fastapi_app.py`. It now reports `remediation_execution` as `not_executed` with `ok: false`
  and posts nothing.

The frontend wrapper `remediateDoctorIssue` has no caller in `apps/frontend/src`; it will now throw the
410 as an `ApiError` if something starts using it.

## Verification

From `products/kenn/apps/backend/src`:

```sh
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests/test_doctor_remediate_disabled.py kenn/tests/test_mcp_new_tools.py kenn/tests/test_doctor_handler.py
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests
```

- Scoped: 8 passed (4 new, in `test_doctor_remediate_disabled.py`).
- Restoring either old file fails the new tests (3 of 3 route cases; the MCP case).
- Full backend: 3,511 passed, 12 skipped, no failures (123.97 s).

## Limits

- Disabling is the conservative choice, not a repair: there is still no confirmed, read-back
  remediation path for Session Doctor findings.
- `SessionDoctor.formulate_surgical_remediation_proposal` and its remediation batch are untouched.
- Other track-0 fallbacks found in this trace (`core/live_control_planner.py` batch builder,
  `core/session_doctor.py`, `core/subjective_translator.py`, the unreachable `LiveExecutor`) are not
  changed here.

## Exact changed files

Paths are relative to `products/kenn`.

- `apps/backend/src/kenn/routes/doctor_handler.py`
- `apps/backend/src/kenn/core/mcp/session_intelligence.py`
- `apps/backend/src/kenn/tests/test_doctor_remediate_disabled.py` (new)
