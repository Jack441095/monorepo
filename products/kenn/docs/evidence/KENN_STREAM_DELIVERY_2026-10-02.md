# Streaming request delivery — 2 October 2026

This records a bounded A3/A4 repair in [KENN_PLAN.md](../../KENN_PLAN.md).

## Reproduced defects and changed behavior

HTTP and CLI completion used concatenated provisional tokens ahead of the
engine's authoritative final answer. A grounding rejection could therefore show
the rejected draft even though the engine returned a replacement. Both consumers
now use final `metadata.answer` when present, including an explicit empty answer.
An empty SSE completion uses the existing generic terminal result envelope;
the regular nonempty assistant-response contract is unchanged.

Streams now evaluate the shared status/cancel/transport shortcuts before semantic
cache lookup. Direct and CLI bound requests register a turn; HTTP propagates its
already registered turn. Nonstring or oversized chat/plug-in identifiers become
unbound instead of aliasing another chat. Anonymous requests do not supersede
each other. Superseded delivery emits empty cancelled metadata that can retract
provisional text, while explicitly leaving actual inference cancellation unclaimed.

Session answer memory, semantic-cache writes and HTTP context/checkpoint/demo
finalization check ownership under the existing turn lock. A new turn or cancel
cannot race those writes. The lock covers persistence, including cache embedding;
it does not cover retrieval or answer generation. Cancellation may wait for an
already-started save.

Plug-in-bound answers bypass semantic cache because that key does not identify
current plug-in evidence. Proposal/confirmation events are excluded from cache.
Cache replay copies metadata and replaces request identifiers without mutating
stored events. Stream proposals expose the same top-level token and card flags
as foreground proposals; the play/stop shortcut reads its nested service token.

## Verification

The final scoped run passed 97 tests in 3.24 s, including 47 new stream-delivery
cases and three new owner-helper cases. Twenty-three behavior mutations were
caught using temporary compiled functions, with production source hashes
unchanged. Removing only one of two event-copy guards was redundant; removing
both reproduced the guarded cache-mutation defect.

```sh
# From products/kenn/apps/backend/src
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests/test_stream_request_delivery.py kenn/tests/test_answer_upgrade_context.py kenn/tests/test_streamed_generation_prefix_guard.py kenn/tests/test_llm_stream_honesty.py kenn/tests/test_chat_stream_weak_retrieval.py kenn/tests/test_mixing_doctor.py kenn/tests/test_semantic_cache_versioning.py kenn/tests/test_session_memory_preferences.py
```

The combined backend run passed **3,413 tests, 12 skips and six existing warnings
in 102.25 s**. Afterwards, the checkpoint regression's test double was refined to
return metadata: the focused case passed, and removing its owner guard failed the
intended final-answer assertion. Production code did not change after the full
run. Subsequent unused-helper deletion has its own scoped receipt.

Grounding thresholds, measurement/citation checks and the first-two-chunks prefix
guard are unchanged. All cases used deterministic fixtures; no model or real-Live
qualification is claimed. Broader nonstream cache invalidation after preference
or Live changes and raw trace/trust persistence remain audit items in the plan.

## Exact changed files

Paths are relative to `products/kenn`.

- `apps/backend/src/kenn/core/chat_answer.py`: stream wrappers, stream answer
  persistence, proposal fields and play/stop token extraction.
- `apps/backend/src/kenn/core/answer_upgrades.py`: owner observation/write helpers.
- `apps/backend/src/kenn/core/chat_cli.py`: both final-answer consumers.
- `apps/backend/src/kenn/server.py`: ask identifier normalization and SSE completion.
- `apps/backend/src/kenn/tests/test_answer_upgrade_context.py`.
- `apps/backend/src/kenn/tests/test_stream_request_delivery.py`.
- `docs/evidence/KENN_STREAM_DELIVERY_2026-10-02.md`: this receipt.
- `KENN_PLAN.md`: bounded stream-delivery check and remaining audit boundaries.
