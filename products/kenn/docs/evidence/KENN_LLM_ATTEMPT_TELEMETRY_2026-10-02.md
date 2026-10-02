# Provider-attempt telemetry — 2 October 2026

Records the telemetry work landed in `97fe1c6f` and `2c071773`. It supports the C2 item
in [KENN_PLAN.md](../../KENN_PLAN.md) but does **not** complete it; the parent item
stays open.

## What changed

- `llm/llm_rewrite.py`: `LLMUsage` carries the provider's native load, prompt-eval and
  eval durations and token counts, the completion reason, and whether the call failed,
  was interrupted or came from the answer cache. `capture_usage()` collects every attempt
  made inside a request, and `get_public_usage_stats` reports the new counts. A metric the
  provider did not return is stored as unknown, not zero.
- `core/live_command.py`: the repair path keeps usage per call with an `attempts` count.
- `tooling/scripts/measure_chat_latency.py`: each question keeps its `provider_calls`, and
  the summary counts failures and cache hits.

## Verification

From `products/kenn/apps/backend/src`:

```sh
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests/test_llm_usage_telemetry.py kenn/tests/test_live_command.py kenn/tests/test_measure_chat_latency.py
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests
```

- The three files above: 174 passed (re-run for this receipt). The 230-test scoped run
  I made during review also covered neighbouring LLM test files and is not reproduced by
  this command.
- Full backend suite passed with no failures; the last recorded run (with the cache
  session-state work on top) was 3,474 passed, 12 skipped.
- `kenn/tests/test_llm_usage_telemetry.py` is new (315 lines).

## Limits

- **No mutation checks** were run on this slice, unlike the cache work. The tests assert
  the recorded fields, but I have not shown they fail when a field is dropped.
- **No real-model run.** Everything uses stubbed provider responses. Whether Ollama and
  the OpenAI-compatible path return these fields for the pinned Qwen3 models is not
  measured here.
- Superseded requests can still persist text or memory/cache writes through paths this
  slice did not touch, so that clause of the plan item is not covered.
- Route calls and rejected/interrupted streams are recorded when they go through
  `llm_rewrite`; any provider call that bypasses it is not.
- No latency or quality change is claimed.

## Exact changed files

Paths are relative to `products/kenn`.

- `apps/backend/src/kenn/llm/llm_rewrite.py`
- `apps/backend/src/kenn/core/live_command.py`
- `apps/backend/src/kenn/tests/test_llm_usage_telemetry.py` (new)
- `apps/backend/src/kenn/tests/test_live_command.py`
- `tooling/scripts/measure_chat_latency.py`
- `apps/backend/src/kenn/tests/test_measure_chat_latency.py`
