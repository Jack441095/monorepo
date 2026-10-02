# Background answer context — 2 October 2026

This records the first bounded A2/A3 audit and fix after the planning consolidation
at `f060bf54`. It is evidence for [KENN_PLAN.md](../../KENN_PLAN.md), not another
work queue. The broader route/context audit remains open.

## Verified defect and resulting behavior

The main HTTP ask handler passed session, plug-in and correlation identifiers to
the foreground answer, but passed only question, limit and history to its
background answer. Omitting the session identifier also lost project preferences:
`session_memory.update_session` generates an anonymous session when no identifier
is supplied. It did not prevent a second memory update.

The background call now retains all three identifiers and the submitted history.
`record_session=False` preserves preference reads while skipping the raw answer's
session update and the wrapper's semantic-cache lookup/save. The foreground
template records the user turn once. Normal foreground defaults are unchanged.
Reasoning traces and other diagnostics remain on their existing paths; this flag
is not a general prohibition on every diagnostic write.

Only an eligible knowledge template starts generation. A proposal response does
not trigger another background dispatch. Generation uses the existing grounding
and timeout rules; protected thresholds, measurement expressions and streaming
prefix checks are unchanged.

Each main HTTP ask begins a turn in its chat before early routing. A newer turn
or `/api/session/clear` discards that chat's previous result. A slow foreground
request cannot start an upgrade after a newer turn has begun. Polling requires the
originating `session_id`; another or missing identifier returns `expired`. This
is chat-identity scoping, not a new authentication system.

The worker keeps the single generation slot until inference finishes. Discarding
delivery does not claim to abort inference. Expired entries are pruned on polling
as well as admission/completion; result and turn maps each retain at most 50
entries, with a 600 s lifetime.

The UI checks message presence, pending state and current turn both before and
after a poll. Sending another question stops replacement of the older answer;
removing its message stops polling. Accepted sources replace template sources,
including clearing them when the accepted answer supplies none.

A worker finishing after invalidation logs `expired`, rather than `accepted`.
Busy admission is logged once by `answer_upgrades.start`. The timing harness uses
the same scoped engine calls. Its sequential run does not qualify HTTP/UI timing,
concurrent conversation or producer behavior. Server acceptance is not proof that
an answer was displayed; C1 still needs displayed-result timing.

## Traced boundary and remaining scope

| Boundary | Source binding inspected | Evidence in this slice |
| --- | --- | --- |
| Main UI request | `useKenn.sendMessage` → `api.askKenn` → `server.Handler.do_POST` | Identifier/history fixture and frontend tests |
| Foreground/background engine | `answer_payload` → `_answer_payload` → `_answer_payload_raw` | Project preference isolation; no second session update or cache access |
| Worker and poll | `answer_upgrades.begin_turn/start/get/invalidate` → `Handler.do_GET` | Owner, late-job, expiry, storage and HTTP clear fixtures |
| Display replacement | `api.getAnswerUpgrade` → `useKenn.waitForUpgrade` | Encoded owner query, in-flight supersession, removed message and empty sources |
| Sequential timing | `measure_background_swap.measure` | Same chat identifier; accepted/busy fixtures; one busy log |

Other bound owners were located but are not qualified by this change:
`routes.fastapi_app.ask_endpoint` calls `routes.chat_routes.handle_ask`;
`server.grounded_knowledge_answer` serves the separate knowledge path used by
`core.mcp.knowledge.ask_audio_engineering_question`. Their argument and temporary
engine-binding behavior needs independent fixtures. Voice consumers, stream
parity, every proposal/Apply/readback/Undo binding and alternate chat UIs also
remain under A2.

These identifiers do not freeze a context revision. Preference/Live changes,
project switching, Apply/Undo during generation and foreground semantic-cache
versioning remain open under A3. Upgrade payloads still replace answer text and
sources; full context/preference/trace metadata replacement is not qualified.
No real-model quality, latency or owner-supervised Live qualification was run.
Tests used isolated jobs, temporary SQLite state, mocked engine calls and a local
ephemeral HTTP fixture; engineering did not write to a running Live session.

