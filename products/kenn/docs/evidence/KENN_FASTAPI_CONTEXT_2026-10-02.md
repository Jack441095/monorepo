# FastAPI chat binding and context — 2 October 2026

This records a bounded A2/A3 audit and fix after `7f9139ab`. It supports
[KENN_PLAN.md](../../KENN_PLAN.md); the broader route and context audit remains open.

## Reproduced defects and changed behavior

The actual binding is `routes.fastapi_app.ask_endpoint` →
`routes.chat_routes.handle_ask` → `core.chat.answer_payload`, which re-exports
`core.chat_answer.answer_payload`. A real `TestClient` request reproduced
`TypeError: answer_payload() got an unexpected keyword argument 'orchestrator'`.
The five existing FastAPI route tests did not send an ask request. No caller of
this handler supplied its unused optional `orchestrator` argument.

The handler now uses the public answer signature. It preserves the engine's
existing routing policy, forwards the plugin identifier and generated request
correlation identifier, and retains history plus bounded session context.
`AskRequest` now accepts `plugin_session_id`; Pydantic previously discarded it.
Missing or explicitly null optional identifiers become empty strings, and a
null retrieval limit uses the existing default of 5. A missing or null question
still returns 422; whitespace-only input returns 400 before starting a turn.

FastAPI ask now starts a turn in the existing in-process background registry.
Session clear invalidates that chat's pending or completed result before clearing
session memory. Another chat's result remains available. A late worker cannot
restore its discarded result, and its model slot remains occupied until it
finishes. Invalid questions do not discard the previous answer. These changes do
not coordinate separate server processes or claim to abort inference.

The chat facade docstring also pointed to the retired `docs/BACKLOG.md`. It now
points to the sole plan and Git history for the decomposition record.

## Verification

The new tests keep the real public answer function for request binding checks,
and replace only its lower implementation with a deterministic result. A separate
test runs the real retrieval-only answer against empty index fixtures and a
temporary SQLite database: song A reads its explicit preference, song B does
not, each question records one turn, and submitted history is not mutated.
Late-completion tests use events and isolated background jobs. Engineering did
not write to a running Live session, load a model, install dependencies or change
grounding rules.

Before the fix, the new file produced seven failures and three passes, including
the public-signature crash, null-limit error and both session-clear aliases.
After the fix, from `products/kenn/apps/backend/src`:

```sh
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests/test_chat_route_context.py kenn/tests/test_fastapi_routes.py kenn/tests/test_project_memory_stage4.py kenn/tests/test_answer_upgrade_context.py kenn/tests/test_answer_upgrades.py kenn/tests/test_answer_upgrade_timeout.py
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests/test_live_command.py::test_llm_plan_gets_one_structural_repair_attempt
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests/test_personal_path_gate.py
```

- Scoped suite: 49 passed, two existing deprecation warnings, in 3.59 s.
  A final run with chat-directory and legacy-file paths also isolated passes the
  same 49 checks in 3.16 s.
- Initial full backend suite: 3,131 passed, 12 skipped, five warnings and two
  failed in 76.96 s. One failure is the known structural-repair order dependency;
  it passes alone in 0.11 s. The other caught three machine-specific command paths
  missed in the preceding research commit. Those commands now derive their root
  from Git. The gate was not weakened. Follow-up verification is recorded below.
- Follow-up full suite: 3,132 passed, 12 skipped, five warnings and the same
  structural-repair failure in 73.58 s. A5 remains open; no assertion was weakened.
- Personal-path and planning artifact checks: 88 passed in 2.47 s. All 62 local
  Markdown links across the plan, this receipt and the research report resolve.
- Ten deliberate mutations were caught by assertion failures: unsupported answer
  keyword, request plugin field, engine plugin identifier, engine correlation,
  new-turn invalidation, session-clear invalidation, null session normalization,
  null limit default, session context, and project session forwarding. Each run
  used a separate Python bytecode cache. Edited files were restored and SHA-256
  checked after the run.

Local logs are `/tmp/kenn-fastapi-suite-2026-10-02.log`,
`/tmp/kenn-fastapi-suite-verified-2026-10-02.log` and
`/tmp/kenn-fastapi-mutations-2026-10-02.json`. The temporary mutation script is
`/tmp/kenn-fastapi-mutations-2026-10-02.py`; individual outputs use the
`/tmp/kenn-fastapi-mutation-` prefix.

## Remaining audit scope

FastAPI's async ask endpoint still invokes the synchronous engine directly.
Event-loop scheduling, cancellation and model admission across request owners
remain unqualified. This slice does not establish full main-HTTP/FastAPI route
parity, streaming behavior or proposal/Apply/readback/Undo behavior.

The separate MCP knowledge tool posts to the main server's `/api/knowledge/ask`,
bound to `server.grounded_knowledge_answer`. That helper temporarily replaces
module-level chat-engine functions while holding a lock used only by that helper,
then calls the answer engine without session/plugin identifiers. Concurrent
interaction with other owners and its memory behavior still need independent
fixtures. This is a source finding, not a reproduced concurrency defect here.

Preference/Live changes, project switching and Apply/Undo during generation also
remain open under A3. No real-model latency, answer quality or owner-supervised
Live qualification is claimed.

## Exact changed files

Paths below are relative to `products/kenn`.

- `KENN_PLAN.md`: marks only this verified A3 slice complete.
- `docs/evidence/KENN_FASTAPI_CONTEXT_2026-10-02.md`: this receipt.
- `apps/backend/src/kenn/routes/chat_routes.py`: correct answer binding, context
  forwarding, optional defaults and chat-specific background invalidation.
- `apps/backend/src/kenn/routes/fastapi_app.py`: accepts the plugin identifier.
- `apps/backend/src/kenn/core/chat.py`: removes the obsolete planning pointer.
- `apps/backend/src/kenn/tests/test_chat_route_context.py`: ten request, boundary,
  isolation and late-completion regressions.
- `docs/research/KENN_PRODUCT_AND_OPEN_SOURCE_RESEARCH_2026-10-02.md`: replaces
  three machine-specific command roots with the Git checkout root after the
  existing personal-path gate caught them.
