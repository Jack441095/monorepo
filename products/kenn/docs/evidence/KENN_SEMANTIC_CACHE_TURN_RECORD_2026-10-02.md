# Semantic cache hits and session memory — 2 October 2026

Third A3 slice on the semantic answer cache, on top of `c95684be`. It supports
[KENN_PLAN.md](../../KENN_PLAN.md) and follows
[KENN_SEMANTIC_CACHE_SESSION_STATE_2026-10-02.md](KENN_SEMANTIC_CACHE_SESSION_STATE_2026-10-02.md).

## Reproduced defect and changed behavior

Session memory is written by the engine at the end of a run. A cache hit returns before
the engine runs, so a replayed answer was never recorded. Reproduced with the real
`update_session` and a stubbed engine: asking A twice gave a cache hit and the stored
turn count stayed at 1. With A, B, A the new test fails without the fix: the third ask
comes from the cache, so the count stops at 2 and `last_question` stays B. The next
follow-up would resolve against B's exchange, not the one the user had just seen. The replayed
payload (and, on the stream path, the replayed `session` event) also carried the session
block from the first asking.

New `_record_cache_hit_turn` in `core/chat_answer.py` records the replayed answer as a
turn. Both paths call it on a hit and refresh the session block from memory. The stream
path records inside `answer_upgrades.write_if_current`, so a request that was cancelled
or replaced between the shortcut check and the replay records nothing and is discarded.
The turn stores no retrieval results, because the cached ones belong to the first asking
and a follow-up would otherwise reuse them; an empty list makes it search fresh.

A request with no session id is unchanged in practice: a blank id loads empty state and
the engine already records into a throwaway session for it.

Not changed: the cache key, TTL, similarity threshold, what is stored, models or retrieval.

## Verification

From `products/kenn/apps/backend/src`:

```sh
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests/test_semantic_cache_turn_record.py kenn/tests/test_semantic_cache_state_bound.py kenn/tests/test_stream_request_delivery.py
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests
```

- Scoped: 73 passed across the three files (6 are new, in `test_semantic_cache_turn_record.py`).
- Full backend: 3,480 passed, 12 skipped, no failures (151.70 s), the earlier 3,474 plus the six new cases.
- Six deliberate mutations were each caught by the new file: the non-stream record call,
  the non-stream session refresh, the stream record call, the stream session-event
  refresh, the stream turn-ownership check and the empty retrieval list. The edited file
  was restored and byte-compared after each. My first attempt at the ownership mutation
  was malformed and my first test never reached the cache path; both were redone.

No model was loaded, nothing was written to Live, no dependency or CI file changed.

## Limits

- The engine is stubbed; the test stands in for its two-line tail (record the turn, attach
  the session block). A change to that tail would need the stub updated.
- A replayed turn updates last question, answer, topics and tracks but, by design, not the
  retrieval results. A follow-up right after a cache hit searches fresh instead of reusing
  the first asking's evidence. No latency effect was measured.
- This does not make cached answers current; it only keeps session memory in step with
  what the user was shown.

## Exact changed files

Paths are relative to `products/kenn`.

- `apps/backend/src/kenn/core/chat_answer.py`: `_record_cache_hit_turn` and its two call sites.
- `apps/backend/src/kenn/tests/test_semantic_cache_turn_record.py` (new, 6 cases).
- `docs/evidence/KENN_SEMANTIC_CACHE_TURN_RECORD_2026-10-02.md`: this receipt.
- `KENN_PLAN.md`: ticks this slice.
