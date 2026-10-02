# Removing the caller-less self-confirming write path — 2 October 2026

A2/A3 slice, found in the route map ([KENN_A2_ROUTE_MAP_2026-10-02.md](KENN_A2_ROUTE_MAP_2026-10-02.md)).

## Changed behavior

`tool_auto_remediate_session_issues` in `autonomous_agent.py` audited the session and applied the
whole remediation batch through `LiveActionService.execute_batch_autonomous`, which confirms its own
proposals. A repo-wide search (code and tests, excluding docs and runtime data) found no caller, no
string reference and no dynamic tool-table registration, so it was never reachable. It was the only
caller of that method, which made it a latent write path with no human in the loop. It is deleted,
along with `_track_confirmation`, an older token gate that also had no caller.

`execute_autonomous` and `execute_batch_autonomous` stay in `core/live_action_service.py`; they now
have no caller outside the service. Not changed: every route and tool that is reachable.

## Verification

From `products/kenn/apps/backend/src`:

```sh
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests/test_agent_tools_never_self_confirm.py kenn/tests/test_autonomous_tool_receipts.py kenn/tests/test_closed_loop_agent.py
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests
```

- Scoped: 10 passed, 2 of them new (`test_agent_tools_never_self_confirm.py`).
- Full backend: 3,520 passed, 12 skipped, no failures (123.34 s), the earlier 3,518 plus the two new cases.
- Restoring the old file makes both new tests fail; the edited file was restored and byte-compared.

No model was loaded, nothing was written to Live, no dependency or CI file changed.

## Limits

- The guard is a source check on `autonomous_agent.py`. A new self-confirming path added in some
  other module would not trip it.
- `LiveExecutor` (`core/live_executor.py`) also has no production caller but five test files build
  on it, so it was left alone rather than folded into this slice.
- `run_agent_loop` and the closed-loop session methods are reachable from each other and from a
  test (`test_closed_loop_agent.py`), so they were not touched.

## Exact changed files

Paths are relative to `products/kenn`.

- `apps/backend/src/kenn/autonomous_agent.py`: two functions removed (33 lines, no additions).
- `apps/backend/src/kenn/tests/test_agent_tools_never_self_confirm.py` (new, 2 cases).
- `docs/evidence/KENN_AUTONOMOUS_DEAD_WRITE_PATHS_2026-10-02.md`: this receipt.
- `docs/evidence/KENN_A2_ROUTE_MAP_2026-10-02.md` and `KENN_PLAN.md`: link and tick.
