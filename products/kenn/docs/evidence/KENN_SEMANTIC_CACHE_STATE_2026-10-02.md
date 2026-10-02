# Semantic cache and state-bound answers — 2 October 2026

This records a bounded A3 audit and fix on top of `124bd349`, landed as two commits
(preference invalidation, then state-bound answers). It supports [KENN_PLAN.md](../../KENN_PLAN.md); the broader request-owner
trace remains open.

## Reproduced defects and changed behavior

The semantic answer cache (`core/session_memory.py`, three tiers: in-memory exact,
NumPy matrix, SQLite) is keyed by session, query and a logic/index version string. It
lasts one hour. Source reading found three ways it could replay an answer that no
longer described the session:

1. **Preference changes did not invalidate it.** The preference citation and
   `applied_preferences` are appended inside the answer engine, so they are cached with
   the answer. After a preference was saved, restored, forgotten or the profile cleared,
   the old answer, citation included, kept coming back until the TTL ran out.
   `AssistantProfileStore` now calls the new `drop_session_semantic_cache` after each
   of those four changes (only when something actually changed). Putting it in the
   store covers HTTP, chat commands and MCP, which all write through it.
2. **The non-stream path cached proposals.** `answer_payload` stored any high-confidence
   payload. An orchestrator result with a proposal and `confirmation_token` was replayed
   for a repeat of the same single-turn question, without a fresh Live read and with a
   token that had already been used or had expired. The stream path already refused
   proposals, but not orchestrator results that carry no proposal (read-only Live answers).
   Both paths now share `_may_store_in_semantic_cache`, which rejects `proposal`,
   `requires_confirmation`, `confirmation_token` and `orchestration`.
3. **The non-stream path ignored the plug-in session.** The stream path skips the cache
   when `plugin_session_id` is set because plug-in context is not in the cache key.
   `answer_payload` read and wrote the cache regardless, and a cache hit skipped the
   orchestrator dispatch that consumes that identifier. It now skips both read and write.

Not changed: the cache key itself, the TTL, the threshold, grounding rules, or any
model or retrieval behavior.

## Verification

From `products/kenn/apps/backend/src`:

```sh
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests/test_preference_cache_invalidation.py kenn/tests/test_semantic_cache_state_bound.py kenn/tests/test_assistant_profile_memory.py kenn/tests/test_preference_history_restore.py kenn/tests/test_session_memory_preferences.py kenn/tests/test_stream_request_delivery.py kenn/tests/test_answer_upgrade_context.py kenn/tests/test_knowledge_request_context.py kenn/tests/test_chat_route_context.py kenn/tests/test_read_index_context.py
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests
```

- Scoped: 122 passed (before the proposal-only case was added).
- Full backend: **3,463 passed, 12 skipped, no failures** in 166.04 s; a second full
  run passed identically (3,463 / 12) in 175.80 s.
- Twelve deliberate mutations were caught: the four store call sites, the SQLite
  delete, the in-memory exact-tier delete, the non-stream plug-in guard, each of the
  four keys in the shared rule, and the non-stream write bypassing the shared rule. One
  mutation (dropping `proposal` from the rule) first survived because the test case
  also set the token; a proposal-only case was added and then catches it. Edited files
  were restored and byte-compared.

No model was loaded, nothing was written to Live, and no dependency or CI file changed.

## Remaining scope

Other answer routes can also describe state at a moment (mix-review follow-ups,
audio-generation payloads, track-memory answers). This slice only closed the ones with
a demonstrated replay path: proposals, tokens and orchestrator results. Live-state
change invalidation for those routes, raw trace/trust persistence, project switching
and Apply/Undo during generation remain open under A3. The `llm_answer_cache` table in
`llm/llm_rewrite.py` keys on model config and messages, so preference text that reaches
the prompt is already part of its key; that was read, not re-measured here.

## Exact changed files

Paths are relative to `products/kenn`.

- `apps/backend/src/kenn/core/session_memory.py`: `drop_session_semantic_cache`.
- `apps/backend/src/kenn/core/assistant_profile_memory.py`: drops the session's cache
  after record, restore, forget and clear.
- `apps/backend/src/kenn/core/chat_answer.py`: `_may_store_in_semantic_cache`, used by
  both paths; plug-in guard on the non-stream path.
- `apps/backend/src/kenn/tests/test_preference_cache_invalidation.py`: nine cases.
- `apps/backend/src/kenn/tests/test_semantic_cache_state_bound.py`: nine cases.
- `docs/evidence/KENN_SEMANTIC_CACHE_STATE_2026-10-02.md`: this receipt.
- `KENN_PLAN.md`: ticks this A3 slice.