## Verification

From `products/kenn/apps/backend/src`:

```sh
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests/test_answer_upgrade_context.py kenn/tests/test_answer_upgrades.py kenn/tests/test_answer_upgrade_timeout.py kenn/tests/test_measure_background_swap.py kenn/tests/test_project_memory_stage4.py kenn/tests/test_chat_stream_weak_retrieval.py
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests/test_live_command.py::test_llm_plan_gets_one_structural_repair_attempt
```

- Scoped backend: 48 passed, two existing deprecation warnings, in 4.27 s.
- Full backend: 3,122 passed, 12 skipped, five warnings and one failed in 78.18 s.
  The sole failure is the pre-existing order-dependent structural-repair test;
  it still passes alone, in 0.12 s. A5 remains open. No assertion was weakened.
- Frontend: 20 passed across `src/composables/useKenn.test.ts` and
  `src/api/kenn.test.ts`, using the installed ARM Node executable:
  `/opt/homebrew/bin/node node_modules/vitest/vitest.mjs run src/composables/useKenn.test.ts src/api/kenn.test.ts`.
  The default Intel Node selected a missing architecture-specific Rolldown
  binding; no dependency was installed or changed.
- Full frontend typecheck remains blocked by missing installed `@vue/test-utils`
  in unchanged `src/components/__tests__/KennRecipeCard.component.test.ts:3`.
  It is already declared in the package and lockfile. A temporary configuration
  extending `tsconfig.app.json`, excluding only that component test, passes
  `vue-tsc --noEmit`; the temporary file was removed.
- Fifteen mutations were caught by assertion failures: poll owner, new-turn
  invalidation, stale foreground admission, poll TTL, storage bound, duplicate
  memory, background cache access, background identifiers, HTTP session clear,
  proposal re-dispatch, discarded-answer metrics, in-flight UI response,
  removed-message polling, source replacement and UI poll owner. Each edited
  source was restored and SHA-256 checked before the next mutation.

Local logs: `/tmp/kenn-answer-upgrade-suite-2026-10-02.log` and
`/tmp/kenn-upgrade-mutations-2026-10-02.json`; individual mutation outputs are
`/tmp/kenn-upgrade-mutant-0.log` through `-14.log`.

## Exact changed files

Paths below are relative to `products/kenn`.

- `KENN_PLAN.md`: checks off this bounded slice while retaining the broader audit.
- `docs/evidence/KENN_BACKGROUND_CONTEXT_2026-10-02.md`: this receipt.
- `apps/backend/src/kenn/core/answer_upgrades.py`: scoped turns, polling,
  invalidation, pruning and single admission/outcome logging.
- `apps/backend/src/kenn/core/chat_answer.py`: optional session recording and
  background semantic-cache exclusion.
- `apps/backend/src/kenn/core/route_log.py`: exposes expired outcomes.
- `apps/backend/src/kenn/server.py`: identifiers, eligible admission, turn
  supersession, scoped polling and session-clear invalidation.
- `apps/backend/src/kenn/tests/test_answer_upgrade_context.py`: new context,
  isolation, expiry, concurrency, metric and HTTP regressions.
- `apps/backend/src/kenn/tests/test_answer_upgrades.py`: expired metric field.
- `apps/backend/src/kenn/tests/test_measure_background_swap.py`: accepted/busy
  harness context and admission-count regressions.
- `apps/frontend/src/api/kenn.ts`: carries chat identity on upgrade polling.
- `apps/frontend/src/api/kenn.test.ts`: encoded poll identity regression.
- `apps/frontend/src/composables/useKenn.ts`: current-message/turn delivery and
  accepted-source replacement.
- `apps/frontend/src/composables/useKenn.test.ts`: late delivery, removed message
  and source replacement regressions.
- `tooling/scripts/measure_background_swap.py`: matching scoped engine calls,
  one busy count and explicit sequential benchmark limits.
