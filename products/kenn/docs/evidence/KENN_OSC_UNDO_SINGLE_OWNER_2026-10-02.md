# Undo route has one owner — 2 October 2026

An A2 slice (duplicate owner of `/api/ableton/osc/undo`). It follows
[KENN_FASTAPI_LIVE_COMMAND_OWNER_2026-10-02.md](KENN_FASTAPI_LIVE_COMMAND_OWNER_2026-10-02.md) and supports
[KENN_PLAN.md](../../KENN_PLAN.md).

## Reproduced defect and changed behavior

Undo lived inline in `server.py` (about 125 lines) and again, much shorter, in
`routes/daw_routes.py:handle_osc_undo`. Compared by reading:

- The FastAPI copy planned every undo with the generic `LiveActionService.propose_undo`, so a
  MIDI clip, clip duplication, rename, audition or sample-import receipt could not be reversed there.
- Its apply step called only the generic `execute`, so none of the domain undo proposals
  (clip remove, duplication undo, rename undo, audition stop, sample remove, device and recipe
  proposals) were routed to their services.
- It also recorded no receipt for the undo it had applied.

The inline block moved, verbatim apart from `self` becoming `handler` and the service lookup
using the existing `_get_live_action_service()` seam, to
`routes/daw_command_handler.py:handle_osc_undo(handler, payload)`. `server.py` and the FastAPI
route both call it. `daw_routes.py` lost four imports that nothing there uses any more.

## Verification

From `products/kenn/apps/backend/src`:

```sh
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests/test_fastapi_live_command_owner.py kenn/tests/test_server_smoke.py kenn/tests/test_mcp_facade.py kenn/tests/test_mcp_dispatch_routing.py kenn/tests/test_live_qualification_runner.py
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests
```

- Scoped: the four existing files that mention the undo route (165 tests) pass after the move; the new file has 7 cases, 2 of them for undo (plan and apply through
  FastAPI for a clip-duplication receipt, and stdlib/FastAPI parity on a plan and on a rejected request).
- Mutations caught: restoring the old FastAPI owner (2 fail), dropping the receipt record,
  disabling the duplication receipt dispatch and disabling the duplication undo apply branch. Files restored and byte-compared.
- Full backend: 3,507 passed, 12 skipped, no failures (122.31 s).

## Limits

- The other apply branches were moved without change and are exercised only by the existing
  suite, not by new cases. Only the clip-duplication path is pinned by the new tests, so a
  future edit to, say, the rename or device branch is not caught by this slice.
- The undo apply branches read only `confirm_token`, not the `confirmation_token` alias,
  matching the request model for this route (`UndoRequest`). Not changed.
- Services are faked; no Live was involved.

## Exact changed files

Paths are relative to `products/kenn`.

- `apps/backend/src/kenn/server.py`: undo block replaced by a call.
- `apps/backend/src/kenn/routes/daw_command_handler.py`: `handle_osc_undo` and its schema imports.
- `apps/backend/src/kenn/routes/daw_routes.py`: delegates; unused imports removed.
- `apps/backend/src/kenn/tests/test_fastapi_live_command_owner.py`: two more cases.
