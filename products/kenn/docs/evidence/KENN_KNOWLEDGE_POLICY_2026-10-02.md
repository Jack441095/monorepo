# Request-local knowledge policy — 2 October 2026

This records an A2/A3 slice after `42845978`, supporting
[KENN_PLAN.md](../../KENN_PLAN.md). The broader request-owner audit remains open.

## Reproduced defects

The MCP binding is `KennMCPFacade.handle_message` →
`core.mcp.knowledge.ask_audio_engineering_question` →
`KennHTTPClient.post("/api/knowledge/ask")` → `server.Handler.do_POST` →
`server.grounded_knowledge_answer` → `core.chat_answer.answer_payload`.

The knowledge helper temporarily replaced six engine functions under a lock that
normal chat did not use. A deterministic test paused knowledge retrieval while
another chat ran: the normal chat returned `production` instead of its fixture
specialist. Both public `_scoped_answer_payload` owners reproduced the same race
under their separate wrapper locks.

The helper's replacements also left the earlier short-circuit evaluator active.
Knowledge questions `play` and `stop` created transport proposals; preference
commands reached conversational memory shortcuts. The helper omitted session and
plugin identifiers, losing scoped preferences and recording an anonymous chat
turn. The HTTP route discarded the Mix Review identifier supplied by MCP, and a
null question became the text `None`.

## Changed behavior

The answer engine now accepts a request-local `retrieval_only` policy. It disables
model generation, conversational memory/cache writes, mutable shortcuts and
specialist dispatch. Ordinary chat retains its existing default policy. The
knowledge helper and both public wrappers no longer replace shared functions.

The bounded `retrieval_route` option permits `production` or `ableton` knowledge
when retrieval-only mode is selected. The package wrapper retains its existing
route classifier plus whole-word Live concept check, preserving Ableton workflow
answer shapes without dispatch. The legacy wrapper and MCP use `production`.
Package missing-index abstention remains intact.

The HTTP knowledge route rejects null or empty questions before the engine. It
normalizes optional identifiers, forwards the explicit stored Mix Review ID and
request correlation ID, and retains session/plugin IDs through the real public
answer binding. Stored review metrics and already-captured plugin evidence keep
their existing typed history envelopes. A named project's preferences can inform
an answer without adding another conversational turn or semantic-cache entry.
Diagnostic trace storage and existing read-only evidence lookup remain separate;
this does not claim that all storage access is disabled.

## Verification

Tests use temporary SQLite databases, empty retrieval fixtures, thread events,
fake transport proposals and ephemeral loopback HTTP servers. No model was
loaded, no dependency was added, no grounding rule changed, and engineering did
not write to a running Live session.

- Before the engine fix, the first knowledge regression file produced 15 failures
  and one pass. The failures include the actual race, transport shortcuts, lost
  preferences, dropped review ID and null question, plus the absent policy API.
- The final knowledge file has 20 passing cases, including actual public-engine
  context binding and MCP → real HTTP → helper → engine forwarding of typed
  stored review evidence.
- The scoped backend command below passed 218 tests in 8.85 s. The combined
  backend run passed 3,171 tests with 12 optional-dependency skips in 98.40 s;
  the A5 receipt records that command and the skip boundaries. This run predates
  the next reference/status/cancellation fixes.
- Both new wrapper concurrency tests fail against their original wrappers.
  Legacy `chat/tests/test_app.py`: 39 passed. Package `test_app.py`,
  `test_public_api.py` and `test_security_and_abuse.py`: 61 passed, including
  existing real-index Ableton EQ Eight answer-shape checks.
- Eighteen engine/HTTP mutations and seven wrapper mutations were caught by
  failures. These cover shared dispatcher replacement, shortcut/model/memory
  policy, specialist hooks, context forwarding, nullable input, safe routes and
  the explicit Live guard. Mutated sources were restored and SHA-256 checked.

The backend scoped command, from `products/kenn/apps/backend/src`, is:

```sh
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests/test_knowledge_request_context.py kenn/tests/test_server_smoke.py kenn/tests/test_mcp_facade.py kenn/tests/test_project_memory_stage4.py kenn/tests/test_answer_upgrade_context.py kenn/tests/test_answer_upgrades.py kenn/tests/test_answer_upgrade_timeout.py kenn/tests/test_chat_route_context.py kenn/tests/test_fastapi_routes.py kenn/tests/test_chat_answer_evidence.py kenn/tests/test_server_evidence_context.py kenn/tests/test_realtime_mix_comparison.py kenn/tests/test_session_grounded_advice_evaluation.py
```

Local mutation receipts are `/tmp/kenn-knowledge-mutations-2026-10-02.json` and
`/tmp/kenn-wrapper-mutations-2026-10-02.json`. Wrapper suite logs are
`/tmp/kenn-legacy-knowledge-suite-2026-10-02.log` and
`/tmp/kenn-package-knowledge-suite-2026-10-02.log`.
The scoped backend log is `/tmp/kenn-knowledge-scoped-final-2026-10-02.log`.

## Remaining scope

The public wrappers still change legacy model enablement at import, and index
overrides can alter shared retrieval modules. Those import-time owners need
separate fixtures. This fix does not establish complete main-HTTP/FastAPI/public
route parity, streaming or model cancellation, cache invalidation after Live or
preference changes, Apply/readback/Undo, real-model quality or Live qualification.

## Exact changed files

Paths below are relative to `products/kenn`.

- `KENN_PLAN.md`: checks only this verified request-policy slice.
- `docs/evidence/KENN_KNOWLEDGE_POLICY_2026-10-02.md`: this receipt.
- `apps/backend/src/kenn/core/chat_answer.py`: request-local knowledge policy and
  bounded production/Ableton retrieval route.
- `apps/backend/src/kenn/server.py`: removes global hook replacement and forwards
  knowledge request context with nullable-input validation.
- `apps/backend/src/kenn/tests/test_knowledge_request_context.py`: 20 policy,
  concurrency, memory, context and HTTP/MCP regressions.
- `chat/app.py` and `packages/chat/app.py`: migrate their public knowledge owners.
- `chat/tests/test_app.py` and `packages/chat/tests/test_app.py`: seven wrapper
  regressions for concurrency, policy forwarding and safe answer shape.
