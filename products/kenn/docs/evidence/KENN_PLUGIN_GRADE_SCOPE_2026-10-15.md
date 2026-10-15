# Plug-in grade scoping — 15 October 2026

This records a bounded E2 correctness fix in [KENN_PLAN.md](../../KENN_PLAN.md), based on `66fabec9`.

## Changed behavior

The plug-in live-context response used to combine its per-insert snapshot with `get_mix_doctor().get_latest_report()` and the telemetry manager's process-wide latest reading. Neither global value carried an insert/session association, so a request for one plug-in context could receive another session's MQM summary and grade.

The response now withholds both `mqm` and `grade` until those readings can be tied to the requested session. A regression seeds a process-wide latest report while requesting an unrelated insert context and verifies neither field appears. This restores the correct grade provenance; it does not complete the plug-in grade display or session-scoped grade delivery.

## Verification

Backend command, from `products/kenn/apps/backend/src`, using FakeLive:

```sh
KENN_LIVE_BACKEND=fake ../.venv/bin/python -m pytest -q -p no:randomly kenn/tests/test_plugin_handoff.py
```

**59 passed in 0.10 s.** `git diff --check` passed.

## Exact changed files

- `apps/backend/src/kenn/plugin_handoff.py`: remove unassociated process-wide report and telemetry from per-insert context responses.
- `apps/backend/src/kenn/tests/test_plugin_handoff.py`: verify an unrelated latest report cannot appear in the requested context.
- `KENN_PLAN.md`: correct the earlier handoff grade claim and keep scoped grade delivery open.
- `docs/evidence/KENN_PLUGIN_GRADE_SCOPE_2026-10-15.md`: this receipt.
