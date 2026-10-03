# Remaining request-owner audit, 3 October 2026

Source review at `e522d52c` on `fix/review-critical-2026-10-02`. This updates three
unverified observations in [the 2 October route map](KENN_A2_ROUTE_MAP_2026-10-02.md).
No runtime behavior changed and no plan item is newly ticked.

## Current findings

- `routes/daw_routes.py::handle_confirmation_revoke` uses the imported
  `revoke_confirmation`. Both `server.py` and `routes/fastapi_app.py` bind the handler.
  It requires an exact nonempty session and token; the historical unused-import
  observation is superseded. Existing tests exercise both HTTP adapters on fake Live.
- `orchestrator.py::_dispatch_ableton` still substitutes `orchestrated-live` when
  session identity is absent; `_dispatch_autonomous_producer` similarly substitutes
  `orchestrated-producer`. Public payload and stream functions permit an empty session.
  These are shared fallback names, not separate request owners. The existing autonomous
  dispatch test supplies a session explicitly and does not establish isolation for
  anonymous calls. Next: a named regression fixture for two callers without identity,
  tracing proposal ownership, repeat-command context and cancellation before a fix.
- `autonomous-systems/thursday/thursday/client.py::ask_kenn` passes history and session
  to the current payload path. Its `ImportError`/`OSError` fallback calls
  `Audio_Too/server/agents/Shared/kenn_bridge.py::ask_kenn`, whose interface accepts
  neither history nor session. Both bridge branches call `ask_once` with `history=None`
  and omit session identity; they return answer text without payload metadata.
  When the current KENN package resolves, this reaches `core/chat_cli.py::ask_once`,
  which can query the companion before calling the current payload implementation.
  The source trace therefore establishes a lossy compatibility path, not proof that
  a separate legacy engine is loaded. Its older path assumptions and failure behavior
  still need an isolated fixture. No Thursday files were edited.

## Verification receipt

Run from `products/kenn` on 3 October 2026:

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH='apps/backend/src:tooling' apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_orchestrator_autonomous.py apps/backend/src/kenn/tests/test_confirmation_cancellation_routes.py apps/backend/src/kenn/tests/test_session_clear_revokes_pending_confirmations.py -o cache_dir=/private/tmp/kenn-remaining-owner-audit-20261003
```

Result: **62 passed, 2 existing deprecation warnings in 1.24 s**. Fresh pytest cache;
no real model, GPU job or real Live interaction. The warnings concern Starlette's
httpx integration and AnyIO's `BlockingPortal` alias; no dependencies were changed.
The last full backend run remains 4090 passed, 12 skipped and the known pre-existing
`test_personal_path_gate.py::test_the_shipped_tree_has_no_personal_path_or_remote_host`
failure. This documentation-only slice did not rerun the full suite.

Limits: source reading and existing scoped tests do not reproduce anonymous dispatch
or the Thursday fallback. No confirmation bypass, cross-chat execution, inference
abort or latency improvement is claimed. C1, C2 and C3 remain unticked; their Live-open
15 s gate is still failed. Physical GPUs 0 and 1 are authorized, but this audit needs
neither GPU inference nor an index rebuild.
