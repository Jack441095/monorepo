# Payload-path cache contract and C1 retrieval timing — 13 October 2026

Cloud session, Fake Live, stubbed model replies. No real model or Live run; no speed or quality result.

## The cache contract gap

The [2 Oct receipt](KENN_C1_PAYLOAD_30Q_AND_CACHE_CONTRACT_2026-10-02.md) fixed the stream: a timed-out stream
leaves a high-confidence template, and caching it keeps the model away from that question for an hour after the
load has gone. It listed the non-streaming path as "not marked `transient` … Not changed". That path is
`answer_payload()`, which the companion's `/api/ask` uses when background upgrades are off (the default,
`KENN_LLM_BACKGROUND` unset).

Shown before the fix with the real `make_answer()` and `enhance()` over fixture retrieval and the model call raising
`TimeoutError`: the payload read `confidence: "high"`, `generation_outcome: "generation returned no answer: request
failed"`, and `save_to_semantic_cache` was called once. `_may_store_in_semantic_cache` only read
`generation_validation.transient`, which this path never sets.

Fix, in `apps/backend/src/kenn/core/chat_answer.py`:

- `make_answer()` resets `_last_outcome.transient` on entry with the other per-thread outcome fields, and sets it
  only when `enhance()` failed with `request failed` (timeout, refused connection, any non-2xx status after its
  retry). `structure check` stays cacheable: that is the model's own output for that prompt and tends to repeat,
  the same reasoning as the stream's guard trip.
- `_answer_payload_raw()` adds `generation_transient` to the payload; `_may_store_in_semantic_cache` refuses it.

The background upgrade is not affected (it runs with `record_session=False`, which never touches the cache), and
nothing about grounding, retrieval or proposals changed.

Tests: `apps/backend/src/kenn/tests/test_payload_transient_cache.py`, 6 cases (timeout and refused connection not
cached; structure-check failure and accepted answer still cached; a stale flag from an earlier failed answer on
the thread does not mark a later weak-results template; the predicate reads the flag). Mutations, each restored
afterwards: the predicate ignoring the flag fails 4; marking every failure transient fails 1; dropping the reset
on entry fails 1.

## Retrieval timing in the C1 harness

`_answer_payload_raw()` has always returned `timings_ms` with `load_index_ms` and `search_ms`, and the companion
copies them into its `timing` block, but `measure_chat_latency.py` left `phase_seconds.context_retrieval` unknown.
It now fills it with their sum on the `payload` and `foreground` surfaces, keeps `payload_timings_ms` verbatim,
and leaves it unknown on `stream` (no timings there) and `background` (the timing belongs to the template, and the
upgrade retrieves again where we cannot see it). `route_query` runs before that window and the grounding gate runs
inside `answer_ms` with the model call, so neither is counted and `verification` stays unknown. Four new tests.

## Checks

- Scoped: 558 passed, 2 skipped across the 21 cache, payload, upgrade, stream and latency test files; 57 passed in
  `test_measure_chat_latency.py` and `test_captured_review_contract.py` after the timing change.
- Full backend suite (`KENN_LIVE_BACKEND=fake`): 4802 passed, 137 skipped, 1 failed. The failure is
  `test_query_typo_correction.py::test_typo_query_routes_to_production_and_avoids_weak_match_early_return`,
  which also fails on clean `main` (this container has no git-ignored index).

Still open from that receipt and not changed here: rejected answers stay in the 24 h LLM response cache (measurement
runs disable it with `KENN_LLM_CACHE=0`), and the background upgrade reads session state after the foreground has
updated it. C2 stays open.
