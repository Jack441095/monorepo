# Semantic cache and session-dependent answers — 2 October 2026

Second A3 slice on the semantic answer cache, on top of `13b4c91d`. It supports
[KENN_PLAN.md](../../KENN_PLAN.md) and follows
[KENN_SEMANTIC_CACHE_STATE_2026-10-02.md](KENN_SEMANTIC_CACHE_STATE_2026-10-02.md), which
closed proposals, tokens, orchestrator results and preference changes.

## Reproduced defects and changed behavior

The cache key is session, query and a logic/index version. Anything else an answer reads
is not in the key, so a repeat of the same query inside the one-hour TTL replayed the
first answer. Three more routes read that kind of state:

1. **Follow-ups and diagnostic reports.** "is that too loud?" and "the kick is still
   boomy" only mean something against the session summary or the active diagnostic plan.
   The cached answer came back even after the conversation had moved on.
2. **Saved mix reviews.** Answers built from `mix_review_timeline_lookup` or
   `latest_track_memory_lookup` were cached. A review saved after the first answer never
   reached the second.
3. **Audio generation.** `audio_generation_payload` queues a job and returns it as
   `audiogen`. A cache hit replayed that job record for a request that queued nothing.

New `_answer_reads_session_state(query, session_id)` in `core/chat_answer.py` is true for
a follow-up or an elliptical complaint ("still", "no change", "didn't work") inside a
session, for a reported diagnostic result, and for a mix-review or track-memory lookup.
Both the stream and non-stream paths skip the cache read and write when it is true.
A follow-up with no session has nothing to depend on and is still cached.
`_may_store_in_semantic_cache` also refuses any payload with an `audiogen` job record.

Not changed: the key, TTL, similarity threshold, grounding rules, models or retrieval.

## Verification

From `products/kenn/apps/backend/src`:

```sh
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests/test_semantic_cache_state_bound.py
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests
```

- Scoped: 20 passed (11 new cases over the earlier nine).
- Full backend: 3,474 passed, 12 skipped, no failures (129.81 s), run on the final tree
  with the state gate, the audiogen rule and both receipts in place. An earlier run before
  the audiogen rule gave 3,473 passed.
- Nine deliberate mutations were each caught by the file: the follow-up clause, the
  elliptical clause, the diagnostic clause, the timeline lookup, the track-memory lookup,
  the session requirement, the stream gate, the non-stream gate and the audiogen key. The
  edited file was restored and byte-compared after each.

No model was loaded, nothing was written to Live, no dependency or CI file changed.

## Limits

- The gate is a list of the routes found by reading the code. A new route that reads
  session state is not covered until it is added; the plan's request-owner trace stays open.
- `_ELLIPTICAL_TURN_RE` is a short word list. A complaint phrased without those words in
  a session is still cacheable if it is not a recognised follow-up.
- Cached knowledge answers are unaffected, so the cache still saves repeat latency for them.
  No latency numbers were measured here.

## Exact changed files

Paths are relative to `products/kenn`.

- `apps/backend/src/kenn/core/chat_answer.py`: `_ELLIPTICAL_TURN_RE`,
  `_answer_reads_session_state`, the gate in both paths, `audiogen` in the never-store keys.
- `apps/backend/src/kenn/tests/test_semantic_cache_state_bound.py`: 11 more cases.
- `docs/evidence/KENN_SEMANTIC_CACHE_SESSION_STATE_2026-10-02.md`: this receipt.
- `KENN_PLAN.md`: ticks this slice.
