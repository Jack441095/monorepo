# Thirty-question payload run, and what it showed about the stream cache — 2 October 2026

Recorded source: `efdd11f1` plus the uncommitted cache fix described below. The
[numeric receipt](KENN_C1_PAYLOAD_30Q_2026-10-02.json) is the raw output of one run. It is the **payload** surface
(`answer_payload`, the non-streaming path the HTTP upgrade runs), the counterpart to the
[stream baseline](KENN_C1_STREAM_30Q_2026-10-02.md). Same Mac, model, index, questions and order, same isolation
(FakeLive, temp chats and database, `KENN_LLM_CACHE=0`, semantic cache cleared between questions). The stream run
had finished before this one started, and nothing else heavy ran.

## Results

| | count |
| --- | ---: |
| Questions | 30 |
| Went to the model | 29 |
| Model finished and the answer was kept | 10 |
| Model finished but the answer fell back to the template | 2 |
| Model hit the 20 s read timeout, template served | 17 |

- Time to answer, all 30: median 20.06 s, p95 20.24 s. The p95 is just the timeout.
- Kept answers took 11.8 to 19.6 s. Against the plan's gate (70% accepted within 15 s) that is **3 of 30** (10%), and
  10 of 30 within 20 s. Gate failed, as on the stream surface.
- The 17 timeouts are 59% of the questions that reached the model. Stream completion on the same questions had a
  median of 18.9 s and a p95 of 28.5 s, so a 20 s cap cuts off roughly the slow half. That fits the numbers but we did
  not test it. In particular, 14 of the 17 timeouts fall after question 9, which looks like a streak, and we did not
  look for a cause (thermal, memory, longer answers).
- The runner's own `brain attempted/accepted` counters read 0 on this surface, and its "top rejection" is empty. They
  are not filled in for the payload path. The table above comes from each row's `llm_enhanced` flag, checked
  against the `make_answer` stage lines (same order, same counts: 10 enhanced, 19 fallback).
- The two fallbacks where the model finished (`bass-processing`, `sidechain-bass-disappears`) were rejected by the
  gate; the receipt does not say why on this surface.
- Compared with the stream run: stream got 22 of 29 accepted but late, payload got 10 of 29 and cut off at 20 s. Neither
  clears the 15 s gate. The 20 s foreground cap is what makes payload worse, so it is a setting to decide on, not a
  property of the model.

## What this showed about the stream cache

The runner clears the semantic cache between questions, so no benchmark so far could show cache effects. Reading
`_may_store_in_semantic_cache` for that reason turned up one real mismatch.

When a stream dies (timeout, dropped connection) with no usable candidate, the answer falls back to the template, which
is marked high confidence. That template was eligible for the semantic cache, with a one-hour TTL. After one slow
night, every repeat of that question on the stream surface would have skipped the model for an hour, even once the
load that caused the timeout had gone.

**Change**, `core/chat_answer.py`: the stream failure branch sets `generation_validation["transient"]` to true unless
the stream was stopped by the measurement guard, and `_may_store_in_semantic_cache` refuses transient results. A guard
trip is still cached, because a model that wrote an unsupported number once tends to do it again.

**Tests**: `test_a_dead_stream_is_marked_transient_and_a_guard_trip_is_not` (`test_streamed_generation_prefix_guard.py`),
`test_the_template_left_by_a_model_that_timed_out_is_not_cached` and
`test_the_template_left_by_a_rejected_answer_is_still_cached` (`test_semantic_cache_state_bound.py`). The first two
fail on the old code (checked by reverting `chat_answer.py`); the third pins existing behaviour. KENN suite: 3,555
passed, 5 skipped, 0 failed.

## Findings left alone

- **Route classification call.** When keyword routing finds nothing, `llm_route_query` can call the model. It ignores
  `allow_llm`, so the model-free foreground answer can still make one, and it has no cache. The foreground gives it
  20 s and the background 120 s, so the template and the upgrade could be built under different routes. It only
  fires on questions no keyword route matches, and we did not see it fire in either run. **Fixed 3 Oct:**
  `route_query` takes `allow_llm` and returns `unknown` instead of calling the model when it is false; the two
  `chat_answer.py` callers pass theirs. The retrieval-side call in `chat_retrieval.py` only runs when a calibration
  file exists, and none does today, so it is untouched. Tests: `test_route_query_model_free.py` (3,559 passed, 5
  skipped, 0 failed with a fresh pytest cache dir). Whether the foreground and background routes still differ when
  the model answers a route the keywords could not was not measured.
- **Non-streaming path.** A timeout there is not marked `transient`. The non-stream cache check also needs
  `record_session`, which the background upgrade does not set, so the exposure is smaller, but we did not trace the
  foreground path to confirm. Not changed.
- **Latent, unchecked in practice:** rejected answers are cached for 24 h in the LLM response cache; `max_tokens` is not
  part of that cache's key; the background run reads session state after the foreground has already updated it.

## What this does not cover

One run, no repeat for noise. Live-closed only. No admission, retrieval or verification timing, and no memory or audio
readings. The 20 s cap is the setting under test, not a finding about the model. C1 and the C2 template/upgrade item
both stay unticked.
