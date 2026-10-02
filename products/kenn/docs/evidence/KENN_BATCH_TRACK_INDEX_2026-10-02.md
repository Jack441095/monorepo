# Batch parameter changes need a track — 2 October 2026

An A2 slice. It supports [KENN_PLAN.md](../../KENN_PLAN.md) and follows the track-0 sweep in
[KENN_DOCTOR_REMEDIATION_CLOSED_2026-10-02.md](KENN_DOCTOR_REMEDIATION_CLOSED_2026-10-02.md).

## Reproduced defect and changed behavior

`LiveControlPlanner.propose_batch_parameter_changes` read `int(change.get("track_index", 0))`. A batch
change with no `track_index` was therefore planned against track 0: the planner inspected track 0's
device and issued a confirmation token for it. The repo rule is that KENN never assumes track 0, and the
single-change HTTP route already refuses a missing track.

A change with no `track_index` (or `null`) now returns
`Batch change N has no track_index; KENN never assumes track 0.` before any Live inspection. Device and
parameter indices still default to 0 on purpose: a parameter may be named instead of numbered, and
two existing tests (duplicate-name resolution, malformed request) depend on that.

## Verification

From `products/kenn/apps/backend/src`:

```sh
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests/test_batch_transactions.py
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests
```

- Scoped: 11 passed (1 new: the refusal, which also asserts Live was never asked for device parameters).
- Restoring the old line fails the new test. My first version also required device and parameter
  indices and broke two existing tests; I narrowed it to the track.
- Full backend: 3,512 passed, 12 skipped, no failures (115.84 s).

## Limits

- Device and parameter index defaults to 0 remain. A caller that names neither a device index nor a
  parameter name still gets device 0 / parameter 0 of the given track.
- Other track-0 fallbacks stay: `core/session_doctor.py` and `core/subjective_translator.py` read tracks from
  a Live snapshot, not from a request, and `core/live_executor.py` is unreachable. Not changed.

## Exact changed files

Paths are relative to `products/kenn`.

- `apps/backend/src/kenn/core/live_control_planner.py`
- `apps/backend/src/kenn/tests/test_batch_transactions.py`
