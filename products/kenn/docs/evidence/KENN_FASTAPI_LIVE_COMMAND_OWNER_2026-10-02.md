# FastAPI Live command route uses the stdlib owner — 2 October 2026

An A2 slice (duplicate owner of `/api/ableton/command`). It supports
[KENN_PLAN.md](../../KENN_PLAN.md).

## Reproduced defect and changed behavior

`routes/daw_routes.py:handle_live_command`, the FastAPI owner, was a second copy of
`routes/daw_command_handler.py:handle_live_command`, the stdlib owner. Compared by reading
and by running a fixture:

- A proposal with a MIDI clip schema, posted to the FastAPI function with a token,
  returned 200 and `requires_confirmation` ("Explicit confirmation is required for this exact
  MIDI clip proposal."). The generic planner does not know the domain schemas, so a clip
  create/update/remove, duplication, rename, audition or sample proposal was never applied.
  It failed closed, not open.
- A command that did apply on this route recorded no receipt, so Undo had nothing to find.
- The route's `CommandRequest` drops `llm_plan`, `recipe_steps`, `deterministic_only`,
  `correlation_id` and `mix_review_id`. That is unchanged here.

`daw_routes.handle_live_command` now runs the stdlib handler against a small reply collector
and returns its status and body. The shared pending-proposals dict is passed through.

## Verification

From `products/kenn/apps/backend/src`:

```sh
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests/test_fastapi_live_command_owner.py kenn/tests/test_confirmation_cancellation_routes.py kenn/tests/test_fastapi_routes.py
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests
```

- Scoped: 61 passed across the three files (5 new, in `test_fastapi_live_command_owner.py`).
- Mutations caught: restoring the old function (3 of 4 original cases fail), dropping the
  `session_id` argument fallback, and passing an empty dict instead of the shared pending dict
  (that one survived my first four tests and caused the fifth to be written). Files were
  restored and byte-compared.
- Full backend: 3,505 passed, 12 skipped, no failures (121.66 s).

No model loaded, nothing written to Live, no dependency or CI change.

## Limits

- Handlers are faked at the service boundary; no Live (real or fake) was involved.
- `/api/ableton/osc/undo` still has two owners; it is the next slice.
- The FastAPI request model still ignores the extra fields listed above, so evidence-bound
  recipes and client-supplied plans stay unavailable on that app. Widening it is a separate decision.
- `MidiClipActionService` is imported but unused in `daw_routes.py`; left alone.

## Exact changed files

Paths are relative to `products/kenn`.

- `apps/backend/src/kenn/routes/daw_routes.py`
- `apps/backend/src/kenn/tests/test_fastapi_live_command_owner.py` (new)
